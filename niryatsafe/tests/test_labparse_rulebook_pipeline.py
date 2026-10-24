import json, os, re, shutil, sqlite3, tempfile, unittest
from tests._util import ROOT, bundle
from niryatsafe.labparse import parse_line, parse_table
from niryatsafe.rulebook import compile_bundle, validate
from niryatsafe.engine import MESSAGE_KEYS, ACTION_KEYS


class LabParse(unittest.TestCase):
    def test_shared_cases(self):
        b = bundle()
        with open(os.path.join(ROOT, "tests", "labparse_cases.json"), encoding="utf-8") as fh:
            cases = json.load(fh)
        for c in cases:
            with self.subTest(line=c["line"]):
                r = parse_line(c["line"], b)
                if c["expect"] is None:
                    self.assertIsNone(r)
                else:
                    self.assertIsNotNone(r)
                    for k, v in c["expect"].items():
                        self.assertEqual(r.get(k), v, k)

    def test_table_roundtrip_into_engine(self):
        from niryatsafe.engine import evaluate
        text = "Parameter\tResult\tUnit\tLOQ\nTricyclazole\t0.04\tmg/kg\t0.01\nCarbendazim\tND\tmg/kg\t0.01\nrandom words here"
        t = parse_table(text, bundle())
        self.assertEqual(len(t["rows"]), 2)
        self.assertEqual(len(t["skipped"]), 2)  # header + noise
        r = evaluate({"results": t["rows"], "as_of": "2026-10-21"}, bundle())
        self.assertIn("result.tricyclazole", [f["id"] for f in r["findings"] if f["severity"] == "block"])


class Rulebook(unittest.TestCase):
    def test_bundle_is_valid(self):
        self.assertEqual(validate(compile_bundle()), [])

    def test_catalogs_have_same_placeholders_in_both_languages(self):
        b = bundle()
        ph = lambda s: sorted(set(re.findall(r"\{(\w+)\}", s)))
        for ns in ("m", "a"):
            for k, en in b["i18n"]["en"][ns].items():
                self.assertEqual(ph(en), ph(b["i18n"]["hi"][ns][k]), f"{ns}.{k}")
        for k in MESSAGE_KEYS:
            self.assertIn(k, b["i18n"]["hi"]["m"])
        for k in ACTION_KEYS:
            self.assertIn(k, b["i18n"]["hi"]["a"])

    def test_every_limit_has_a_resolvable_source_and_basis(self):
        b = bundle()
        for aid, a in b["analytes"].items():
            for blk in ("eu", "india"):
                for s in (a.get(blk) or {}).get("sources", []):
                    self.assertIn(s, b["sources"])
        for s in b["sources"].values():
            self.assertTrue(s["url"].startswith("https://"))
            self.assertIn(s["verified"], ("primary", "secondary", "unchecked"))

    def test_government_figures_in_rulebook(self):
        a = bundle()["analytes"]
        self.assertEqual(a["tricyclazole"]["limits"]["EU"]["limit"], 0.01)
        self.assertEqual(a["tricyclazole"]["limits"]["IN"]["limit"], 3.0)
        self.assertEqual(a["arsenic_inorganic"]["limits"]["EU"]["by_form"], {"raw_white": 0.15, "sella": 0.25, "brown": 0.25})
        self.assertEqual(a["triazophos"]["limits"]["EU"]["limit"], 0.02)
        self.assertEqual(a["aflatoxin_b1"]["limits"]["EU"]["limit"], 2.0)  # stored in ug/kg; the CSV row is 0.002 mg/kg

    def test_rules_csv_follows_the_deck_contract(self):
        import csv
        from niryatsafe.rulebook import RB
        with open(os.path.join(RB, "limits.csv"), newline="", encoding="utf-8") as fh:
            rd = csv.DictReader(fh)
            self.assertEqual(rd.fieldnames[:5], ["product", "substance", "market", "limit_mg_kg", "source"])
            rows = list(rd)
        self.assertGreater(len(rows), 300)
        r = [x for x in rows if x["substance"] == "tricyclazole" and x["market"] == "EU"][0]
        self.assertEqual((r["product"], r["limit_mg_kg"]), ("rice", "0.01"))

    def test_bad_rows_are_rejected_with_a_line_number(self):
        import tempfile
        from niryatsafe.rulebook import compile_bundle
        d = tempfile.mkdtemp()
        path = os.path.join(d, "limits.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("product,substance,market,limit_mg_kg,source\nrice,tricyclazole,EU,abc,reg_2017_983\nrice,tricyclazole,XX,0.01,reg_2017_983\nrice,tricyclazole,EU,0.01,\n")
        with self.assertRaises(ValueError) as cm:
            compile_bundle(limits_path=path)
        msg = str(cm.exception)
        self.assertIn("line 2", msg); self.assertIn("unknown market", msg); self.assertIn("needs a source", msg.replace("every rule needs a source", "needs a source"))

    def test_a_new_market_is_new_rows_not_new_code(self):
        """Add market XX (rows + a markets entry) without touching engine code: limits apply, docs/regime are reported as partial."""
        import copy
        from niryatsafe.engine import evaluate
        b = copy.deepcopy(bundle())
        b.pop("_index", None)
        b["markets"]["XX"] = {"name": {"en": "Testland", "hi": "टेस्टलैंड"}, "countries": ["XQ"], "default_limit": 0.05, "default_source": "reg_396_2005"}
        b["countries"]["XQ"] = {"en": "Xq", "hi": "Xq"}
        b["analytes"]["tricyclazole"]["limits"]["XX"] = {"limit": 0.2, "sources": ["reg_396_2005"], "basis": "law"}
        inp = {"lot": {"dest": "XQ"}, "results": [{"analyte": "tricyclazole", "status": "value", "value": 0.1, "unit": "mg/kg"}], "as_of": "2026-10-21"}
        r = evaluate(inp, b)
        f = [x for x in r["findings"] if x["id"] == "result.tricyclazole"][0]
        self.assertEqual((f["key"], f["params"]["limit"]), ("limit_ok", 0.2))      # 0.1 passes the test market, would block in the EU
        self.assertIn("market_partial", [x["key"] for x in r["findings"]])
        inp["lot"]["dest"] = "DE"
        self.assertEqual([x for x in evaluate(inp, b)["findings"] if x["id"] == "result.tricyclazole"][0]["key"], "limit_exceeded")


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, fixtures):
        from pipeline.build import build
        fx = os.path.join(ROOT, "data", "fixtures")
        db, sig = os.path.join(self.tmp, "t.db"), os.path.join(self.tmp, "signals.json")
        return build(db, sig, [os.path.join(fx, "rasff_export_SYNTHETIC.csv")] if fixtures else [],
                     [os.path.join(fx, "fda_refusals_SYNTHETIC.csv")] if fixtures else [], "2026-10-21", bundle_path=False), db

    def test_reference_only_matches_government_table(self):
        sig, db = self.build(False)
        self.assertFalse(sig["demo"])
        self.assertEqual(sig["by_analyte"]["tricyclazole"]["total"], 97)
        self.assertEqual(sig["by_analyte"]["thiamethoxam"]["total"], 60)
        self.assertEqual(sig["by_analyte"]["tricyclazole"]["by_year"]["2023"], 19)
        self.assertEqual(sig["recent_span"], [2021, 2025])
        self.assertEqual(sig["by_analyte"]["tricyclazole"]["recent"], 6 + 22 + 19 + 19 + 2)

    def test_synthetic_fixtures_are_flagged_and_filtered(self):
        sig, db = self.build(True)
        self.assertTrue(sig["demo"])
        con = sqlite3.connect(db)
        n_all = con.execute("select count(*) from events where source='rasff'").fetchone()[0]
        n_in = con.execute("select count(*) from v_india_rice_eu").fetchone()[0]
        self.assertGreater(n_all, n_in)                       # Pakistan + sesame + groundnut rows filtered out
        self.assertEqual(con.execute("select count(*) from events where synthetic=0").fetchone()[0], 0)
        self.assertTrue(all(e.startswith("SYN-") for (e,) in con.execute("select event_id from events where source='rasff'")))
        self.assertIn("us", sig)
        self.assertTrue(sig["us"]["synthetic"])

    def test_raw_events_replace_reference_for_covered_years(self):
        sig, _ = self.build(True)
        by = sig["by_analyte"]["tricyclazole"]["by_year"]
        self.assertNotEqual(by.get("2024"), 19)  # reference value for 2024 replaced by (synthetic) raw count
        self.assertEqual(by.get("2018"), 14)     # years not covered by raw data keep the reference value

    def test_backtest_harness_and_limits_table(self):
        import pandas as pd
        from pipeline.backtest import backtest
        from pipeline.ingest import load_rasff
        fx = os.path.join(ROOT, "data", "fixtures", "rasff_export_SYNTHETIC.csv")
        ev = load_rasff(fx, bundle(), synthetic=True)
        res = backtest(ev, bundle(), "2026-10-21")
        self.assertGreater(res["with_measured_value"], 10)
        self.assertGreaterEqual(res["hit_rate"], 0.95)       # every synthetic value sits above or near an EU limit
        self.assertTrue(res["synthetic"])
        sig, db = self.build(True)
        con = sqlite3.connect(db)
        n = con.execute("select count(*) from limits where market='EU'").fetchone()[0]
        self.assertGreater(n, 300)
        row = con.execute("select limit_mg_kg, alerts_on_indian_rice from v_limits_and_refusals where substance='tricyclazole'").fetchone()
        self.assertEqual(row, (0.01, 97))

    def test_limits_diff_against_an_eu_export(self):
        from niryatsafe.rulebook import read_limits
        from pipeline.limits import diff, load_export
        path = os.path.join(self.tmp, "eu.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("Pesticide residue,Product,MRL (mg/kg)\nTricyclazole,Rice,0.01*\nTriazophos,Rice,0.05\nNewazole,Rice,0.02\nTricyclazole,Rice flour,9\nTebuconazole,Wheat,1.5\n")
        ex = load_export(path)
        self.assertEqual(sorted(ex), ["newazole", "triazophos", "tricyclazole"])
        res = diff(read_limits(), bundle(), ex)
        self.assertEqual(res["changed"], [("triazophos", 0.02, 0.05)])
        self.assertIn(("Newazole", 0.02), res["only_in_export"])
        self.assertGreaterEqual(res["same"], 1)

    def test_value_extraction(self):
        from pipeline.normalize import extract_value
        self.assertEqual(extract_value("Tricyclazole (0,22 mg/kg) in rice"), (0.22, "mg/kg"))
        self.assertEqual(extract_value("Aflatoxin B1 3.5 \u00b5g/kg"), (3.5, "ug/kg"))
        self.assertEqual(extract_value("live insects"), (None, None))

    def test_date_orders(self):
        import pandas as pd
        from pipeline.ingest import _iso
        s = pd.Series(["2024-03-05", "05/03/2024", "13/03/2024"])
        self.assertEqual(list(_iso(s, "dmy")), ["2024-03-05", "2024-03-05", "2024-03-13"])
        s = pd.Series(["03/05/2024", "2024-03-05"])
        self.assertEqual(list(_iso(s, "mdy")), ["2024-03-05", "2024-03-05"])

    def test_header_mapping_and_hazard_groups(self):
        from pipeline.normalize import hazard_group, canon_header, extract_substances, build_alias_index
        self.assertEqual(canon_header("Date of case"), "dateofcase")
        self.assertEqual(hazard_group("Aflatoxins in rice"), "mycotoxin")
        self.assertEqual(hazard_group("Live insects in rice"), "pest_infestation")
        pairs = build_alias_index(bundle())
        self.assertEqual(extract_substances("Tricyclazole in basmati rice from India", pairs), ["tricyclazole"])
        self.assertEqual(extract_substances("Diazinon and thiamethoxam in rice", pairs).__len__(), 2)


if __name__ == "__main__":
    unittest.main()

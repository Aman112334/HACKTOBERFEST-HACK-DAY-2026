import copy, random, unittest
from tests._util import AS_OF, bundle, sample, run, keys, ids
from niryatsafe.engine import evaluate, normalize_input, canon, memo_id, cyrb53, days_from_civil, parse_date

BASE_OK = lambda: sample("clean")


class Samples(unittest.TestCase):
    def test_expected_verdicts(self):
        for s in bundle()["samples"]:
            with self.subTest(sample=s["id"]):
                self.assertEqual(run(sample(s["id"]))["verdict"], s["expect"])

    def test_clean_has_no_blockers_or_fixes(self):
        r = run(sample("clean"))
        self.assertEqual((r["counts"]["block"], r["counts"]["fix"]), (0, 0))
        self.assertEqual(r["steps"], 0)

    def test_india_pass_eu_fail_is_flagged(self):
        r = run(sample("hold"))
        f = [x for x in r["findings"] if x["id"] == "result.tricyclazole"][0]
        self.assertEqual(f["severity"], "block")
        self.assertTrue(f["params"]["india_ok"])
        self.assertEqual(f["params"]["india_limit"], 3.0)
        self.assertEqual(f["params"]["limit"], 0.01)


class Limits(unittest.TestCase):
    def one(self, analyte, **row):
        inp = sample("clean")
        inp["results"] = [r for r in inp["results"] if r["analyte"] != analyte] + [dict(analyte=analyte, **row)]
        return run(inp)

    def f(self, res, analyte):
        return [x for x in res["findings"] if x["id"] == "result." + analyte][0]

    def test_above_limit_blocks(self):
        r = self.one("tricyclazole", status="value", value=0.02, unit="mg/kg")
        self.assertEqual(r["verdict"], "HOLD")
        self.assertEqual(self.f(r, "tricyclazole")["key"], "limit_exceeded")

    def test_equal_to_limit_is_watch_not_block(self):
        r = self.one("tricyclazole", status="value", value=0.01, unit="mg/kg")
        self.assertEqual(self.f(r, "tricyclazole")["key"], "limit_close")
        self.assertEqual(r["verdict"], "FIX_FIRST")

    def test_just_under_watch_band_passes(self):
        r = self.one("tricyclazole", status="value", value=0.0079, unit="mg/kg")
        self.assertEqual(self.f(r, "tricyclazole")["severity"], "pass")

    def test_unit_equivalence(self):
        for val, unit in ((3.0, "ug/kg"), (3.0, "ppb"), (0.003, "mg/kg"), (0.003, "ppm"), (3.0, "µg/kg")):
            r = self.one("aflatoxin_b1", status="value", value=val, unit=unit)
            self.assertEqual(self.f(r, "aflatoxin_b1")["key"], "limit_exceeded", (val, unit))
        r = self.one("aflatoxin_b1", status="value", value=1.0, unit="ug/kg")
        self.assertEqual(self.f(r, "aflatoxin_b1")["severity"], "pass")

    def test_unknown_unit_is_fix_not_pass(self):
        r = self.one("cadmium", status="value", value=0.05, unit="furlongs")
        self.assertEqual(self.f(r, "cadmium")["key"], "unit_unknown")

    def test_nd_with_loose_loq_cannot_prove_compliance(self):
        r = self.one("carbendazim", status="nd", unit="mg/kg", loq=0.05)
        self.assertEqual(self.f(r, "carbendazim")["key"], "loq_too_high")
        self.assertEqual(r["verdict"], "FIX_FIRST")

    def test_nd_without_loq_is_fix(self):
        r = self.one("carbendazim", status="nd", unit="mg/kg")
        self.assertEqual(self.f(r, "carbendazim")["key"], "loq_missing")

    def test_triazophos_has_its_own_limit(self):
        # EU limit for triazophos in rice is 0.02 (not 0.01): 0.015 is 75% of it -> pass; 0.017 -> watch; 0.021 -> block
        self.assertEqual(self.f(self.one("triazophos", status="value", value=0.015, unit="mg/kg"), "triazophos")["key"], "limit_ok")
        self.assertEqual(self.f(self.one("triazophos", status="value", value=0.017, unit="mg/kg"), "triazophos")["key"], "limit_close")
        self.assertEqual(self.f(self.one("triazophos", status="value", value=0.021, unit="mg/kg"), "triazophos")["key"], "limit_exceeded")

    def test_worst_case_wins_for_duplicate_rows(self):
        inp = sample("clean")
        inp["results"].append({"analyte": "Tricyclazol", "status": "value", "value": 0.5, "unit": "mg/kg"})
        r = run(inp)
        self.assertEqual(r["verdict"], "HOLD")

    def test_default_limit_for_unlisted_pesticide_in_loq_list(self):
        r = self.one("Diazinon", status="value", value=0.05, unit="mg/kg")
        self.assertEqual(r["verdict"], "HOLD")

    def test_unknown_substance_above_default_is_verify_not_hold(self):
        r = self.one("Foobarazole", status="value", value=0.05, unit="mg/kg")
        self.assertIn("verify_mrl", keys(r, "fix"))
        self.assertEqual(r["verdict"], "FIX_FIRST")

    def test_mu_note_only_when_exceedance_is_within_uncertainty(self):
        r = self.one("tricyclazole", status="value", value=0.012, unit="mg/kg")
        self.assertIn("mu_note", keys(r))
        r = self.one("tricyclazole", status="value", value=0.2, unit="mg/kg")
        self.assertNotIn("mu_note", keys(r))

    def test_hold_adds_no_blending_note(self):
        self.assertIn("no_blending", keys(run(sample("hold"))))


class Arsenic(unittest.TestCase):
    def lot(self, form, analyte, value):
        inp = sample("clean")
        inp["lot"]["form"] = form
        inp["results"] = [r for r in inp["results"] if not r["analyte"].startswith("arsenic")]
        inp["results"].append({"analyte": analyte, "status": "value", "value": value, "unit": "mg/kg"})
        return run(inp)

    def test_limit_depends_on_form(self):
        self.assertEqual(self.lot("raw_white", "arsenic_inorganic", 0.2)["verdict"], "HOLD")
        r = self.lot("sella", "arsenic_inorganic", 0.2)  # 0.2 is exactly 80% of 0.25 -> watch
        self.assertEqual(r["verdict"], "FIX_FIRST")
        self.assertEqual(self.lot("sella", "arsenic_inorganic", 0.1)["verdict"], "SHIP")

    def test_total_arsenic_over_limit_asks_for_speciation_not_hold(self):
        r = self.lot("raw_white", "arsenic_total", 0.3)
        self.assertEqual(r["verdict"], "FIX_FIRST")
        self.assertIn("as_total_speciation", keys(r, "fix"))

    def test_total_arsenic_under_limit_passes(self):
        self.assertEqual(self.lot("raw_white", "arsenic_total", 0.1)["verdict"], "SHIP")


class Evidence(unittest.TestCase):
    def test_no_evidence_is_never_ship(self):
        inp = sample("clean")
        inp["results"], inp["lab"]["screen"] = [], False
        r = run(inp)
        self.assertEqual(r["verdict"], "FIX_FIRST")
        self.assertIn("lab_missing", keys(r))

    def test_screen_covers_unreported_must_analytes(self):
        inp = sample("clean")
        inp["results"] = [x for x in inp["results"] if x["analyte"] != "tricyclazole"]
        r = run(inp)
        self.assertEqual(r["verdict"], "SHIP")
        self.assertIn("covered_by_screen", keys(r))

    def test_without_screen_missing_must_analyte_is_fix(self):
        inp = sample("clean")
        inp["lab"]["screen"] = False
        inp["results"] = [x for x in inp["results"] if x["analyte"] != "tricyclazole"]
        r = run(inp)
        self.assertIn("required.tricyclazole", ids(r, "fix"))

    def test_spray_makes_analyte_required_and_ranks_it_first(self):
        inp = sample("early")
        r = run(inp)
        required = [f for f in r["findings"] if f["severity"] == "fix" and f["id"].startswith("required.")]
        self.assertEqual(required[0]["params"].get("reason"), "sprayed")
        self.assertEqual(required[0]["analyte"], "tebuconazole" if "tebuconazole" in r["input"]["sprays"] else required[0]["analyte"])

    def test_unknown_sprayed_substance_is_fix(self):
        r = run(sample("early"))
        self.assertIn("farm.sprayed.unk:isoprothiolane", ids(r, "fix"))

    def test_punjab_note_only_for_punjab_origin(self):
        inp = sample("hold")
        self.assertIn("sprayed_note_gap_punjab", keys(run(inp)))
        inp["lot"]["origin"] = "haryana"
        self.assertNotIn("sprayed_note_gap_punjab", keys(run(inp)))


class Papers(unittest.TestCase):
    def test_missing_and_unconfirmed(self):
        r = run(sample("fix"))
        self.assertIn("doc.phyto", ids(r, "fix"))
        self.assertIn("doc.coi", ids(r, "fix"))
        self.assertIn("doc.ched_d", ids(r, "note"))  # importer-side, never blocks

    def test_label_checks_are_out_of_scope_for_v01(self):
        self.assertNotIn("doc.labels", ids(run(sample("clean"))))


class Dates(unittest.TestCase):
    def test_age_boundary(self):
        inp = sample("clean")
        inp["lot"]["ship_date"] = "2026-11-10"
        inp["lab"]["report_date"] = "2026-09-11"   # exactly 60 days
        self.assertIn("lab_fresh", keys(run(inp)))
        inp["lab"]["report_date"] = "2026-09-10"   # 61 days
        self.assertIn("lab_stale", keys(run(inp)))

    def test_report_after_ship_is_invalid(self):
        inp = sample("clean")
        inp["lab"]["report_date"] = "2026-12-01"
        self.assertIn("lab_date_invalid", keys(run(inp)))

    def test_as_of_required(self):
        with self.assertRaises(ValueError):
            evaluate({"lot": {}}, bundle())

    def test_civil_days(self):
        self.assertEqual(days_from_civil(1970, 1, 1), 0)
        self.assertEqual(days_from_civil(2026, 3, 1) - days_from_civil(2026, 2, 1), 28)
        self.assertIsNone(parse_date("2026-13-01"))


class Properties(unittest.TestCase):
    def rand_lot(self, rnd):
        b = bundle()
        names = list(b["analytes"]) + ["Diazinon", "Foobarazole"]
        inp = {"lot": {"form": rnd.choice(["raw_white", "sella", "brown"]), "dest": rnd.choice(["", "DE", "NL", "FR", "US", "EU"]),
                       "ship_date": rnd.choice([None, "2026-11-05", "2026-12-20"]), "origin": rnd.choice(["punjab", "haryana", ""]),
                       "lot_id": rnd.choice(["", "A-1"])},
               "lab": {"accredited": rnd.choice([True, False, None]), "report_date": rnd.choice([None, "2026-10-01", "2026-06-01"]),
                       "linked": rnd.choice([True, False, None]), "sampling": rnd.choice(["third_party", "lab", "self", None]),
                       "screen": rnd.choice([True, False, None])},
               "results": [], "sprays": [], "docs": {}, "as_of": AS_OF}
        for n in rnd.sample(names, rnd.randint(0, 12)):
            if rnd.random() < 0.5:
                inp["results"].append({"analyte": n, "status": "nd", "unit": rnd.choice(["mg/kg", "ug/kg", "ppb"]),
                                       "loq": rnd.choice([None, 0.001, 0.01, 0.05, 1.0])})
            else:
                inp["results"].append({"analyte": n, "status": "value", "value": rnd.choice([0.002, 0.008, 0.01, 0.05, 0.3, 1.5, 4.0]),
                                       "unit": rnd.choice(["mg/kg", "ug/kg", "ppm", "ppb", "stone"]), "loq": None})
        inp["sprays"] = rnd.sample(names + ["Mystery 5"], rnd.randint(0, 3))
        for d in ("iec", "rcac", "phyto", "coi", "invoice_pl", "ched_d"):
            inp["docs"][d] = rnd.choice([True, False, None])
        return inp

    def test_determinism_and_hold_requires_law(self):
        rnd = random.Random(11)
        for _ in range(150):
            inp = self.rand_lot(rnd)
            a, b = run(inp), run(inp)
            self.assertEqual(canon(a), canon(b))
            if a["verdict"] == "HOLD":
                blocks = [f for f in a["findings"] if f["severity"] == "block"]
                self.assertTrue(all(f["basis"] == "law" and f["key"] == "limit_exceeded" for f in blocks))
            if a["verdict"] == "SHIP":
                self.assertEqual(a["counts"]["fix"] + a["counts"]["block"], 0)

    def test_removing_exceedances_never_leaves_a_hold(self):
        rnd = random.Random(5)
        for _ in range(100):
            inp = self.rand_lot(rnd)
            r = run(inp)
            bad = {f["analyte"] for f in r["findings"] if f["severity"] == "block"}
            if not bad:
                continue
            from niryatsafe.engine import resolve
            inp2 = copy.deepcopy(inp)
            inp2["results"] = [x for x in inp2["results"] if (resolve(x["analyte"], bundle())["id"] if resolve(x["analyte"], bundle())["kind"] == "analyte" else x["analyte"]) not in bad]
            self.assertNotEqual(run(inp2)["verdict"], "HOLD")

    def test_no_results_no_screen_never_ships(self):
        rnd = random.Random(3)
        for _ in range(60):
            inp = self.rand_lot(rnd)
            inp["results"], inp["lab"]["screen"] = [], False
            self.assertNotEqual(run(inp)["verdict"], "SHIP")

    def test_memo_id_changes_with_input(self):
        a, b = sample("clean"), sample("clean")
        b["lot"]["lot_id"] = "different"
        self.assertNotEqual(run(a)["memo_id"], run(b)["memo_id"])
        self.assertEqual(run(a)["memo_id"], run(copy.deepcopy(a))["memo_id"])

    def test_cyrb53_reference_values(self):
        self.assertEqual(cyrb53(""), 3338908027751811)
        self.assertEqual(cyrb53("a"), 7929297801672961)  # values from the JS reference implementation
        self.assertEqual(cyrb53("NiryatSafe|\u0928"), 2060174726641122)


if __name__ == "__main__":
    unittest.main()

"""python -m pipeline build [--rasff FILE ...] [--fda FILE ...] [--fixtures] | inspect FILE | audit"""
from __future__ import annotations

import argparse
import os
import sys

from .build import DEFAULT_DB, DEFAULT_SIGNALS, ROOT, audit, build
from .ingest import inspect


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build SQLite + signals.json + compiled bundle")
    b.add_argument("--rasff", nargs="*", default=[], help="RASFF Window export(s), CSV or XLSX")
    b.add_argument("--fda", nargs="*", default=[], help="FDA import refusal export(s), CSV or XLSX")
    b.add_argument("--raw-dir", default=os.path.join(ROOT, "data", "raw"),
                   help="also pick up rasff*.csv/xlsx and fda*.csv/xlsx from this folder")
    b.add_argument("--fixtures", action="store_true", help="add the SYNTHETIC test fixtures (demo only)")
    b.add_argument("--db", default=DEFAULT_DB)
    b.add_argument("--out", default=DEFAULT_SIGNALS)
    b.add_argument("--as-of", default=None)
    i = sub.add_parser("inspect", help="show how a raw export's columns are mapped")
    i.add_argument("file")
    sub.add_parser("audit", help="compare rulebook tiers with the refusal signals")
    ld = sub.add_parser("limits-diff", help="compare rules/limits.csv with an EU Pesticides Database export (pre-release review)")
    ld.add_argument("file")
    ld.add_argument("--write-candidates", default=None)
    bt = sub.add_parser("backtest", help="would NiryatSafe have flagged past refused lots? (needs a RASFF export with values)")
    bt.add_argument("--rasff", nargs="*", default=[])
    bt.add_argument("--fixtures", action="store_true")
    bt.add_argument("--as-of", default=None)
    a = ap.parse_args(argv)

    if a.cmd == "inspect":
        print(inspect(a.file))
        return 0
    if a.cmd == "audit":
        from niryatsafe.rulebook import compile_bundle
        notes = audit(compile_bundle())
        print("\n".join(notes) if notes else "tiers agree with the signals")
        return 0
    if a.cmd == "limits-diff":
        from niryatsafe.rulebook import compile_bundle, read_limits
        from .limits import diff, load_export, render, write_candidates
        res = diff(read_limits(), compile_bundle(), load_export(a.file))
        print(render(res))
        if a.write_candidates:
            write_candidates(res, a.write_candidates)
            print("candidate rows written to", a.write_candidates)
        return 1 if (res["changed"] or res["only_in_export"]) else 0
    if a.cmd == "backtest":
        import pandas as pd
        from datetime import date
        from niryatsafe.rulebook import compile_bundle
        from .backtest import backtest, render
        from .ingest import load_rasff
        b = compile_bundle()
        files = list(a.rasff) + ([os.path.join(ROOT, "data", "fixtures", "rasff_export_SYNTHETIC.csv")] if a.fixtures else [])
        if not files:
            files = [os.path.join(ROOT, "data", "raw", f) for f in sorted(os.listdir(os.path.join(ROOT, "data", "raw")))
                     if f.lower().startswith("rasff") and f.lower().endswith((".csv", ".xlsx"))] if os.path.isdir(os.path.join(ROOT, "data", "raw")) else []
        if not files:
            sys.exit("no RASFF export given: pass --rasff FILE, drop one in data/raw/, or use --fixtures to test the harness")
        ev = pd.concat([load_rasff(f, b, synthetic="synthetic" in f.lower()) for f in files], ignore_index=True)
        print(render(backtest(ev, b, a.as_of or date.today().isoformat())))
        return 0
    rasff, fda = list(a.rasff), list(a.fda)
    if os.path.isdir(a.raw_dir):
        for f in sorted(os.listdir(a.raw_dir)):
            low = f.lower()
            if low.endswith((".csv", ".xlsx", ".xls")):
                (rasff if low.startswith("rasff") else fda if low.startswith("fda") else []).append(os.path.join(a.raw_dir, f))
    if a.fixtures:
        fx = os.path.join(ROOT, "data", "fixtures")
        rasff.append(os.path.join(fx, "rasff_export_SYNTHETIC.csv"))
        fda.append(os.path.join(fx, "fda_refusals_SYNTHETIC.csv"))
    sig = build(a.db, a.out, rasff, fda, a.as_of)
    print(f"signals: {sig['totals']['notifications']} notifications, years {sig['totals']['first_year']}-{sig['totals']['last_year']}, "
          f"sources={len(sig['sources'])}{' (INCLUDES SYNTHETIC DATA)' if sig['demo'] else ''}")
    print(f"sqlite : {a.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

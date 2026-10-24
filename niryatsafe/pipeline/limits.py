"""Compare rules/limits.csv with an export from the EU Pesticides Database (rice MRLs): the pre-release review step.

    python -m pipeline limits-diff EXPORT.csv|xlsx [--write-candidates proposed_rows.csv]

Reads the export with flexible column names (substance / product / MRL), keeps the rows for rice, and reports
  changed          the MRL differs from our row                (a maintainer decides, then edits limits.csv)
  only_in_export   the EU lists it, we have no row            (candidate new rows)
  only_in_rules    we have a row, the export does not list it (check that it is still current)
Exit code 1 when anything differs, so a release script can refuse to continue until a maintainer has looked."""
from __future__ import annotations

import csv
import re

from niryatsafe.engine import norm

from .ingest import read_table
from .normalize import canon_header

COLS = {
    "substance": ["pesticideresidue", "pesticideresidues", "pesticide", "residue", "substance", "activesubstance"],
    "product": ["product", "productname", "commodity", "productdescription", "productcode"],
    "mrl": ["mrl", "mrlmgkg", "mrlvalue", "maximumresiduelevel", "mrlmgperkg", "valuemgkg"],
}


def _col(df, key):
    look = {canon_header(c): c for c in df.columns}
    for w in COLS[key]:
        if w in look:
            return look[w]
    raise ValueError(f"export has no {key} column; found {list(df.columns)}")


def parse_mrl(v):
    m = re.search(r"\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def load_export(path: str) -> dict:
    df = read_table(path)
    sc, pc, mc = _col(df, "substance"), _col(df, "product"), _col(df, "mrl")
    out = {}
    for _, r in df.iterrows():
        prod = str(r[pc]).lower()
        if not re.search(r"\brice\b", prod) or re.search(r"flour|waffle|cake|wild|starch|bran|straw|cracker", prod):
            continue
        v = parse_mrl(r[mc])
        if v is not None:
            out[norm(r[sc])] = (str(r[sc]).strip(), v)
    return out


def diff(rules_rows: list, bundle: dict, export: dict) -> dict:
    kinds = {}
    for aid, a in bundle["analytes"].items():
        kinds[norm(aid)] = a["kind"]
        kinds[norm(a["names"]["en"])] = a["kind"]
    ours = {}
    for r in rules_rows:
        if r["market"].strip() != "EU" or (r.get("form") or "").strip():
            continue
        k = norm(r["substance"])
        if kinds.get(k, "pesticide") == "pesticide":
            ours[k] = (r["substance"], float(r["limit_mg_kg"]))
    changed = [(ours[k][0], ours[k][1], export[k][1]) for k in sorted(ours) if k in export and abs(ours[k][1] - export[k][1]) > 1e-9]
    only_export = [(export[k][0], export[k][1]) for k in sorted(export) if k not in ours]
    only_rules = [ours[k][0] for k in sorted(ours) if k not in export]
    return {"changed": changed, "only_in_export": only_export, "only_in_rules": only_rules,
            "same": sum(1 for k in ours if k in export and abs(ours[k][1] - export[k][1]) <= 1e-9)}


def render(res: dict) -> str:
    lines = [f"unchanged: {res['same']}", f"changed: {len(res['changed'])}"]
    lines += [f"  {s}: ours {a} -> EU database {b}" for s, a, b in res["changed"][:25]]
    lines.append(f"only in the EU export (candidate new rows): {len(res['only_in_export'])}")
    lines += [f"  {s}: {v}" for s, v in res["only_in_export"][:25]]
    lines.append(f"only in our rules (confirm they are still current): {len(res['only_in_rules'])}")
    lines += [f"  {s}" for s in res["only_in_rules"][:25]]
    return "\n".join(lines)


def write_candidates(res: dict, path: str):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["product", "substance", "market", "limit_mg_kg", "source", "form", "basis", "note"])
        for s, _a, b in res["changed"]:
            w.writerow(["rice", s, "EU", b, "eu_pesticides_db", "", "law", "CHANGED: replaces the existing row; maintainer to confirm"])
        for s, v in res["only_in_export"]:
            w.writerow(["rice", s.lower(), "EU", v, "eu_pesticides_db", "", "law", "NEW from EU Pesticides Database export"])

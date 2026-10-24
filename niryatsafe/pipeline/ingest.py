"""Read RASFF / FDA exports and the Government of India reference tables into one common schema."""
from __future__ import annotations

import hashlib
import os

import pandas as pd

from .normalize import SYNONYMS, build_alias_index, detect_mapping, extract_substances, extract_value, hazard_group, is_rice

EVENT_COLS = ["source", "event_id", "event_date", "destination", "origin_country", "product_text", "is_rice",
              "hazard_group", "substance", "value", "unit", "action", "synthetic"]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def read_table(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype=str).fillna("")
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, keep_default_na=False)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"cannot decode {path}")


def _iso(series: pd.Series, order: str = "dmy") -> pd.Series:
    """ISO first (never flipped); then day-first (RASFF exports) or month-first (FDA exports) numeric dates."""
    fmts = ["%Y-%m-%d", "%Y/%m/%d"] + (["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"] if order == "dmy"
                                          else ["%m/%d/%Y", "%m-%d-%Y"])
    out = pd.Series([pd.NaT] * len(series), index=series.index, dtype="datetime64[ns]")
    for f in fmts:
        out = out.fillna(pd.to_datetime(series.astype(str).str.slice(0, 10), format=f, errors="coerce"))
    return out.dt.strftime("%Y-%m-%d")


def _cell(row, col):
    return str(row[col]).strip() if col else ""


def load_rasff(path: str, bundle: dict, synthetic: bool = False) -> pd.DataFrame:
    df = read_table(path)
    m = detect_mapping(df, ["event_id", "event_date", "ntype", "subject", "category", "origin", "hazards",
                            "hazard_category", "action", "result"])
    if not m["subject"] or not m["event_date"]:
        raise ValueError(f"{os.path.basename(path)}: need at least Subject and Date columns, found {list(df.columns)}")
    alias = build_alias_index(bundle)
    out = []
    for i, row in df.iterrows():
        subject, hazards, cat = _cell(row, m["subject"]), _cell(row, m["hazards"]), _cell(row, m["category"])
        subs = extract_substances(f"{subject} {hazards}", alias) or [None]
        value, unit = extract_value(f"{_cell(row, m['result'])} {hazards} {subject}")
        for sub in subs:
            out.append({
                "source": "rasff", "value": value, "unit": unit, "event_id": _cell(row, m["event_id"]) or f"row{i}", "_date": row[m["event_date"]],
                "destination": "EU", "origin_country": _cell(row, m["origin"]), "product_text": subject,
                "is_rice": int(is_rice(f"{subject} {cat}")),
                "hazard_group": hazard_group(f"{subject} {hazards}", _cell(row, m["hazard_category"])),
                "substance": sub, "action": _cell(row, m["action"]), "synthetic": int(synthetic),
            })
    return _finish(out)


def load_fda(path: str, bundle: dict, synthetic: bool = False) -> pd.DataFrame:
    df = read_table(path)
    m = detect_mapping(df, ["fda_date", "fda_country", "fda_desc", "fda_charges", "fda_fei", "fda_product_code"])
    if not m["fda_date"] or not m["fda_charges"]:
        raise ValueError(f"{os.path.basename(path)}: need Refusal Date and Refusal Charges columns, found {list(df.columns)}")
    alias = build_alias_index(bundle)
    out = []
    for i, row in df.iterrows():
        desc, charges = _cell(row, m["fda_desc"]), _cell(row, m["fda_charges"])
        subs = extract_substances(f"{desc} {charges}", alias) or [None]
        for sub in subs:
            out.append({
                "source": "fda", "value": None, "unit": None, "event_id": f"{_cell(row, m['fda_fei'])}#{i}", "_date": row[m["fda_date"]],
                "destination": "US", "origin_country": _cell(row, m["fda_country"]), "product_text": desc,
                "is_rice": int(is_rice(desc)), "hazard_group": hazard_group(charges), "substance": sub,
                "action": "refused", "synthetic": int(synthetic),
            })
    return _finish(out, "mdy")


def _finish(rows, order: str = "dmy") -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=EVENT_COLS)
    df = pd.DataFrame(rows)
    df["event_date"] = _iso(df.pop("_date"), order)
    return df[EVENT_COLS]


def load_reference(ref_dir: str):
    counts = pd.read_csv(os.path.join(ref_dir, "rasff_india_rice_gov.csv"))
    gap = pd.read_csv(os.path.join(ref_dir, "limits_gap.csv"))
    return counts, gap


def inspect(path: str) -> str:
    df = read_table(path)
    m = detect_mapping(df, list(SYNONYMS))
    lines = [f"{path}: {len(df)} rows; columns: {list(df.columns)}", "detected mapping:"]
    lines += [f"  {k:16} -> {v}" for k, v in m.items() if v]
    return "\n".join(lines)

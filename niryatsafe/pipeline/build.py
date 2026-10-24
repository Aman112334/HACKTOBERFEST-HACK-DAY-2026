"""Build the SQLite store and signals.json from reference tables plus any raw RASFF / FDA exports."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date

import pandas as pd

from .ingest import load_fda, load_rasff, load_reference, sha256_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(ROOT, "data", "reference")
DEFAULT_DB = os.path.join(ROOT, "data", "niryatsafe.db")
DEFAULT_SIGNALS = os.path.join(ROOT, "rules", "compiled", "signals.json")

REF_LABEL = "Government of India, Lok Sabha USQ 2057 (11 Mar 2025): EU RASFF detections in Indian rice, 2015 to Mar 2025"


def _is_synthetic(path: str) -> bool:
    return "synthetic" in os.path.basename(path).lower() or os.sep + "fixtures" + os.sep in path


def india_rice_eu(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events
    m = (events.destination == "EU") & (events.is_rice == 1) & events.origin_country.str.contains("india", case=False, na=False)
    return events[m]


def compute_signals(counts_ref: pd.DataFrame, gap: pd.DataFrame, events: pd.DataFrame, sources: list,
                    as_of: str, window: int = 5) -> dict:
    by: dict = {}
    for r in counts_ref.itertuples():
        by.setdefault(r.analyte, {})
        by[r.analyte][int(r.year)] = by[r.analyte].get(int(r.year), 0) + int(r.count)
    ref_years = sorted(int(y) for y in counts_ref.year.unique())
    hazards: dict = {}
    raw = india_rice_eu(events)
    raw_sub = raw[raw.substance.notna()] if not raw.empty else raw
    raw_years = []
    if not raw_sub.empty:
        yr = pd.to_datetime(raw_sub.event_date, errors="coerce").dt.year.dropna().astype(int)
        raw_years = sorted(set(yr))
        covered = set(range(min(raw_years), max(raw_years) + 1))
        for a in by:  # raw data replaces the reference for the years it covers (same underlying RASFF records)
            for y in list(by[a]):
                if y in covered:
                    del by[a][y]
        for sub, y in zip(raw_sub.substance, yr):
            by.setdefault(sub, {})
            by[sub][int(y)] = by[sub].get(int(y), 0) + 1
    if not raw.empty:
        for g, n in raw.hazard_group.value_counts().items():
            hazards[g] = int(n)
    all_years = sorted(set(ref_years) | set(raw_years))
    last = max(all_years) if all_years else int(as_of[:4])
    recent_years = list(range(last - window + 1, last + 1))
    out = {}
    for a, ys in sorted(by.items()):
        out[a] = {"total": int(sum(ys.values())), "recent": int(sum(v for y, v in ys.items() if y in recent_years)),
                  "by_year": {str(y): int(v) for y, v in sorted(ys.items())}}
    sig = {
        "built_on": as_of,
        "demo": any(s.get("synthetic") for s in sources),
        "sources": sources,
        "years": all_years,
        "recent_span": [recent_years[0], recent_years[-1]],
        "by_analyte": out,
        "hazards": hazards,
        "gap": json.loads(gap.where(gap.notna(), None).to_json(orient="records")),
        "totals": {"notifications": int(sum(v["total"] for v in out.values())),
                   "first_year": all_years[0] if all_years else None, "last_year": last},
    }
    us = events[events.destination == "US"] if not events.empty else events
    if not us.empty:
        usr = us[(us.is_rice == 1) & us.origin_country.str.contains("india", case=False, na=False)]
        sig["us"] = {"refusals": int(len(us)), "india_rice": int(len(usr)),
                     "by_hazard": {k: int(v) for k, v in usr.hazard_group.value_counts().items()},
                     "synthetic": bool(us.synthetic.max())}
    return sig


def build(db_path=DEFAULT_DB, signals_path=DEFAULT_SIGNALS, rasff=(), fda=(), as_of=None, ref_dir=REF_DIR,
          bundle_path=None) -> dict:
    from niryatsafe.rulebook import compile_bundle

    as_of = as_of or date.today().isoformat()
    bundle = compile_bundle(signals_path=os.path.join(ROOT, "rules", "compiled", "_none_.json"))
    counts, gap = load_reference(ref_dir)
    sources = [{"id": "ls_2057_2025", "label": REF_LABEL, "kind": "reference", "rows": int(counts["count"].sum()),
                "first_year": int(counts.year.min()), "last_year": int(counts.year.max()), "synthetic": False}]
    frames = []
    for p in rasff:
        df = load_rasff(p, bundle, synthetic=_is_synthetic(p))
        frames.append(df)
        sources.append({"id": "rasff:" + os.path.basename(p), "label": os.path.basename(p), "kind": "rasff",
                        "rows": int(len(df)), "sha": sha256_file(p), "synthetic": _is_synthetic(p)})
    for p in fda:
        df = load_fda(p, bundle, synthetic=_is_synthetic(p))
        frames.append(df)
        sources.append({"id": "fda:" + os.path.basename(p), "label": os.path.basename(p), "kind": "fda",
                        "rows": int(len(df)), "sha": sha256_file(p), "synthetic": _is_synthetic(p)})
    events = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["source", "event_id", "event_date", "destination", "origin_country", "product_text", "is_rice",
                 "hazard_group", "substance", "value", "unit", "action", "synthetic"])
    sig = compute_signals(counts, gap, events, sources, as_of)

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    from niryatsafe.engine import norm
    from niryatsafe.rulebook import read_limits
    lim = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in read_limits()])
    lim["limit_mg_kg"] = lim.limit_mg_kg.astype(float)
    lim["key"] = lim.substance.map(norm)
    counts = counts.assign(key=counts.analyte.map(norm))
    events.to_sql("events", con, index=False)
    lim.to_sql("limits", con, index=False)
    counts.to_sql("reference_counts", con, index=False)
    gap.to_sql("limit_gap", con, index=False)
    pd.DataFrame(sources).to_sql("sources", con, index=False)
    con.executescript("""
        CREATE VIEW v_india_rice_eu AS
          SELECT * FROM events WHERE destination='EU' AND is_rice=1 AND lower(origin_country) LIKE '%india%';
        CREATE VIEW v_signal_by_year AS
          SELECT analyte, year, SUM(count) AS n FROM reference_counts GROUP BY analyte, year;
        CREATE VIEW v_limits_and_refusals AS
          SELECT l.product, l.substance, l.market, l.limit_mg_kg, l.source,
                 COALESCE((SELECT SUM(count) FROM reference_counts r WHERE r.key = l.key), 0) AS alerts_on_indian_rice
          FROM limits l WHERE l.market = 'EU';
        CREATE INDEX ix_events_sub ON events(substance, event_date);
    """)
    con.commit()
    con.close()

    os.makedirs(os.path.dirname(signals_path), exist_ok=True)
    with open(signals_path, "w", encoding="utf-8") as fh:
        json.dump(sig, fh, ensure_ascii=False, indent=1, sort_keys=True)
    if bundle_path is not False:
        from niryatsafe.rulebook import write_bundle
        write_bundle(signals_path=signals_path) if bundle_path is None else write_bundle(bundle_path, signals_path)
    return sig


def audit(bundle: dict) -> list:
    """Compare rulebook tiers against current signals; return human-readable suggestions."""
    sig = (bundle.get("signals") or {}).get("by_analyte", {})
    notes = []
    for aid, a in bundle["analytes"].items():
        rec = sig.get(aid, {}).get("recent", 0)
        tot = sig.get(aid, {}).get("total", 0)
        if a["tier"] == "must" and rec == 0 and not a.get("punjab_2025"):
            notes.append(f"{aid}: tier 'must' but no notification in the recent window, consider 'should'")
        if a["tier"] != "must" and a["kind"] == "pesticide" and rec >= 3:
            notes.append(f"{aid}: {rec} recent notifications but tier '{a['tier']}', consider promoting to 'must'")
        if a["tier"] == "must" and tot == 0:
            notes.append(f"{aid}: tier 'must' with no notification on record at all")
    for aid, v in sig.items():
        if aid not in bundle["analytes"] and v.get("recent", 0) >= 3:
            notes.append(f"{aid}: {v['recent']} recent notifications and no entry in the rulebook")
    return notes

"""Back-test: would NiryatSafe have flagged lots that were actually refused? (deck slides 5, 6 and 9)

Takes RASFF border rejections of Indian rice that carry a measured value, rebuilds each as a one-analyte lot, runs the real
engine, and counts how many were flagged (HOLD, or FIX FIRST because the value sat in the watch band).
Notifications without a measured value (live insects, labelling ...) cannot be tested by lab-value rules: they are counted apart."""
from __future__ import annotations

import statistics
import time

from niryatsafe.engine import evaluate, resolve

from .build import india_rice_eu

FLAG_KEYS = ("limit_exceeded", "limit_close", "verify_mrl")


def backtest(events, bundle: dict, as_of: str) -> dict:
    ev = india_rice_eu(events)
    ev = ev[ev.substance.notna()] if len(ev) else ev
    testable = ev[ev.value.notna() & ev.unit.notna()] if len(ev) else ev
    flagged, missed, times, by = 0, [], [], {}
    for r in testable.itertuples():
        lot = {"lot": {}, "results": [{"analyte": r.substance, "status": "value", "value": float(r.value), "unit": r.unit}], "as_of": as_of}
        t0 = time.perf_counter()
        out = evaluate(lot, bundle)
        times.append((time.perf_counter() - t0) * 1000)
        aid = resolve(r.substance, bundle)["id"]
        hit = any(f["key"] in FLAG_KEYS and f["analyte"] in (aid, r.substance) for f in out["findings"])
        s = by.setdefault(r.substance, {"tested": 0, "flagged": 0})
        s["tested"] += 1
        s["flagged"] += int(hit)
        flagged += int(hit)
        if not hit:
            missed.append({"event_id": r.event_id, "substance": r.substance, "value": r.value, "unit": r.unit})
    n = len(testable)
    return {
        "indian_rice_eu_events": int(len(events[events.destination == "EU"])) if len(events) else 0,
        "india_rice_with_substance": int(len(ev)), "with_measured_value": int(n), "flagged": flagged,
        "hit_rate": (flagged / n) if n else None, "missed": missed, "by_substance": by,
        "median_ms_per_verdict": round(statistics.median(times), 3) if times else None,
        "synthetic": bool(testable.synthetic.max()) if n else False,
    }


def render(res: dict) -> str:
    lines = ["NiryatSafe back-test on past refused lots",
             f"  Indian-rice notifications with a named substance : {res['india_rice_with_substance']}",
             f"  ...of which carry a measured value (testable)    : {res['with_measured_value']}"]
    if res["with_measured_value"]:
        lines += [f"  would have been flagged (HOLD or FIX FIRST)      : {res['flagged']}  ({res['hit_rate']:.0%})",
                  f"  median time from lab value to verdict            : {res['median_ms_per_verdict']} ms (Python engine)"]
        for sub, s in sorted(res["by_substance"].items(), key=lambda kv: -kv[1]["tested"]):
            lines.append(f"    {sub:24} {s['flagged']}/{s['tested']}")
        for m in res["missed"][:10]:
            lines.append(f"  MISSED: {m}")
    else:
        lines.append("  No notification carries a measured value: export the RASFF Window detail columns or add a Result column.")
    if res["synthetic"]:
        lines.append("  NOTE: this ran on SYNTHETIC fixtures. It proves the harness, not the product. Use a real RASFF export for the pilot scorecard.")
    return "\n".join(lines)

"""NiryatSafe rules engine.

Deterministic: no network, no clock, no randomness, no ML.  The same (lot, bundle, as_of) always yields
byte-identical output, and web/src/engine.js is a line-for-line port that is differential-tested against
this file (tests/test_parity.py + web/tests/parity.test.mjs).

Verdict logic
    HOLD       at least one `block` finding: a quantified result above a *legal* EU limit.
    FIX_FIRST  no block, but at least one `fix`: missing / unusable evidence, close-to-limit result,
               missing paper.  "Unknown" is never treated as "pass".
    SHIP       everything required is evidenced and compliant.
Only findings whose basis is `law` can ever be `block`.
"""
from __future__ import annotations

import json
import re

SEVERITY_RANK = {"block": 0, "fix": 1, "note": 2, "pass": 3}
GATE_RANK = {"farm": 0, "lab": 1, "papers": 2, "border": 3}
UNIT_FACTORS = {"mg/kg": 1.0, "ppm": 1.0, "ug/kg": 0.001, "ppb": 0.001}
FORMS = ("raw_white", "sella", "brown")
SAMPLING = ("third_party", "lab", "self")

# Every message key this engine can emit.  rulebook.py checks them against rulebook/i18n.json.
MESSAGE_KEYS = [
    "limit_exceeded", "limit_close", "limit_ok", "nd_ok", "loq_too_high", "loq_missing", "unit_unknown",
    "as_total_speciation", "as_total_ok", "verify_mrl", "required_missing_signal", "required_missing_sprayed",
    "required_missing_default", "covered_by_screen", "should_missing", "sprayed_note", "sprayed_note_gap",
    "sprayed_note_punjab", "sprayed_note_gap_punjab", "sprayed_note_nolimit", "sprayed_unknown",
    "lab_missing", "lab_accredited",
    "lab_not_accredited", "lab_accreditation_unknown", "lab_fresh", "lab_stale", "lab_date_missing",
    "lab_date_invalid", "lab_linked", "lab_unlinked", "lab_link_unknown", "sampling_ok", "sampling_self",
    "sampling_unknown", "screen_ok", "screen_missing", "doc_ok", "doc_missing", "doc_unconfirmed",
    "regime_checks", "mu_note", "no_blending", "market_not_covered", "market_partial",
]
ACTION_KEYS = ["hold", "retest", "lower_loq", "test", "lookup_test", "verify_mrl", "speciation",
               "get_report", "lab_fix_accredited", "lab_fix_date", "lab_fix_fresh", "lab_fix_linked",
               "lab_fix_sampling", "lab_fix_unit", "screen", "get_doc"]


# ----------------------------------------------------------------------------------------------
# small deterministic helpers (ported 1:1 to JS)
# ----------------------------------------------------------------------------------------------
def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def r12(x: float) -> float:
    return round(x, 12)


def round_half_up(x: float) -> int:
    import math
    return int(math.floor(x + 0.5))


def days_from_civil(y: int, m: int, d: int) -> int:
    y -= 1 if m <= 2 else 0
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def parse_date(s):
    if not isinstance(s, str):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if mo < 1 or mo > 12 or d < 1 or d > 31:
        return None
    return days_from_civil(y, mo, d)


def unit_key(u) -> str:
    return str(u or "").strip().lower().replace("\u00b5", "u").replace("\u03bc", "u").replace(" ", "")


def num_str(x) -> str:
    s = ("%.9f" % x).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _json_str(s: str) -> str:
    out = ['"']
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        u = data[i] | (data[i + 1] << 8)
        ch = chr(u)
        if u == 0x22:
            out.append('\\"')
        elif u == 0x5C:
            out.append("\\\\")
        elif 0x20 <= u < 0x7F:
            out.append(ch)
        else:
            out.append("\\u%04x" % u)
    out.append('"')
    return "".join(out)


def canon(v) -> str:
    """Canonical JSON: sorted keys, no spaces, ASCII-only, fixed-point numbers. Identical in JS."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return num_str(v)
    if isinstance(v, str):
        return _json_str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(canon(x) for x in v) + "]"
    keys = sorted(v.keys())
    return "{" + ",".join(_json_str(k) + ":" + canon(v[k]) for k in keys) + "}"


def cyrb53(s: str) -> int:
    M = 0xFFFFFFFF

    def imul(a, b):
        return ((a & M) * (b & M)) & M

    h1, h2 = 0xDEADBEEF, 0x41C6CE57
    data = s.encode("utf-16-le")
    for i in range(0, len(data), 2):
        ch = data[i] | (data[i + 1] << 8)
        h1 = imul(h1 ^ ch, 2654435761)
        h2 = imul(h2 ^ ch, 1597334677)
    h1 = imul(h1 ^ (h1 >> 16), 2246822507)
    h1 ^= imul(h2 ^ (h2 >> 13), 3266489909)
    h2 = imul(h2 ^ (h2 >> 16), 2246822507)
    h2 ^= imul(h1 ^ (h1 >> 13), 3266489909)
    return 4294967296 * (2097151 & (h2 & M)) + (h1 & M)


def to_base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = ""
    while n > 0:
        out = digits[n % 36] + out
        n //= 36
    return out


def memo_id(text: str) -> str:
    s = to_base36(cyrb53(text)).upper().rjust(11, "0")[-8:]
    return "NS-" + s[:4] + "-" + s[4:]


# ----------------------------------------------------------------------------------------------
# bundle indexes and market-keyed lookups
# ----------------------------------------------------------------------------------------------
def build_index(bundle: dict) -> dict:
    alias = {}
    for aid, a in bundle["analytes"].items():
        for name in [aid, a["names"]["en"]] + list(a.get("aliases", [])):
            alias.setdefault(norm(name), aid)
    return {"alias": alias}


def get_index(bundle: dict) -> dict:
    idx = bundle.get("_index")
    if idx is None:
        idx = build_index(bundle)
        bundle["_index"] = idx
    return idx


def resolve(name, bundle) -> dict:
    k = norm(name)
    aid = get_index(bundle)["alias"].get(k)
    if aid is not None:
        return {"kind": "analyte", "id": aid, "label": bundle["analytes"][aid]["names"]["en"]}
    return {"kind": "unknown", "id": "unk:" + k, "label": str(name).strip()}


def market_of(dest, bundle):
    """EU member-state code (or the market code itself) -> market; empty -> default market; anything else -> None."""
    if not dest:
        return bundle["meta"]["default_market"]
    if dest in bundle["markets"]:
        return dest
    for code, m in bundle["markets"].items():
        if dest in m["countries"]:
            return code
    return None


def limit_for(defn, market, form):
    lim = ((defn or {}).get("limits") or {}).get(market)
    if not lim:
        return None
    if "by_form" in lim and form in lim["by_form"]:
        return lim["by_form"][form]
    return lim.get("limit")


def src_of(defn, market, default_source):
    lim = ((defn or {}).get("limits") or {}).get(market)
    srcs = lim.get("sources") if lim else None
    return list(srcs) if srcs else [default_source]


def india_of(defn):
    lim = ((defn or {}).get("limits") or {}).get("IN")
    return (lim.get("limit") if lim else None), (list(lim.get("sources", [])) if lim else [])


def risk_level(bundle, aid):
    """Risk flag from recent border-alert counts (presentation only: it never changes a verdict)."""
    n = int((((bundle.get("signals") or {}).get("by_analyte") or {}).get(aid) or {}).get("recent", 0))
    p = bundle["meta"]["policy"]
    if n >= p["risk_high"]:
        return "high"
    if n >= p["risk_med"]:
        return "med"
    return "low" if n >= 1 else None


# ----------------------------------------------------------------------------------------------
# input normalisation
# ----------------------------------------------------------------------------------------------
def _tri(v):
    return v if v is True or v is False else None


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def normalize_input(raw: dict) -> dict:
    raw = raw or {}
    lot = raw.get("lot") or {}
    lab = raw.get("lab") or {}
    form = lot.get("form")
    results = []
    for r in raw.get("results") or []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("analyte") or "").strip()
        if not name:
            continue
        status = r.get("status")
        if status == "nd":
            results.append({"analyte": name, "status": "nd", "value": None,
                            "unit": unit_key(r.get("unit")) or None, "loq": _num(r.get("loq"))})
        elif status == "value":
            v = _num(r.get("value"))
            if v is None or v < 0:
                continue
            results.append({"analyte": name, "status": "value", "value": v,
                            "unit": unit_key(r.get("unit")) or None, "loq": _num(r.get("loq"))})
    sprays = []
    for s in raw.get("sprays") or []:
        s = str(s or "").strip()
        if s and s not in sprays:
            sprays.append(s)
    docs = {}
    for k, v in (raw.get("docs") or {}).items():
        docs[str(k)] = _tri(v)
    sampling = lab.get("sampling")
    return {
        "lot": {
            "form": form if form in FORMS else "raw_white",
            "dest": str(lot.get("dest") or "").strip().upper(),
            "ship_date": lot.get("ship_date") if parse_date(lot.get("ship_date")) is not None else None,
            "origin": str(lot.get("origin") or "").strip().lower(),
            "lot_id": str(lot.get("lot_id") or "").strip(),
        },
        "lab": {
            "accredited": _tri(lab.get("accredited")),
            "report_date": lab.get("report_date") if parse_date(lab.get("report_date")) is not None else None,
            "linked": _tri(lab.get("linked")),
            "sampling": sampling if sampling in SAMPLING else None,
            "screen": _tri(lab.get("screen")),
        },
        "results": results,
        "sprays": sprays,
        "docs": docs,
        "as_of": raw.get("as_of") if parse_date(raw.get("as_of")) is not None else None,
    }


# ----------------------------------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------------------------------
def _canon_value(value, unit, target_unit):
    """Return value in the analyte's canonical unit, or None if the unit is not understood."""
    f = UNIT_FACTORS.get(unit if unit else ("mg/kg" if target_unit == "mg/kg" else "ug/kg"))
    if f is None:
        return None
    mgkg = value * f
    return r12(mgkg * 1000.0) if target_unit == "ug/kg" else r12(mgkg)


def _pseudo(label: str) -> dict:
    return {"kind": "pesticide", "unit": "mg/kg", "tier": "watch", "names": {"en": label}, "limits": {}, "pseudo": True}


def _ulabel(defn) -> str:
    return "\u00b5g/kg" if (defn or {}).get("unit") == "ug/kg" else "mg/kg"


def _finalize(findings, inp, bundle):
    policy = bundle["meta"]["policy"]
    findings.sort(key=lambda f: (SEVERITY_RANK[f["severity"]], -f["priority"], GATE_RANK[f["gate"]], f["id"]))
    counts = {"block": 0, "fix": 0, "note": 0, "pass": 0}
    for f in findings:
        counts[f["severity"]] += 1
    verdict = "HOLD" if counts["block"] else ("FIX_FIRST" if counts["fix"] else "SHIP")
    gates = {}
    for g in GATE_RANK:
        gs = [f for f in findings if f["gate"] == g]
        if any(f["severity"] == "block" for f in gs):
            gates[g] = "block"
        elif any(f["severity"] == "fix" for f in gs):
            gates[g] = "fix"
        elif any(f["severity"] == "pass" for f in gs):
            gates[g] = "pass"
        elif gs:
            gates[g] = "info"
        else:
            gates[g] = "idle"
    bhash = bundle["meta"].get("hash", "")
    rb_age = max(0, parse_date(inp["as_of"]) - parse_date(bundle["meta"]["verified_on"]))
    return {
        "verdict": verdict, "counts": counts, "steps": counts["block"] + counts["fix"], "gates": gates,
        "findings": findings, "memo_id": memo_id(canon(inp) + "|" + bhash), "as_of": inp["as_of"], "input": inp,
        "rulebook": {"id": bundle["meta"]["id"], "version": bundle["meta"]["version"], "hash": bhash,
                     "verified_on": bundle["meta"]["verified_on"], "age_days": rb_age,
                     "stale": rb_age > policy["stale_after_days"]},
    }


def evaluate(raw_input: dict, bundle: dict) -> dict:
    inp = normalize_input(raw_input)
    if inp["as_of"] is None:
        raise ValueError("as_of (YYYY-MM-DD) is required: the engine never reads the clock")
    policy = bundle["meta"]["policy"]
    watch = policy["watch_fraction"]
    mu = policy["mu_default"]
    form = inp["lot"]["form"]
    signals = (bundle.get("signals") or {}).get("by_analyte", {})
    findings = []

    def add(fid, gate, sev, basis, key, params=None, sources=None, analyte=None, action=None, priority=0):
        findings.append({
            "id": fid, "gate": gate, "severity": sev, "basis": basis, "key": key,
            "analyte": analyte, "params": params or {}, "sources": sources or [],
            "action": action, "priority": priority,
        })

    def recent(aid):
        return int((signals.get(aid) or {}).get("recent", 0))

    market = market_of(inp["lot"]["dest"], bundle)
    if market is None:
        add("market.coverage", "border", "fix", "practice", "market_not_covered", {"dest": inp["lot"]["dest"]})
        return _finalize(findings, inp, bundle)
    mk = bundle["markets"][market]
    dl, dsrc = mk["default_limit"], mk["default_source"]

    # ---- resolve and de-duplicate result rows (worst case wins) ---------------------------------
    rows = {}
    order = []
    for r in inp["results"]:
        res = resolve(r["analyte"], bundle)
        key = res["id"]
        defn = bundle["analytes"][key] if res["kind"] == "analyte" else None
        target = defn["unit"] if defn else "mg/kg"
        if r["status"] == "value":
            cv = _canon_value(r["value"], r["unit"], target)
            rank = (1, cv if cv is not None else 0.0)
        else:
            cv = None
            lq = _canon_value(r["loq"], r["unit"], target) if r["loq"] is not None else None
            rank = (0, lq if lq is not None else 0.0)
        entry = {"res": res, "row": r, "cv": cv, "rank": rank, "target": target}
        if key not in rows:
            rows[key] = entry
            order.append(key)
        elif entry["rank"] > rows[key]["rank"]:
            rows[key] = entry

    has_results = len(order) > 0

    # ---- per-result limit checks ------------------------------------------------------------------
    for key in order:
        e = rows[key]
        res, r, target = e["res"], e["row"], e["target"]
        defn = bundle["analytes"][key] if res["kind"] == "analyte" else _pseudo(res["label"])
        label = defn["names"]["en"]
        unit_label = _ulabel(defn)
        fid = "result." + key
        pr = recent(key)
        subj = key if res["kind"] == "analyte" else label
        limit = limit_for(defn, market, form)
        known = limit is not None
        L = limit if known else dl
        india, india_src = india_of(defn)
        srcs = src_of(defn, market, dsrc) if known else [dsrc]
        if known and india is not None:
            for s in india_src:
                if s not in srcs:
                    srcs.append(s)
        unit_ok = UNIT_FACTORS.get(r["unit"] if r["unit"] else ("mg/kg" if target == "mg/kg" else "ug/kg")) is not None
        if not unit_ok:
            add(fid, "lab", "fix", "practice", "unit_unknown", {"analyte": label, "unit": r["unit"]}, [], subj,
                {"kind": "lab_fix", "params": {"what": "unit"}}, pr)
            continue

        # total arsenic is only a screen for the (regulated) inorganic fraction
        if defn.get("screen_for"):
            if "arsenic_inorganic" in rows:
                continue
            if r["status"] == "value":
                v = e["cv"]
                if v > L:
                    add(fid, "lab", "fix", "guidance", "as_total_speciation",
                        {"analyte": label, "value": v, "limit": L, "unit": unit_label}, srcs, subj,
                        {"kind": "speciation", "params": {"limit": L, "unit": unit_label}}, pr)
                else:
                    add(fid, "lab", "pass", "law", "as_total_ok",
                        {"analyte": label, "value": v, "limit": L, "unit": unit_label}, srcs, subj)
                continue

        if r["status"] == "value":
            v = e["cv"]
            if known and v > L:
                add(fid, "lab", "block", "law", "limit_exceeded",
                    {"analyte": label, "value": v, "limit": L, "unit": unit_label,
                     "ratio": round_half_up(v / L * 10) / 10.0,
                     "within_u": r12(v * (1 - mu)) <= L,
                     "india_limit": india, "india_ok": (v <= india) if india is not None else None},
                    srcs, subj, {"kind": "hold", "params": {}}, pr)
            elif known and v >= watch * L:
                add(fid, "lab", "fix", "practice", "limit_close",
                    {"analyte": label, "value": v, "limit": L, "unit": unit_label,
                     "pct": round_half_up(v / L * 100)}, srcs, subj,
                    {"kind": "retest", "params": {"analyte": label}}, pr)
            elif (not known) and v > L:
                add(fid, "lab", "fix", "law", "verify_mrl",
                    {"analyte": label, "value": v, "limit": L, "unit": unit_label, "india_limit": india},
                    [dsrc], subj, {"kind": "verify_mrl", "params": {"analyte": label}}, pr)
            else:
                add(fid, "lab", "pass", "law", "limit_ok",
                    {"analyte": label, "value": v, "limit": L, "unit": unit_label}, srcs, subj)
        else:
            if r["loq"] is None:
                add(fid, "lab", "fix", "guidance", "loq_missing", {"analyte": label, "limit": L, "unit": unit_label},
                    ["sante_11312"], subj, {"kind": "lower_loq", "params": {"analyte": label, "limit": L, "unit": unit_label}}, pr)
            else:
                q = _canon_value(r["loq"], r["unit"], target)
                if q > L:
                    add(fid, "lab", "fix", "guidance", "loq_too_high",
                        {"analyte": label, "loq": q, "limit": L, "unit": unit_label}, ["sante_11312"], subj,
                        {"kind": "lower_loq", "params": {"analyte": label, "limit": L, "unit": unit_label}}, pr)
                else:
                    add(fid, "lab", "pass", "law", "nd_ok",
                        {"analyte": label, "loq": q, "limit": L, "unit": unit_label}, srcs, subj)

    # ---- required evidence: must-tier analytes + anything sprayed ----------------------------------
    required = []  # (id, label, reason)
    for aid, a in bundle["analytes"].items():
        if a["tier"] == "must":
            required.append((aid, a["names"]["en"], "signal"))
    sprayed_res = []
    for name in inp["sprays"]:
        res = resolve(name, bundle)
        sprayed_res.append(res)
        if not any(x[0] == res["id"] for x in required):
            required.append((res["id"], res["label"], "sprayed"))
        else:
            required = [(x[0], x[1], "sprayed" if x[0] == res["id"] else x[2]) for x in required]
    screen = inp["lab"]["screen"] is True
    for rid, label, reason in required:
        if rid in rows:
            continue
        analyte_def = bundle["analytes"].get(rid)
        lim = limit_for(analyte_def, market, form) if analyte_def else None
        L = lim if lim is not None else dl
        fid = "required." + rid
        subj = rid if analyte_def else label
        if screen:
            add(fid, "lab", "pass", "guidance", "covered_by_screen", {"analyte": label}, ["reg_2019_1793"], subj)
        else:
            rkey = "required_missing_default" if lim is None else (
                "required_missing_sprayed" if reason == "sprayed" else "required_missing_signal")
            ul = _ulabel(analyte_def)
            add(fid, "lab", "fix", "law", rkey,
                {"analyte": label, "reason": reason, "recent": recent(rid), "limit": L, "unit": ul},
                src_of(analyte_def, market, dsrc), subj,
                {"kind": "test", "params": {"analyte": label, "limit": L, "unit": ul}},
                recent(rid) + (1000 if reason == "sprayed" else 0))

    # ---- should-tier analytes that were not reported: one aggregate note ---------------------------
    missing_names = []
    has_as = ("arsenic_inorganic" in rows) or ("arsenic_total" in rows)
    for aid, a in bundle["analytes"].items():
        if a["tier"] != "should" or aid in rows:
            continue
        if aid in ("arsenic_inorganic", "arsenic_total") and has_as:
            continue
        if a["kind"] == "pesticide" and screen:
            continue
        if aid == "arsenic_total" and "arsenic_inorganic" not in rows and not has_as:
            continue  # listed once, under inorganic arsenic
        if any(x[0] == aid for x in required):
            continue
        missing_names.append(a["names"]["en"])
    if missing_names:
        add("lab.should_missing", "lab", "note", "law", "should_missing", {"list": ", ".join(missing_names)},
            ["reg_2023_915"])

    # ---- spray history (upstream prevention) ----------------------------------------------------
    for res in sprayed_res:
        fid = "farm.sprayed." + res["id"]
        if res["kind"] == "analyte":
            a = bundle["analytes"][res["id"]]
            lim = limit_for(a, market, form)
            india, _ = india_of(a)
            gap = round_half_up(india / lim) if (lim and india) else None
            punjab = bool(a.get("punjab_2025")) and inp["lot"]["origin"] == "punjab"
            if lim is None:
                skey = "sprayed_note_nolimit"
            elif gap is not None and gap >= 2:
                skey = "sprayed_note_gap_punjab" if punjab else "sprayed_note_gap"
            elif punjab:
                skey = "sprayed_note_punjab"
            else:
                skey = "sprayed_note"
            add(fid, "farm", "note", "guidance", skey,
                {"analyte": res["label"], "limit": lim if lim is not None else dl, "unit": _ulabel(a),
                 "india_limit": india, "gap": gap},
                ["punjab_2025", "ls_2057_2025"] if a.get("punjab_2025") else ["ls_2057_2025"], res["id"])
        else:
            add(fid, "farm", "fix", "law", "sprayed_unknown",
                {"analyte": res["label"], "limit": dl, "unit": "mg/kg"},
                [dsrc], res["label"], {"kind": "lookup_test", "params": {"analyte": res["label"]}})

    # ---- lab-level evidence quality ----------------------------------------------------------------
    lab = inp["lab"]
    reg = mk.get("regime")
    inc = reg["increased_checks"] if reg else None
    if not has_results and not screen:
        add("lab.report", "lab", "fix", "practice", "lab_missing", {"pct": inc["pct"] if inc else None},
            inc["sources"] if inc else [], None, {"kind": "get_report", "params": {}}, 10000)
    if has_results or screen:
        if lab["accredited"] is True:
            add("lab.accreditation", "lab", "pass", "practice", "lab_accredited", {}, ["sante_11312"])
        elif lab["accredited"] is False:
            add("lab.accreditation", "lab", "fix", "practice", "lab_not_accredited", {}, ["sante_11312"], None,
                {"kind": "lab_fix", "params": {"what": "accredited"}})
        else:
            add("lab.accreditation", "lab", "fix", "practice", "lab_accreditation_unknown", {}, ["sante_11312"],
                None, {"kind": "lab_fix", "params": {"what": "accredited"}})
        ref = parse_date(inp["lot"]["ship_date"]) if inp["lot"]["ship_date"] else parse_date(inp["as_of"])
        rep = parse_date(lab["report_date"]) if lab["report_date"] else None
        max_age = policy["report_max_age_days"]
        if rep is None:
            add("lab.freshness", "lab", "fix", "practice", "lab_date_missing", {}, [], None,
                {"kind": "lab_fix", "params": {"what": "date"}})
        elif ref - rep < 0:
            add("lab.freshness", "lab", "fix", "practice", "lab_date_invalid", {}, [], None,
                {"kind": "lab_fix", "params": {"what": "date"}})
        elif ref - rep > max_age:
            add("lab.freshness", "lab", "fix", "practice", "lab_stale", {"age": ref - rep, "max": max_age}, [],
                None, {"kind": "lab_fix", "params": {"what": "fresh"}})
        else:
            add("lab.freshness", "lab", "pass", "practice", "lab_fresh", {"age": ref - rep, "max": max_age}, [])
        if lab["linked"] is True:
            add("lab.link", "lab", "pass", "practice", "lab_linked", {}, [])
        elif lab["linked"] is False:
            add("lab.link", "lab", "fix", "practice", "lab_unlinked", {}, [], None,
                {"kind": "lab_fix", "params": {"what": "linked"}})
        else:
            add("lab.link", "lab", "fix", "practice", "lab_link_unknown", {}, [], None,
                {"kind": "lab_fix", "params": {"what": "linked"}})
        if lab["sampling"] in ("third_party", "lab"):
            add("lab.sampling", "lab", "pass", "guidance", "sampling_ok", {}, ["sante_11312"])
        elif lab["sampling"] == "self":
            add("lab.sampling", "lab", "fix", "guidance", "sampling_self", {}, ["sante_11312"], None,
                {"kind": "lab_fix", "params": {"what": "sampling"}})
        else:
            add("lab.sampling", "lab", "fix", "guidance", "sampling_unknown", {}, ["sante_11312"], None,
                {"kind": "lab_fix", "params": {"what": "sampling"}})
        if screen:
            add("lab.screen", "lab", "pass", "law", "screen_ok", {}, ["reg_2019_1793"])
        else:
            add("lab.screen", "lab", "fix", "law", "screen_missing", {}, ["reg_2019_1793"], None,
                {"kind": "screen", "params": {}})

    # ---- papers -----------------------------------------------------------------------------------
    docs = mk.get("docs")
    for d in docs or []:
        val = inp["docs"].get(d["id"])
        fid = "doc." + d["id"]
        if val is True:
            add(fid, "papers", "pass", d["basis"], "doc_ok", {"doc": d["id"]}, d["sources"])
        else:
            sev = d["missing"]
            key = "doc_missing" if val is False else "doc_unconfirmed"
            add(fid, "papers", sev, d["basis"], key, {"doc": d["id"]}, d["sources"], None,
                {"kind": "get_doc", "params": {"doc": d["id"]}} if sev == "fix" else None)

    # ---- border regime + context notes -------------------------------------------------------------
    if inc:
        add("border.regime", "border", "note", "law", "regime_checks", {"pct": inc["pct"]}, inc["sources"])
    if not docs or not inc:
        add("border.partial", "border", "note", "practice", "market_partial", {"market": market})
    if any(f["key"] == "limit_exceeded" and f["params"].get("within_u") for f in findings):
        add("border.mu", "border", "note", "guidance", "mu_note", {"mu": round_half_up(mu * 100)},
            ["sante_11312", "rasff_wi_2_2"])
    if any(f["severity"] == "block" for f in findings):
        add("border.no_blending", "border", "note", "law", "no_blending", {}, ["reg_2023_915"])

    return _finalize(findings, inp, bundle)


def load_bundle(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

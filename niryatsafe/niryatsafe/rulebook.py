"""Compile rules/ into ONE versioned rules pack (bundle.json) that both engines read.

    rules/limits.csv        one row per rule:  product,substance,market,limit_mg_kg,source  (+ form,basis,note)
    rules/rulebook.yaml     sources, analyte metadata (names, aliases, tiers), markets (countries, documents, border regime)
    rules/i18n.json         Hindi and English text for findings, actions, documents
    rules/ui.json           Hindi and English text for the app
    rules/samples.json      sample lots (Lot 402 and friends)

    python -m niryatsafe.rulebook build              # writes rules/compiled/bundle.json
    python -m niryatsafe.rulebook check              # validates only
    python -m niryatsafe.rulebook sign --by "Name"   # a maintainer signs off the current rules pack before a release
    python -m niryatsafe.rulebook release-check      # fails unless the current pack has been signed off
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from datetime import date

import yaml

from .engine import ACTION_KEYS, MESSAGE_KEYS, canon, norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RB = os.path.join(ROOT, "rules")
COMPILED = os.path.join(RB, "compiled", "bundle.json")
REVIEW = os.path.join(RB, "REVIEW.json")
REQUIRED_COLUMNS = ["product", "substance", "market", "limit_mg_kg", "source"]


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_limits(path: str = None) -> list:
    path = path or os.path.join(RB, "limits.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (rd.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing required column(s) {missing}; the contract is {REQUIRED_COLUMNS}")
        return [dict(r, _line=i + 2) for i, r in enumerate(rd)]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def compile_bundle(signals_path: str | None = None, limits_path: str | None = None) -> dict:
    with open(os.path.join(RB, "rulebook.yaml"), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    i18n = _read_json(os.path.join(RB, "i18n.json"))
    samples = _read_json(os.path.join(RB, "samples.json"), [])
    ui = _read_json(os.path.join(RB, "ui.json"), {})
    signals = _read_json(signals_path or os.path.join(RB, "compiled", "signals.json"), {})

    analytes = {}
    for aid, a in raw["analytes"].items():
        a = dict(a)
        a["id"] = aid
        a.setdefault("aliases", [])
        a["limits"] = {}
        analytes[aid] = a
    alias = {}
    for aid, a in analytes.items():
        for name in [aid, a["names"]["en"]] + list(a["aliases"]):
            alias.setdefault(norm(name), aid)

    problems, seen = [], set()
    for r in read_limits(limits_path):
        where = f"limits.csv line {r['_line']}"
        if r["product"].strip() != "rice":
            problems.append(f"{where}: product must be 'rice' in v1 (got {r['product']!r})")
            continue
        market = r["market"].strip()
        if market != "IN" and market not in raw["markets"]:
            problems.append(f"{where}: unknown market {market!r} (add it under `markets:` in rulebook.yaml)")
            continue
        try:
            lim = float(r["limit_mg_kg"])
        except ValueError:
            problems.append(f"{where}: limit_mg_kg is not a number: {r['limit_mg_kg']!r}")
            continue
        if lim < 0:
            problems.append(f"{where}: negative limit")
        sources = [s.strip() for s in r["source"].split(";") if s.strip()]
        if not sources:
            problems.append(f"{where}: every rule needs a source")
        for s in sources:
            if s not in raw["sources"]:
                problems.append(f"{where}: unknown source id {s!r} (add it under `sources:`)")
        basis = (r.get("basis") or "law").strip() or "law"
        form = (r.get("form") or "").strip()
        if basis not in ("law", "guidance", "practice", "reported"):
            problems.append(f"{where}: basis must be law|guidance|practice|reported")
        if form and form not in ("raw_white", "sella", "brown"):
            problems.append(f"{where}: unknown form {form!r}")
        key = (norm(r["substance"]), market, form)
        if key in seen:
            problems.append(f"{where}: duplicate rule for {r['substance']} / {market} / {form or 'any form'}")
        seen.add(key)
        aid = alias.get(norm(r["substance"]))
        if aid is None:  # a substance we have no metadata for becomes a plain pesticide entry
            aid = _slug(r["substance"])
            nm = r["substance"].strip()
            nm = nm[:1].upper() + nm[1:]
            analytes[aid] = {"id": aid, "kind": "pesticide", "unit": "mg/kg", "tier": "watch", "names": {"en": nm, "hi": nm},
                             "aliases": [], "limits": {}, "auto": True}
            alias[norm(r["substance"])] = aid
        a = analytes[aid]
        val = round(lim * 1000.0, 9) if a["unit"] == "ug/kg" else lim
        blk = a["limits"].setdefault(market, {"sources": sources, "basis": basis})
        if form:
            blk.setdefault("by_form", {})[form] = val
        else:
            blk["limit"] = val
    for a in analytes.values():  # a "screen" analyte (total arsenic) shares the limits of the fraction it screens
        if a.get("screen_for"):
            a["limits"] = json.loads(json.dumps(analytes[a["screen_for"]]["limits"]))

    core = {"meta": raw["meta"], "sources": raw["sources"], "analytes": analytes, "markets": raw["markets"],
            "countries": raw["countries"]}
    digest = hashlib.sha256(canon(core).encode("utf-8")).hexdigest()[:12]
    core["meta"] = dict(core["meta"], hash=digest)
    bundle = dict(core)
    bundle["i18n"] = {lang: dict(i18n[lang], ui=ui.get(lang, {})) for lang in ("en", "hi")}
    bundle["samples"] = samples
    bundle["signals"] = signals
    problems += validate(bundle)
    if problems:
        raise ValueError("rules invalid:\n  - " + "\n  - ".join(problems))
    return bundle


def validate(b: dict) -> list:
    errs = []
    src = b["sources"]
    for aid, a in b["analytes"].items():
        if a.get("tier") not in ("must", "should", "watch"):
            errs.append(f"{aid}: bad tier")
        if a.get("unit") not in ("mg/kg", "ug/kg"):
            errs.append(f"{aid}: bad unit")
        for lang in ("en", "hi"):
            if not a["names"].get(lang):
                errs.append(f"{aid}: missing {lang} name")
        if a["tier"] != "watch" and "EU" not in a["limits"]:
            errs.append(f"{aid}: tier {a['tier']} needs an EU limit row in limits.csv")
    for code, m in b["markets"].items():
        for c in m["countries"]:
            if c not in b["countries"]:
                errs.append(f"market {code}: country {c} has no name")
        for d in m.get("docs", []):
            for s in d["sources"]:
                if s not in src:
                    errs.append(f"doc {d['id']}: unknown source {s}")
            for lang in ("en", "hi"):
                if d["id"] not in b["i18n"][lang]["docs"]:
                    errs.append(f"doc {d['id']}: no {lang} text")
        reg = m.get("regime")
        if reg:
            for s in reg["increased_checks"]["sources"]:
                if s not in src:
                    errs.append(f"regime: unknown source {s}")
    for lang in ("en", "hi"):
        m, a = b["i18n"][lang]["m"], b["i18n"][lang]["a"]
        errs += [f"i18n.{lang}.m missing {k}" for k in MESSAGE_KEYS if k not in m]
        errs += [f"i18n.{lang}.a missing {k}" for k in ACTION_KEYS if k not in a]
    for smp in b["samples"]:
        errs += [f"sample missing {k}" for k in ("id", "title", "input") if k not in smp]
    return errs


def write_bundle(path: str = COMPILED, signals_path: str | None = None) -> dict:
    b = compile_bundle(signals_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(b, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return b


def resolve_sample(sample: dict, as_of: str) -> dict:
    """Turn relative dates (+18d / -6d) in a sample into ISO dates relative to as_of."""
    from datetime import timedelta

    base = date.fromisoformat(as_of)

    def rel(v):
        if isinstance(v, str) and v[:1] in "+-" and v.endswith("d"):
            return (base + timedelta(days=int(v[:-1]))).isoformat()
        return v

    inp = json.loads(json.dumps(sample["input"]))
    inp["lot"]["ship_date"] = rel(inp["lot"].get("ship_date"))
    if inp.get("lab"):
        inp["lab"]["report_date"] = rel(inp["lab"].get("report_date"))
    inp["as_of"] = as_of
    return inp


def sign(by: str, path: str = REVIEW) -> dict:
    b = compile_bundle()
    rec = {"reviewed_by": by, "reviewed_on": date.today().isoformat(), "version": b["meta"]["version"], "hash": b["meta"]["hash"]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1)
    return rec


def release_check(path: str = REVIEW) -> list:
    b = compile_bundle()
    rec = _read_json(path, {})
    out = []
    if not rec.get("reviewed_by"):
        out.append("rules/REVIEW.json has no reviewer: a maintainer must review the rules diff and run `make sign REVIEWER=\"Name\"`")
    elif rec.get("hash") != b["meta"]["hash"]:
        out.append(f"the rules changed since the last review (reviewed {rec.get('hash')}, now {b['meta']['hash']}): review again and re-sign")
    return out


def main(argv=None):
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else "build"
    if cmd == "check":
        compile_bundle()
        print("rules OK")
    elif cmd == "sign":
        by = argv[argv.index("--by") + 1] if "--by" in argv else ""
        if not by:
            sys.exit("usage: sign --by \"Maintainer Name\"")
        print("signed:", sign(by))
    elif cmd == "release-check":
        problems = release_check()
        print("\n".join(problems) if problems else "release check passed: rules pack is signed off")
        sys.exit(1 if problems else 0)
    else:
        b = write_bundle()
        print(f"wrote {COMPILED}  version={b['meta']['version']} hash={b['meta']['hash']} analytes={len(b['analytes'])} markets={list(b['markets'])}")


if __name__ == "__main__":
    main()

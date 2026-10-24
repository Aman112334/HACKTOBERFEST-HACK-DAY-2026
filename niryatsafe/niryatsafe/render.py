"""Server-side rendering of finding text from the shared i18n catalog (mirrors web/src/engine.js `renderFinding`)."""
from __future__ import annotations

import re


def fmt_num(x):
    if x is None:
        return "-"
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if x == 0:
            return "0"
        s = f"{x:.4g}"
        if "e" in s:
            s = f"{x:.6f}".rstrip("0").rstrip(".")
        return s
    return str(x)


def fill(template: str, params: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: fmt_num(params.get(m.group(1), "")), template)


def analyte_name(bundle, ident, lang):
    a = bundle["analytes"].get(ident)
    return a["names"][lang] if a else ident


def render_finding(f: dict, bundle: dict, lang: str = "en") -> dict:
    cat = bundle["i18n"][lang]
    p = dict(f["params"])
    if f.get("analyte") and f["analyte"] in bundle["analytes"]:
        p["analyte"] = analyte_name(bundle, f["analyte"], lang)
    if "doc" in p:
        d = cat["docs"].get(p["doc"], {})
        p["issuer"] = d.get("issuer", "")
        p["doc"] = d.get("name", p["doc"])
    text = fill(cat["m"][f["key"]], p)
    action = None
    if f.get("action"):
        ap = dict(f["action"]["params"])
        if "analyte" in ap and f.get("analyte") in bundle["analytes"]:
            ap["analyte"] = analyte_name(bundle, f["analyte"], lang)
        if "doc" in ap:
            d = cat["docs"].get(ap["doc"], {})
            ap["issuer"] = d.get("issuer", "")
            ap["doc"] = d.get("name", ap["doc"])
        kind = f["action"]["kind"]
        akey = "lab_fix_" + ap["what"] if kind == "lab_fix" else kind
        action = fill(cat["a"][akey], ap)
    return dict(f, text=text, action_text=action)


def render_result(result: dict, bundle: dict, lang: str = "en") -> dict:
    cat = bundle["i18n"][lang]
    out = dict(result)
    out["findings"] = [render_finding(f, bundle, lang) for f in result["findings"]]
    out["verdict_label"] = cat["verdict"][result["verdict"]]
    out["verdict_sub"] = cat["verdict_sub"][result["verdict"]]
    return out

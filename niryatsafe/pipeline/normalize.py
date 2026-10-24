"""Header mapping and hazard extraction. Deterministic text matching against the rulebook's own alias list: no ML, no LLM."""
from __future__ import annotations

import re

import pandas as pd


def canon_header(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


SYNONYMS = {
    # --- RASFF Window style exports
    "event_id": ["reference", "notificationreference", "ref", "notificationid", "number", "id"],
    "event_date": ["dateofcase", "date", "notificationdate", "validationdate", "datecase"],
    "ntype": ["notificationtype", "type", "notificationclassification"],
    "subject": ["subject", "title", "notificationsubject", "description"],
    "category": ["productcategory", "category", "productcat", "producttype"],
    "origin": ["countryoforigin", "origin", "origincountry", "originatingcountry"],
    "hazards": ["hazards", "hazard", "hazardsubstances", "substances", "hazardsubstance"],
    "hazard_category": ["hazardcategory", "hazardscategory", "hazardgroup"],
    "action": ["actiontaken", "action", "distributionstatus", "riskdecision"],
    "result": ["analyticalresult", "analyticalresults", "result", "measuredvalue", "level", "concentration", "hazardvalue"],
    # --- FDA import refusals (Data Dashboard CSV / API names)
    "fda_date": ["refusaldate", "refusedate", "dateofrefusal"],
    "fda_country": ["countryname", "manufacturercountry", "country", "manufacturercountryarea", "countrycode"],
    "fda_desc": ["productcodedescription", "productdescription", "importersproductdescription", "fdaproductdescription"],
    "fda_charges": ["refusalcharges", "charges", "refusalcharge", "chargecodes"],
    "fda_fei": ["feinumber", "fei", "manufacturerfei"],
    "fda_product_code": ["productcode"],
}

HAZARD_PATTERNS = [
    ("pesticide", r"pesticid|residue|mrl|tricyclazole|carbendazim|thiamethoxam|chlorpyrifos|imidacloprid|acephate|profenofos"),
    ("mycotoxin", r"aflatox|ochratox|mycotox|fumonisin|zearalenon|deoxynivalenol"),
    ("metal", r"arsenic|cadmium|\blead\b|mercury|heavy metal"),
    ("microbiological", r"salmonella|e\.? ?coli|listeria|bacillus|pathogen|microbio|mould|mold"),
    ("pest_infestation", r"insect|infest|weevil|beetle|filthy|mite|rodent|foreign (body|matter)"),
    ("labelling", r"label|no english|lacks (n/c|firm)|nutrit|list ingre|misbrand"),
    ("additive", r"additive|colou?r|sudan|sulphite|sulfite|preserv"),
]


def pick(df: pd.DataFrame, key: str):
    lookup = {canon_header(c): c for c in df.columns}
    for w in SYNONYMS[key]:
        if w in lookup:
            return lookup[w]
    return None


def detect_mapping(df: pd.DataFrame, keys) -> dict:
    return {k: pick(df, k) for k in keys}


def hazard_group(text: str, explicit: str | None = None) -> str:
    blob = f"{explicit or ''} {text or ''}".lower()
    for name, pat in HAZARD_PATTERNS:
        if re.search(pat, blob):
            return name
    return "other"


def build_alias_index(bundle: dict):
    """(alias text, analyte id) pairs, longest first. Every substance in limits.csv is an analyte, so one source of names."""
    pairs = []
    for aid, a in bundle["analytes"].items():
        for name in [aid.replace("_", " "), a["names"]["en"]] + list(a.get("aliases", [])):
            n = name.lower().strip()
            if len(n) >= 5 and not n[0].isdigit():
                pairs.append((n, aid))
    pairs.sort(key=lambda p: (-len(p[0]), p[0]))
    return pairs


def extract_substances(text: str, alias_pairs) -> list:
    t = (text or "").lower()
    found = []
    for alias, aid in alias_pairs:
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", t) and aid not in found:
            found.append(aid)
    return found


def is_rice(text: str) -> bool:
    return bool(re.search(r"\brice\b|basmati|paddy", (text or "").lower()))


VALUE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg\s*/\s*kg|[u\u00b5\u03bc]g\s*/\s*kg|ppm|ppb)", re.I)


def extract_value(text: str):
    """First 'number unit' in a text such as 'Tricyclazole (0.22 mg/kg)': returns (value, unit) or (None, None)."""
    m = VALUE_RE.search(text or "")
    if not m:
        return None, None
    unit = re.sub(r"\s+", "", m.group(2).lower()).replace("\u00b5", "u").replace("\u03bc", "u")
    return float(m.group(1).replace(",", ".")), unit

"""Parse a lab table pasted from a PDF / Excel / WhatsApp into engine result rows.

Understands:  tab, semicolon, comma or 2+ space separated columns;  `ND`, `N.D.`, `BQL`, `BDL`, `<LOQ`, `Not detected`, `<0.01`;
values like `0.012`, `0,012`, `0.012 ± 0.004`;  units mg/kg, ppm, ug/kg, µg/kg, ppb;  an optional LOQ column.
web/src/labparse.js is a port of this file and is tested against the same cases (tests/labparse_cases.json)."""
from __future__ import annotations

import re

from .engine import resolve

ND_WORDS = re.compile(r"^(nd|n\.?d\.?|bql|bdl|<\s*loq|<\s*lod|nil|absent|not\s*detected|not\s*detectable|below\s*loq|below\s*detection.*)$", re.I)
UNIT_RE = re.compile(r"(mg\s*/\s*kg|ppm|[uµμ]g\s*/\s*kg|ppb)", re.I)
NUM = r"[0-9]+(?:[.,][0-9]+)?"
HEADER_WORDS = ("parameter", "test", "analyte", "result", "unit", "loq", "mrl", "method", "sr", "s.no", "sl", "sample")


def _num(s: str):
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _split(line: str):
    if "\t" in line:
        parts = line.split("\t")
    elif "|" in line:
        parts = line.strip().strip("|").split("|")
    elif ";" in line:
        parts = line.split(";")
    elif re.search(r"\s{2,}", line.strip()):
        parts = re.split(r"\s{2,}", line.strip())
    elif line.count(",") >= 1 and not re.search(r"\d,\d", line):
        parts = line.split(",")
    else:
        m = re.match(r"^\s*([A-Za-z][A-Za-z0-9 ()+\-/.]*?)\s+((?:<\s*)?" + NUM + r"|nd|n\.?d\.?|bql|bdl|not\s*detected)\b(.*)$", line, re.I)
        parts = [m.group(1), m.group(2) + (m.group(3) or "")] if m else [line]
    return [p.strip() for p in parts if p.strip() != ""]


def _unit(text: str):
    m = UNIT_RE.search(text or "")
    if not m:
        return None
    u = re.sub(r"\s+", "", m.group(1).lower()).replace("µ", "u").replace("μ", "u")
    return u


def parse_line(line: str, bundle: dict):
    cells = _split(line)
    if len(cells) < 2:
        return None
    if re.sub(r"[^a-z.]", "", cells[0].lower()) in HEADER_WORDS or cells[0].lower().startswith(HEADER_WORDS[:1]):
        return None
    if all(re.sub(r"[^a-z.]", "", c.lower()) in HEADER_WORDS for c in cells[1:3] if c):
        return None
    name = re.sub(r"^\d+[.)]?\s+", "", cells[0]).strip()  # strip serial numbers like "3." or "3)"
    if not name or not re.search(r"[A-Za-z]", name):
        return None
    rest = [c for c in cells[1:]]
    unit = None
    for c in rest:
        unit = unit or _unit(c)
    status, value, loq = None, None, None
    for c in rest:
        cc = c.strip()
        low = cc.lower()
        m_lt = re.match(r"^<\s*(" + NUM + r")", cc)
        if ND_WORDS.match(cc.replace(" ", "") if low.startswith(("n.d", "nd", "bql", "bdl")) else cc) or low.startswith("not detected"):
            status = status or "nd"
            continue
        if m_lt:
            status = status or "nd"
            loq = loq if loq is not None else _num(m_lt.group(1))
            continue
        m_v = re.match(r"^(" + NUM + r")\s*(?:±.*|\+/-.*)?\s*(?:" + UNIT_RE.pattern + r")?\s*$", cc, re.I)
        if m_v:
            v = _num(m_v.group(1))
            if status is None and v is not None:
                status, value = "value", v
            elif v is not None and loq is None:
                loq = v  # a second bare number is the LOQ column
    if status is None:
        return None
    res = resolve(name, bundle)
    row = {"analyte": res["id"] if res["kind"] == "analyte" else name, "label": name, "matched": res["kind"] != "unknown",
           "status": status, "unit": unit, "loq": loq}
    if status == "value":
        row["value"] = value
    return row


def parse_table(text: str, bundle: dict, default_unit: str | None = None):
    rows, skipped = [], []
    for ln in (text or "").splitlines():
        if not ln.strip():
            continue
        r = parse_line(ln, bundle)
        if r is None:
            skipped.append(ln.strip())
        else:
            if r["unit"] is None:
                a = bundle["analytes"].get(r["analyte"])
                r["unit"] = default_unit or (a["unit"] if a else "mg/kg")
            rows.append(r)
    return {"rows": rows, "skipped": skipped}

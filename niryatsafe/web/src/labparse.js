// Port of niryatsafe/labparse.py: parse a lab table pasted from a PDF / Excel / WhatsApp into engine result rows.
import { resolve } from "./engine.js";

const ND_WORDS = /^(nd|n\.?d\.?|bql|bdl|<\s*loq|<\s*lod|nil|absent|not\s*detected|not\s*detectable|below\s*loq|below\s*detection.*)$/i;
const UNIT_SRC = "(mg\\s*/\\s*kg|ppm|[uµμ]g\\s*/\\s*kg|ppb)";
const UNIT_RE = new RegExp(UNIT_SRC, "i");
const NUM = "[0-9]+(?:[.,][0-9]+)?";
const HEADER_WORDS = ["parameter", "test", "analyte", "result", "unit", "loq", "mrl", "method", "sr", "s.no", "sl", "sample"];
const toNum = (s) => {
  const x = Number(String(s).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

function split(line) {
  let parts;
  if (line.includes("\t")) parts = line.split("\t");
  else if (line.includes("|")) parts = line.trim().replace(/^\||\|$/g, "").split("|");
  else if (line.includes(";")) parts = line.split(";");
  else if (/\s{2,}/.test(line.trim())) parts = line.trim().split(/\s{2,}/);
  else if ((line.match(/,/g) || []).length >= 1 && !/\d,\d/.test(line)) parts = line.split(",");
  else {
    const m = new RegExp("^\\s*([A-Za-z][A-Za-z0-9 ()+\\-/.]*?)\\s+((?:<\\s*)?" + NUM + "|nd|n\\.?d\\.?|bql|bdl|not\\s*detected)\\b(.*)$", "i").exec(line);
    parts = m ? [m[1], m[2] + (m[3] || "")] : [line];
  }
  return parts.map((p) => p.trim()).filter((p) => p !== "");
}
const unitOf = (text) => {
  const m = UNIT_RE.exec(text || "");
  return m ? m[1].toLowerCase().replace(/\s+/g, "").replace(/µ/g, "u").replace(/μ/g, "u") : null;
};

export function parseLine(line, bundle) {
  const cells = split(line);
  if (cells.length < 2) return null;
  const key0 = cells[0].toLowerCase().replace(/[^a-z.]/g, "");
  if (HEADER_WORDS.includes(key0) || cells[0].toLowerCase().startsWith("parameter")) return null;
  const head = cells.slice(1, 3).filter((c) => c);
  if (head.every((c) => HEADER_WORDS.includes(c.toLowerCase().replace(/[^a-z.]/g, "")))) return null;
  const name = cells[0].replace(/^\d+[.)]?\s+/, "").trim();
  if (!name || !/[A-Za-z]/.test(name)) return null;
  const rest = cells.slice(1);
  let unit = null;
  for (const c of rest) unit = unit || unitOf(c);
  let status = null, value = null, loq = null;
  const mV = new RegExp("^(" + NUM + ")\\s*(?:±.*|\\+/-.*)?\\s*(?:" + UNIT_SRC + ")?\\s*$", "i");
  for (const c of rest) {
    const cc = c.trim();
    const low = cc.toLowerCase();
    const mLt = new RegExp("^<\\s*(" + NUM + ")").exec(cc);
    const ndTest = ["n.d", "nd", "bql", "bdl"].some((p) => low.startsWith(p)) ? cc.replace(/ /g, "") : cc;
    if (ND_WORDS.test(ndTest) || low.startsWith("not detected")) { status = status || "nd"; continue; }
    if (mLt) { status = status || "nd"; if (loq === null) loq = toNum(mLt[1]); continue; }
    const m = mV.exec(cc);
    if (m) {
      const v = toNum(m[1]);
      if (status === null && v !== null) { status = "value"; value = v; }
      else if (v !== null && loq === null) loq = v;
    }
  }
  if (status === null) return null;
  const res = resolve(name, bundle);
  const row = { analyte: res.kind === "analyte" ? res.id : name, label: name, matched: res.kind !== "unknown", status, unit, loq };
  if (status === "value") row.value = value;
  return row;
}

export function parseTable(text, bundle, defaultUnit = null) {
  const rows = [], skipped = [];
  for (const ln of String(text || "").split(/\r?\n/)) {
    if (!ln.trim()) continue;
    const r = parseLine(ln, bundle);
    if (r === null) skipped.push(ln.trim());
    else {
      if (r.unit === null) {
        const a = bundle.analytes[r.analyte];
        r.unit = defaultUnit || (a ? a.unit : "mg/kg");
      }
      rows.push(r);
    }
  }
  return { rows, skipped };
}

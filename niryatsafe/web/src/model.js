import { evaluate, renderFinding, resolveSample, resolve } from "./engine.js";

export const DOC_IDS = ["iec", "rcac", "phyto", "coi", "invoice_pl", "ched_d", "labels"];
const EXTRA_ROWS = ["aflatoxin_b1", "aflatoxin_total", "ochratoxin_a", "arsenic_inorganic", "cadmium"];

export const blankRow = (key, unit) => ({ key, status: "nt", value: "", unit: unit === "ug/kg" ? "ug/kg" : "mg/kg", loq: "" });

export function defaultRows(bundle) {
  const sig = (bundle.signals && bundle.signals.by_analyte) || {};
  const must = Object.entries(bundle.analytes).filter(([, a]) => a.tier === "must")
    .sort((a, b) => ((sig[b[0]] || {}).total || 0) - ((sig[a[0]] || {}).total || 0) || (a[0] < b[0] ? -1 : 1));
  const rows = must.map(([id, a]) => blankRow(id, a.unit));
  for (const id of EXTRA_ROWS) if (bundle.analytes[id]) rows.push(blankRow(id, bundle.analytes[id].unit));
  return rows;
}

export const blankState = (bundle) => ({
  source: "",
  lot: { form: "raw_white", dest: "", ship_date: "", origin: "", lot_id: "" },
  lab: { accredited: null, report_date: "", linked: null, sampling: null, screen: null },
  rows: defaultRows(bundle),
  sprays: [],
  docs: Object.fromEntries(DOC_IDS.map((d) => [d, null])),
});

const numOrNull = (s) => {
  if (s === "" || s === null || s === undefined) return null;
  const x = Number(String(s).replace(",", "."));
  return Number.isFinite(x) ? x : null;
};

export function toInput(state, asOf) {
  return {
    lot: { ...state.lot, ship_date: state.lot.ship_date || null },
    lab: { ...state.lab, report_date: state.lab.report_date || null },
    results: state.rows.filter((r) => r.status !== "nt").map((r) => ({
      analyte: r.key, status: r.status, value: r.status === "value" ? numOrNull(r.value) : null, unit: r.unit, loq: numOrNull(r.loq),
    })),
    sprays: state.sprays,
    docs: state.docs,
    as_of: asOf,
  };
}

export function stateFromSample(bundle, sample, asOf) {
  const inp = resolveSample(sample, asOf);
  const st = blankState(bundle);
  st.lot = { form: inp.lot.form, dest: inp.lot.dest || "", ship_date: inp.lot.ship_date || "", origin: inp.lot.origin || "", lot_id: inp.lot.lot_id || "" };
  st.lab = { accredited: inp.lab.accredited ?? null, report_date: inp.lab.report_date || "", linked: inp.lab.linked ?? null, sampling: inp.lab.sampling ?? null, screen: inp.lab.screen ?? null };
  for (const r of inp.results) {
    const res = resolve(r.analyte, bundle);
    const key = res.kind === "analyte" ? res.id : r.analyte;
    let row = st.rows.find((x) => x.key === key);
    if (!row) { row = blankRow(key, res.kind === "analyte" ? bundle.analytes[key].unit : "mg/kg"); st.rows.push(row); }
    row.status = r.status;
    row.value = r.value === null || r.value === undefined ? "" : String(r.value);
    row.unit = r.unit === "ug/kg" || r.unit === "ppb" ? (r.unit === "ppb" ? "ppb" : "ug/kg") : r.unit || row.unit;
    row.loq = r.loq === null || r.loq === undefined ? "" : String(r.loq);
  }
  st.sprays = [...inp.sprays];
  st.docs = { ...st.docs, ...inp.docs };
  return st;
}

export function rowLabel(row, bundle, lang) {
  const a = bundle.analytes[row.key];
  return a ? a.names[lang] : row.key;
}

export function summaryText(result, bundle, lang, t) {
  const cat = bundle.i18n[lang];
  const todo = result.findings.filter((f) => f.severity === "block" || f.severity === "fix").slice(0, 5)
    .map((f) => "• " + (renderFinding(f, bundle, lang).actionText || renderFinding(f, bundle, lang).text));
  return [`${t("app_name")} — ${cat.verdict[result.verdict]}`, cat.verdict_sub[result.verdict], ...todo,
    `${t("memo_id")} ${result.memo_id} · ${t("rulebook")} ${result.rulebook.version}`].join("\n");
}

export { evaluate };

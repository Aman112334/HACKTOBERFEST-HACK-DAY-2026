import { useRef, useState } from "react";
import { cx } from "./ui.js";
import { marketOf, resolve, riskLevel } from "./engine.js";
import { parseTable } from "./labparse.js";
import { blankRow } from "./model.js";
import { LimitBars } from "./viz.jsx";

export const STATES = [
  ["punjab", "Punjab", "पंजाब"], ["haryana", "Haryana", "हरियाणा"], ["uttar pradesh", "Uttar Pradesh", "उत्तर प्रदेश"],
  ["uttarakhand", "Uttarakhand", "उत्तराखंड"], ["himachal pradesh", "Himachal Pradesh", "हिमाचल प्रदेश"],
  ["delhi", "Delhi", "दिल्ली"], ["jammu and kashmir", "Jammu & Kashmir", "जम्मू और कश्मीर"], ["other", "Other", "अन्य"],
];

/* ---------- controls ---------- */
export function Seg({ value, options, onChange, allowClear, label }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button type="button" key={String(o.v)} role="radio" aria-checked={value === o.v} className={cx(value === o.v && "on")}
          onClick={() => onChange(allowClear && value === o.v ? null : o.v)}>{o.label}</button>
      ))}
    </div>
  );
}
export function Tri({ value, onChange, t, label }) {
  return (
    <Seg value={value} onChange={onChange} label={label} allowClear
      options={[{ v: true, label: t("yes") }, { v: false, label: t("no") }, { v: null, label: t("unsure") }]} />
  );
}
export const Field = ({ label, hint, children, wide }) => (
  <label className={cx("field", wide && "wide")}>
    <span className="flabel">{label}</span>
    {children}
    {hint && <small className="fhint">{hint}</small>}
  </label>
);
const Row = ({ label, hint, children }) => (
  <div className="qrow">
    <div className="qtext"><span className="qlabel">{label}</span>{hint && <small>{hint}</small>}</div>
    {children}
  </div>
);

/* ---------- 01 lot ---------- */
export function LotForm({ st, setLot, bundle, lang, t }) {
  const countries = Object.entries(bundle.countries).sort((a, b) => (a[1][lang] < b[1][lang] ? -1 : 1));
  return (
    <div className="grid2">
      <Field label={t("f_product")}><input value={t("basmati")} readOnly className="ro" /></Field>
      <Field label={t("f_form")} hint={t("f_form_hint")}>
        <Seg value={st.lot.form} onChange={(v) => setLot({ form: v })} label={t("f_form")}
          options={[{ v: "raw_white", label: t("form_raw") }, { v: "sella", label: t("form_sella") }, { v: "brown", label: t("form_brown") }]} />
      </Field>
      <Field label={t("f_origin")}>
        <select value={st.lot.origin} onChange={(e) => setLot({ origin: e.target.value })}>
          <option value="">—</option>
          {STATES.map(([v, en, hi]) => <option key={v} value={v}>{lang === "hi" ? hi : en}</option>)}
        </select>
      </Field>
      <Field label={t("f_dest")}>
        <select value={st.lot.dest} onChange={(e) => setLot({ dest: e.target.value })}>
          <option value="">{t("dest_eu_any")}</option>
          {countries.map(([c, n]) => <option key={c} value={c}>{n[lang]}</option>)}
          <option value="OTHER">{t("dest_other")}</option>
        </select>
      </Field>
      <Field label={t("f_ship")}><input type="date" value={st.lot.ship_date} onChange={(e) => setLot({ ship_date: e.target.value })} /></Field>
      <Field label={t("f_lotid")}><input value={st.lot.lot_id} placeholder="402" onChange={(e) => setLot({ lot_id: e.target.value })} /></Field>
      <Field label={t("f_source")} hint={t("f_source_hint")} wide>
        <input value={st.source} placeholder={t("f_source_ph")} onChange={(e) => setLot({ source: e.target.value }, true)} />
      </Field>
    </div>
  );
}

/* ---------- 02 lab report ---------- */
function mergeParsed(rows, parsed) {
  const out = rows.map((r) => ({ ...r }));
  let added = 0;
  for (const p of parsed) {
    let row = out.find((r) => r.key === p.analyte);
    if (!row) { row = blankRow(p.analyte, "mg/kg"); out.push(row); added++; }
    row.status = p.status;
    row.value = p.status === "value" && p.value !== null && p.value !== undefined ? String(p.value) : "";
    row.unit = p.unit || row.unit;
    row.loq = p.loq === null || p.loq === undefined ? "" : String(p.loq);
  }
  return { rows: out, added };
}

function LabRow({ row, label, finding, findingText, onChange, onRemove, removable, risk, alerts, t }) {
  const set = (patch) => onChange({ ...row, ...patch });
  const p = finding ? finding.params : null;
  const showBars = p && p.limit !== undefined && row.status !== "nt" && finding.key !== "unit_unknown";
  return (
    <li className={cx("lrow", row.status !== "nt" && finding && "sev-" + finding.severity)}>
      <div className="lrow-head">
        <span className="lname">{label}</span>
        {risk && <span className={"risk r-" + risk} title={t("risk_help", { n: alerts })}>{t("risk_" + risk)}</span>}
        <Seg value={row.status} onChange={(v) => set({ status: v })} label={label}
          options={[{ v: "nt", label: t("st_nt") }, { v: "nd", label: t("st_nd") }, { v: "value", label: t("st_value") }]} />
        {removable && <button type="button" className="x" aria-label={t("remove")} onClick={onRemove}>×</button>}
      </div>
      {row.status !== "nt" && (
        <div className="lrow-fields">
          {row.status === "value" && (
            <input inputMode="decimal" className="num" aria-label={t("value")} placeholder={t("value")} value={row.value}
              onChange={(e) => set({ value: e.target.value })} />
          )}
          <select aria-label={t("unit")} value={row.unit} onChange={(e) => set({ unit: e.target.value })}>
            <option value="mg/kg">mg/kg</option><option value="ug/kg">µg/kg</option><option value="ppm">ppm</option><option value="ppb">ppb</option>
          </select>
          <input inputMode="decimal" className="num" aria-label="LOQ" placeholder="LOQ" value={row.loq} onChange={(e) => set({ loq: e.target.value })} />
        </div>
      )}
      {showBars && (
        <>
          <LimitBars limit={p.limit} value={p.value} loq={p.value === undefined ? p.loq : undefined} unit={p.unit}
            indiaLimit={p.india_limit} state={finding.severity === "block" ? "block" : finding.severity === "fix" ? "fix" : "pass"} t={t} />
          <p className={cx("rowtext", finding.severity)}>{findingText}</p>
        </>
      )}
    </li>
  );
}

export function LabForm({ st, setSt, bundle, lang, t, result, renderOne }) {
  const [paste, setPaste] = useState("");
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [add, setAdd] = useState("");
  const fileRef = useRef(null);
  const setLab = (patch) => setSt((s) => ({ ...s, lab: { ...s.lab, ...patch } }));
  const byId = {};
  for (const f of result.findings) byId[f.id] = f;
  const sig = (bundle.signals && bundle.signals.by_analyte) || {};
  const defaultKeys = new Set(["tricyclazole", "thiamethoxam", "chlorpyrifos", "imidacloprid", "carbendazim", "propiconazole", "buprofezin",
    "profenofos", "acephate", "hexaconazole", "aflatoxin_b1", "aflatoxin_total", "ochratoxin_a", "arsenic_inorganic", "cadmium"]);

  const apply = (text) => {
    const out = parseTable(text, bundle);
    if (!out.rows.length) { setNote(t("paste_none")); return; }
    setSt((s) => ({ ...s, rows: mergeParsed(s.rows, out.rows).rows }));
    const unknown = out.rows.filter((r) => !r.matched).length;
    setNote(t("paste_ok", { n: out.rows.length, skipped: out.skipped.length }) + (unknown ? " " + t("paste_unknown", { n: unknown }) : ""));
  };
  const onFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => apply(String(rd.result || ""));
    rd.readAsText(f);
    e.target.value = "";
  };
  const markND = () => setSt((s) => ({
    ...s, rows: s.rows.map((r) => (r.status === "nt" && bundle.analytes[r.key] && bundle.analytes[r.key].kind === "pesticide"
      ? { ...r, status: "nd", unit: "mg/kg", loq: "0.01" } : r)),
  }));
  const addRow = () => {
    const name = add.trim();
    if (!name) return;
    const res = resolve(name, bundle);
    const key = res.kind === "analyte" ? res.id : name;
    setSt((s) => (s.rows.some((r) => r.key === key) ? s : { ...s, rows: [...s.rows, blankRow(key, res.kind === "analyte" ? bundle.analytes[key].unit : "mg/kg")] }));
    setAdd("");
  };
  const names = Object.values(bundle.analytes).map((a) => a.names.en);

  return (
    <>
      <div className="qgroup">
        <Row label={t("lab_accred")} hint={t("lab_accred_h")}><Tri value={st.lab.accredited} onChange={(v) => setLab({ accredited: v })} t={t} label={t("lab_accred")} /></Row>
        <Row label={t("lab_date")}><input type="date" value={st.lab.report_date} onChange={(e) => setLab({ report_date: e.target.value })} /></Row>
        <Row label={t("lab_linked")} hint={t("lab_linked_h")}><Tri value={st.lab.linked} onChange={(v) => setLab({ linked: v })} t={t} label={t("lab_linked")} /></Row>
        <Row label={t("lab_sampling")}>
          <Seg value={st.lab.sampling} onChange={(v) => setLab({ sampling: v })} allowClear label={t("lab_sampling")}
            options={[{ v: "third_party", label: t("samp_third") }, { v: "lab", label: t("samp_lab") }, { v: "self", label: t("samp_self") }]} />
        </Row>
        <Row label={t("lab_screen")} hint={t("lab_screen_h")}><Tri value={st.lab.screen} onChange={(v) => setLab({ screen: v })} t={t} label={t("lab_screen")} /></Row>
      </div>

      <div className="toolbar">
        <button type="button" className="btn small" onClick={() => setOpen((o) => !o)} aria-expanded={open}>{t("paste_btn")}</button>
        <button type="button" className="btn small" onClick={() => fileRef.current && fileRef.current.click()}>{t("csv_btn")}</button>
        <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,text/csv,text/plain" hidden onChange={onFile} />
        <button type="button" className="btn small ghost" onClick={markND} title={t("markond_h")}>{t("markond")}</button>
      </div>
      {open && (
        <div className="paste">
          <textarea rows="6" value={paste} onChange={(e) => setPaste(e.target.value)} spellCheck="false" placeholder={t("paste_ph")} />
          <button type="button" className="btn" onClick={() => { apply(paste); }}>{t("paste_go")}</button>
        </div>
      )}
      {note && <p className="note-line" role="status">{note}</p>}

      <ul className="lrows">
        {st.rows.map((row) => {
          const res = resolve(row.key, bundle);
          const f = byId["result." + res.id];
          const aid = res.kind === "analyte" ? res.id : null;
          return (
            <LabRow key={row.key} row={row} t={t} label={aid ? bundle.analytes[aid].names[lang] : row.key}
              finding={f} findingText={f ? renderOne(f).text : ""} removable={!defaultKeys.has(row.key)}
              risk={aid ? riskLevel(bundle, aid) : null} alerts={aid && sig[aid] ? sig[aid].recent : 0}
              onChange={(nr) => setSt((s) => ({ ...s, rows: s.rows.map((r) => (r.key === row.key ? nr : r)) }))}
              onRemove={() => setSt((s) => ({ ...s, rows: s.rows.filter((r) => r.key !== row.key) }))} />
          );
        })}
      </ul>
      <div className="addrow">
        <input list="analyte-names" value={add} placeholder={t("add_ph")} onChange={(e) => setAdd(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addRow()} />
        <datalist id="analyte-names">{names.map((n) => <option key={n} value={n} />)}</datalist>
        <button type="button" className="btn small" onClick={addRow}>{t("add")}</button>
      </div>
    </>
  );
}

/* ---------- 03 farm ---------- */
export function FarmForm({ st, setSt, bundle, lang, t }) {
  const [other, setOther] = useState("");
  const chips = Object.entries(bundle.analytes).filter(([, a]) => a.kind === "pesticide" && !a.auto)
    .sort((a, b) => ((bundle.signals.by_analyte[b[0]] || {}).total || 0) - ((bundle.signals.by_analyte[a[0]] || {}).total || 0));
  const toggle = (id) => setSt((s) => ({ ...s, sprays: s.sprays.includes(id) ? s.sprays.filter((x) => x !== id) : [...s.sprays, id] }));
  const gap = (a) => {
    const l = a.limits || {};
    return l.IN && l.EU && l.EU.limit ? Math.round(l.IN.limit / l.EU.limit) : null;
  };
  const custom = st.sprays.filter((s) => !bundle.analytes[s]);
  return (
    <>
      <p className="lead">{t("farm_lead")}</p>
      <div className="chips">
        {chips.map(([id, a]) => (
          <button type="button" key={id} className={cx("chip", st.sprays.includes(id) && "on")} aria-pressed={st.sprays.includes(id)} onClick={() => toggle(id)}>
            {a.names[lang]}{gap(a) && gap(a) >= 2 ? <em>×{gap(a)}</em> : null}
          </button>
        ))}
        {custom.map((s) => (
          <button type="button" key={s} className="chip on" aria-pressed="true" onClick={() => toggle(s)}>{s}</button>
        ))}
      </div>
      <div className="addrow">
        <input list="analyte-names" value={other} placeholder={t("farm_other")} onChange={(e) => setOther(e.target.value)} />
        <button type="button" className="btn small" onClick={() => {
          const r = resolve(other, bundle);
          if (other.trim()) setSt((s) => ({ ...s, sprays: s.sprays.includes(r.kind === "analyte" ? r.id : other.trim()) ? s.sprays : [...s.sprays, r.kind === "analyte" ? r.id : other.trim()] }));
          setOther("");
        }}>{t("add")}</button>
      </div>
      <p className="fhint">{t("farm_gap_hint")}</p>
    </>
  );
}

/* ---------- 04 papers ---------- */
export function PapersForm({ st, setSt, bundle, lang, t }) {
  const market = marketOf(st.lot.dest, bundle);
  const mk = market ? bundle.markets[market] : null;
  if (!mk || !mk.docs) return <p className="lead">{t("papers_none")}</p>;
  const cat = bundle.i18n[lang].docs;
  return (
    <div className="qgroup">
      {mk.docs.map((d) => (
        <Row key={d.id} label={cat[d.id].name} hint={cat[d.id].issuer + (d.missing === "note" ? " · " + t("papers_importer") : "")}>
          <Tri value={st.docs[d.id] === undefined ? null : st.docs[d.id]} onChange={(v) => setSt((s) => ({ ...s, docs: { ...s.docs, [d.id]: v } }))} t={t} label={cat[d.id].name} />
        </Row>
      ))}
    </div>
  );
}

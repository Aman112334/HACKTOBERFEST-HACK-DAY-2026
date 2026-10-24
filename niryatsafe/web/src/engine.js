// NiryatSafe rules engine, JavaScript port of niryatsafe/engine.py.
// Deterministic: no network, no clock (as_of is passed in), no randomness. Differential-tested against the Python
// engine on hundreds of generated lots (tests/test_parity.py -> web/tests/parity.test.mjs).

const SEVERITY_RANK = { block: 0, fix: 1, note: 2, pass: 3 };
const GATE_RANK = { farm: 0, lab: 1, papers: 2, border: 3 };
const UNIT_FACTORS = new Map([["mg/kg", 1.0], ["ppm", 1.0], ["ug/kg", 0.001], ["ppb", 0.001]]);
const FORMS = ["raw_white", "sella", "brown"];
const SAMPLING = ["third_party", "lab", "self"];

// ---- small deterministic helpers ---------------------------------------------------------------
export const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, "");
const r12 = (x) => Number(x.toFixed(12));
const roundHalfUp = (x) => Math.floor(x + 0.5);

export function daysFromCivil(y, m, d) {
  y -= m <= 2 ? 1 : 0;
  const era = Math.floor(y / 400);
  const yoe = y - era * 400;
  const doy = Math.floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.floor(yoe / 4) - Math.floor(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}
export function civilFromDays(z) {
  z += 719468;
  const era = Math.floor(z / 146097);
  const doe = z - era * 146097;
  const yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365);
  const y = yoe + era * 400;
  const doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100));
  const mp = Math.floor((5 * doy + 2) / 153);
  const d = doy - Math.floor((153 * mp + 2) / 5) + 1;
  const m = mp < 10 ? mp + 3 : mp - 9;
  return [y + (m <= 2 ? 1 : 0), m, d];
}
export function parseDate(s) {
  if (typeof s !== "string") return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const y = +m[1], mo = +m[2], d = +m[3];
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return daysFromCivil(y, mo, d);
}
export function isoFromDays(n) {
  const [y, m, d] = civilFromDays(n);
  return String(y).padStart(4, "0") + "-" + String(m).padStart(2, "0") + "-" + String(d).padStart(2, "0");
}
const unitKey = (u) => String(u || "").trim().toLowerCase().replace(/\u00b5/g, "u").replace(/\u03bc/g, "u").replace(/ /g, "");

function numStr(x) {
  let s = x.toFixed(9).replace(/0+$/, "").replace(/\.$/, "");
  return s === "" || s === "-0" ? "0" : s;
}
function jsonStr(s) {
  let out = '"';
  for (let i = 0; i < s.length; i++) {
    const u = s.charCodeAt(i);
    if (u === 0x22) out += '\\"';
    else if (u === 0x5c) out += "\\\\";
    else if (u >= 0x20 && u < 0x7f) out += s[i];
    else out += "\\u" + u.toString(16).padStart(4, "0");
  }
  return out + '"';
}
export function canon(v) {
  if (v === null || v === undefined) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (typeof v === "number") return numStr(v);
  if (typeof v === "string") return jsonStr(v);
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  const keys = Object.keys(v).sort();
  return "{" + keys.map((k) => jsonStr(k) + ":" + canon(v[k])).join(",") + "}";
}
export function cyrb53(str) {
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507);
  h1 ^= Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507);
  h2 ^= Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}
export function memoId(text) {
  const s = cyrb53(text).toString(36).toUpperCase().padStart(11, "0").slice(-8);
  return "NS-" + s.slice(0, 4) + "-" + s.slice(4);
}

// ---- bundle indexes and market-keyed lookups -------------------------------------------------------
const indexCache = new WeakMap();
function getIndex(bundle) {
  let idx = indexCache.get(bundle);
  if (!idx) {
    const alias = new Map();
    for (const [aid, a] of Object.entries(bundle.analytes)) {
      for (const name of [aid, a.names.en, ...(a.aliases || [])]) {
        const k = norm(name);
        if (!alias.has(k)) alias.set(k, aid);
      }
    }
    idx = { alias };
    indexCache.set(bundle, idx);
  }
  return idx;
}
export function resolve(name, bundle) {
  const k = norm(name);
  const aid = getIndex(bundle).alias.get(k);
  if (aid !== undefined) return { kind: "analyte", id: aid, label: bundle.analytes[aid].names.en };
  return { kind: "unknown", id: "unk:" + k, label: String(name).trim() };
}
export function marketOf(dest, bundle) {
  if (!dest) return bundle.meta.default_market;
  if (Object.prototype.hasOwnProperty.call(bundle.markets, dest)) return dest;
  for (const [code, m] of Object.entries(bundle.markets)) if (m.countries.includes(dest)) return code;
  return null;
}
function limitFor(defn, market, form) {
  const lim = defn && defn.limits ? defn.limits[market] : undefined;
  if (!lim) return null;
  if (lim.by_form && lim.by_form[form] !== undefined) return lim.by_form[form];
  return lim.limit === undefined ? null : lim.limit;
}
function srcOf(defn, market, defaultSource) {
  const lim = defn && defn.limits ? defn.limits[market] : undefined;
  return lim && lim.sources && lim.sources.length ? [...lim.sources] : [defaultSource];
}
function indiaOf(defn) {
  const lim = defn && defn.limits ? defn.limits.IN : undefined;
  return [lim && lim.limit !== undefined ? lim.limit : null, lim && lim.sources ? [...lim.sources] : []];
}
export function riskLevel(bundle, aid) {
  const sig = (bundle.signals && bundle.signals.by_analyte) || {};
  const n = (sig[aid] && sig[aid].recent) | 0;
  const p = bundle.meta.policy;
  if (n >= p.risk_high) return "high";
  if (n >= p.risk_med) return "med";
  return n >= 1 ? "low" : null;
}
const ulabel = (defn) => (defn && defn.unit === "ug/kg" ? "µg/kg" : "mg/kg");

// ---- input normalisation -------------------------------------------------------------------------
const tri = (v) => (v === true || v === false ? v : null);
function num(v) {
  if (v === null || v === undefined || typeof v === "boolean") return null;
  let x;
  if (typeof v === "string") {
    const t = v.trim();
    if (t === "") return null;
    x = Number(t);
  } else x = Number(v);
  return Number.isFinite(x) ? x : null;
}
export function normalizeInput(raw) {
  raw = raw || {};
  const lot = raw.lot || {}, lab = raw.lab || {};
  const results = [];
  for (const r of raw.results || []) {
    if (!r || typeof r !== "object") continue;
    const name = String(r.analyte || "").trim();
    if (!name) continue;
    if (r.status === "nd") {
      results.push({ analyte: name, status: "nd", value: null, unit: unitKey(r.unit) || null, loq: num(r.loq) });
    } else if (r.status === "value") {
      const v = num(r.value);
      if (v === null || v < 0) continue;
      results.push({ analyte: name, status: "value", value: v, unit: unitKey(r.unit) || null, loq: num(r.loq) });
    }
  }
  const sprays = [];
  for (const s0 of raw.sprays || []) {
    const s = String(s0 || "").trim();
    if (s && !sprays.includes(s)) sprays.push(s);
  }
  const docs = {};
  for (const [k, v] of Object.entries(raw.docs || {})) docs[String(k)] = tri(v);
  return {
    lot: {
      form: FORMS.includes(lot.form) ? lot.form : "raw_white",
      dest: String(lot.dest || "").trim().toUpperCase(),
      ship_date: parseDate(lot.ship_date) !== null ? lot.ship_date : null,
      origin: String(lot.origin || "").trim().toLowerCase(),
      lot_id: String(lot.lot_id || "").trim(),
    },
    lab: {
      accredited: tri(lab.accredited),
      report_date: parseDate(lab.report_date) !== null ? lab.report_date : null,
      linked: tri(lab.linked),
      sampling: SAMPLING.includes(lab.sampling) ? lab.sampling : null,
      screen: tri(lab.screen),
    },
    results,
    sprays,
    docs,
    as_of: parseDate(raw.as_of) !== null ? raw.as_of : null,
  };
}

export function canonValue(value, unit, target) {
  const key = unit ? unit : target === "mg/kg" ? "mg/kg" : "ug/kg";
  const f = UNIT_FACTORS.get(key);
  if (f === undefined) return null;
  const mgkg = value * f;
  return target === "ug/kg" ? r12(mgkg * 1000.0) : r12(mgkg);
}
const rankGreater = (a, b) => a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);
const pseudo = (label) => ({ kind: "pesticide", unit: "mg/kg", tier: "watch", names: { en: label }, limits: {}, pseudo: true });

function finalize(findings, inp, bundle) {
  const policy = bundle.meta.policy;
  findings.sort((a, b) =>
    SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.priority - a.priority || GATE_RANK[a.gate] - GATE_RANK[b.gate] || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const counts = { block: 0, fix: 0, note: 0, pass: 0 };
  for (const f of findings) counts[f.severity] += 1;
  const verdict = counts.block ? "HOLD" : counts.fix ? "FIX_FIRST" : "SHIP";
  const gates = {};
  for (const g of Object.keys(GATE_RANK)) {
    const gs = findings.filter((f) => f.gate === g);
    if (gs.some((f) => f.severity === "block")) gates[g] = "block";
    else if (gs.some((f) => f.severity === "fix")) gates[g] = "fix";
    else if (gs.some((f) => f.severity === "pass")) gates[g] = "pass";
    else if (gs.length) gates[g] = "info";
    else gates[g] = "idle";
  }
  const bhash = bundle.meta.hash || "";
  const rbAge = Math.max(0, parseDate(inp.as_of) - parseDate(bundle.meta.verified_on));
  return {
    verdict, counts, steps: counts.block + counts.fix, gates, findings,
    memo_id: memoId(canon(inp) + "|" + bhash), as_of: inp.as_of, input: inp,
    rulebook: { id: bundle.meta.id, version: bundle.meta.version, hash: bhash, verified_on: bundle.meta.verified_on, age_days: rbAge, stale: rbAge > policy.stale_after_days },
  };
}

// ---- evaluation ----------------------------------------------------------------------------------
export function evaluate(rawInput, bundle) {
  const inp = normalizeInput(rawInput);
  if (inp.as_of === null) throw new Error("as_of (YYYY-MM-DD) is required: the engine never reads the clock");
  const policy = bundle.meta.policy;
  const watch = policy.watch_fraction;
  const mu = policy.mu_default;
  const form = inp.lot.form;
  const signals = (bundle.signals && bundle.signals.by_analyte) || {};
  const findings = [];
  const add = (id, gate, severity, basis, key, params, sources, analyte, action, priority) => {
    findings.push({
      id, gate, severity, basis, key, analyte: analyte === undefined ? null : analyte, params: params || {},
      sources: sources || [], action: action === undefined ? null : action, priority: priority || 0,
    });
  };
  const recent = (aid) => (signals[aid] && signals[aid].recent) | 0;

  const market = marketOf(inp.lot.dest, bundle);
  if (market === null) {
    add("market.coverage", "border", "fix", "practice", "market_not_covered", { dest: inp.lot.dest });
    return finalize(findings, inp, bundle);
  }
  const mk = bundle.markets[market];
  const dl = mk.default_limit, dsrc = mk.default_source;

  // resolve and de-duplicate result rows (worst case wins)
  const rows = new Map();
  const order = [];
  for (const r of inp.results) {
    const res = resolve(r.analyte, bundle);
    const key = res.id;
    const defn = res.kind === "analyte" ? bundle.analytes[key] : null;
    const target = defn ? defn.unit : "mg/kg";
    let cv, rank;
    if (r.status === "value") {
      cv = canonValue(r.value, r.unit, target);
      rank = [1, cv !== null ? cv : 0.0];
    } else {
      cv = null;
      const lq = r.loq !== null ? canonValue(r.loq, r.unit, target) : null;
      rank = [0, lq !== null ? lq : 0.0];
    }
    const entry = { res, row: r, cv, rank, target };
    if (!rows.has(key)) { rows.set(key, entry); order.push(key); }
    else if (rankGreater(entry.rank, rows.get(key).rank)) rows.set(key, entry);
  }
  const hasResults = order.length > 0;

  // per-result limit checks
  for (const key of order) {
    const e = rows.get(key);
    const { res, row: r, target } = e;
    const defn = res.kind === "analyte" ? bundle.analytes[key] : pseudo(res.label);
    const label = defn.names.en;
    const unitLabel = ulabel(defn);
    const fid = "result." + key;
    const pr = recent(key);
    const subj = res.kind === "analyte" ? key : label;
    const limit = limitFor(defn, market, form);
    const known = limit !== null;
    const L = known ? limit : dl;
    const [india, indiaSrc] = indiaOf(defn);
    const srcs = known ? srcOf(defn, market, dsrc) : [dsrc];
    if (known && india !== null) for (const s of indiaSrc) if (!srcs.includes(s)) srcs.push(s);
    const unitOk = UNIT_FACTORS.get(r.unit ? r.unit : target === "mg/kg" ? "mg/kg" : "ug/kg") !== undefined;
    if (!unitOk) {
      add(fid, "lab", "fix", "practice", "unit_unknown", { analyte: label, unit: r.unit }, [], subj, { kind: "lab_fix", params: { what: "unit" } }, pr);
      continue;
    }
    if (defn.screen_for) {
      if (rows.has("arsenic_inorganic")) continue;
      if (r.status === "value") {
        const v = e.cv;
        if (v > L) add(fid, "lab", "fix", "guidance", "as_total_speciation", { analyte: label, value: v, limit: L, unit: unitLabel }, srcs, subj,
          { kind: "speciation", params: { limit: L, unit: unitLabel } }, pr);
        else add(fid, "lab", "pass", "law", "as_total_ok", { analyte: label, value: v, limit: L, unit: unitLabel }, srcs, subj);
        continue;
      }
    }
    if (r.status === "value") {
      const v = e.cv;
      if (known && v > L) {
        add(fid, "lab", "block", "law", "limit_exceeded",
          { analyte: label, value: v, limit: L, unit: unitLabel, ratio: roundHalfUp((v / L) * 10) / 10.0,
            within_u: r12(v * (1 - mu)) <= L, india_limit: india, india_ok: india !== null ? v <= india : null },
          srcs, subj, { kind: "hold", params: {} }, pr);
      } else if (known && v >= watch * L) {
        add(fid, "lab", "fix", "practice", "limit_close", { analyte: label, value: v, limit: L, unit: unitLabel, pct: roundHalfUp((v / L) * 100) }, srcs, subj,
          { kind: "retest", params: { analyte: label } }, pr);
      } else if (!known && v > L) {
        add(fid, "lab", "fix", "law", "verify_mrl", { analyte: label, value: v, limit: L, unit: unitLabel, india_limit: india }, [dsrc], subj,
          { kind: "verify_mrl", params: { analyte: label } }, pr);
      } else {
        add(fid, "lab", "pass", "law", "limit_ok", { analyte: label, value: v, limit: L, unit: unitLabel }, srcs, subj);
      }
    } else if (r.loq === null) {
      add(fid, "lab", "fix", "guidance", "loq_missing", { analyte: label, limit: L, unit: unitLabel }, ["sante_11312"], subj,
        { kind: "lower_loq", params: { analyte: label, limit: L, unit: unitLabel } }, pr);
    } else {
      const q = canonValue(r.loq, r.unit, target);
      if (q > L) add(fid, "lab", "fix", "guidance", "loq_too_high", { analyte: label, loq: q, limit: L, unit: unitLabel }, ["sante_11312"], subj,
        { kind: "lower_loq", params: { analyte: label, limit: L, unit: unitLabel } }, pr);
      else add(fid, "lab", "pass", "law", "nd_ok", { analyte: label, loq: q, limit: L, unit: unitLabel }, srcs, subj);
    }
  }

  // required evidence: must-tier analytes + anything sprayed
  let required = [];
  for (const [aid, a] of Object.entries(bundle.analytes)) if (a.tier === "must") required.push([aid, a.names.en, "signal"]);
  const sprayedRes = [];
  for (const name of inp.sprays) {
    const res = resolve(name, bundle);
    sprayedRes.push(res);
    if (!required.some((x) => x[0] === res.id)) required.push([res.id, res.label, "sprayed"]);
    else required = required.map((x) => (x[0] === res.id ? [x[0], x[1], "sprayed"] : x));
  }
  const screen = inp.lab.screen === true;
  for (const [rid, label, reason] of required) {
    if (rows.has(rid)) continue;
    const def = bundle.analytes[rid] || null;
    const lim = def ? limitFor(def, market, form) : null;
    const L = lim !== null ? lim : dl;
    const fid = "required." + rid;
    const subj = def ? rid : label;
    if (screen) add(fid, "lab", "pass", "guidance", "covered_by_screen", { analyte: label }, ["reg_2019_1793"], subj);
    else {
      const rkey = lim === null ? "required_missing_default" : reason === "sprayed" ? "required_missing_sprayed" : "required_missing_signal";
      const ul = ulabel(def);
      add(fid, "lab", "fix", "law", rkey, { analyte: label, reason, recent: recent(rid), limit: L, unit: ul }, srcOf(def, market, dsrc), subj,
        { kind: "test", params: { analyte: label, limit: L, unit: ul } }, recent(rid) + (reason === "sprayed" ? 1000 : 0));
    }
  }

  // should-tier analytes not reported: one aggregate note
  const missing = [];
  const hasAs = rows.has("arsenic_inorganic") || rows.has("arsenic_total");
  for (const [aid, a] of Object.entries(bundle.analytes)) {
    if (a.tier !== "should" || rows.has(aid)) continue;
    if ((aid === "arsenic_inorganic" || aid === "arsenic_total") && hasAs) continue;
    if (a.kind === "pesticide" && screen) continue;
    if (aid === "arsenic_total" && !rows.has("arsenic_inorganic") && !hasAs) continue;
    if (required.some((x) => x[0] === aid)) continue;
    missing.push(a.names.en);
  }
  if (missing.length) add("lab.should_missing", "lab", "note", "law", "should_missing", { list: missing.join(", ") }, ["reg_2023_915"]);

  // spray history (upstream prevention)
  for (const res of sprayedRes) {
    const fid = "farm.sprayed." + res.id;
    if (res.kind === "analyte") {
      const a = bundle.analytes[res.id];
      const lim = limitFor(a, market, form);
      const [india] = indiaOf(a);
      const gap = lim && india ? roundHalfUp(india / lim) : null;
      const punjab = !!a.punjab_2025 && inp.lot.origin === "punjab";
      let skey;
      if (lim === null) skey = "sprayed_note_nolimit";
      else if (gap !== null && gap >= 2) skey = punjab ? "sprayed_note_gap_punjab" : "sprayed_note_gap";
      else if (punjab) skey = "sprayed_note_punjab";
      else skey = "sprayed_note";
      add(fid, "farm", "note", "guidance", skey, { analyte: res.label, limit: lim !== null ? lim : dl, unit: ulabel(a), india_limit: india, gap },
        a.punjab_2025 ? ["punjab_2025", "ls_2057_2025"] : ["ls_2057_2025"], res.id);
    } else {
      add(fid, "farm", "fix", "law", "sprayed_unknown", { analyte: res.label, limit: dl, unit: "mg/kg" }, [dsrc], res.label,
        { kind: "lookup_test", params: { analyte: res.label } });
    }
  }

  // lab-level evidence quality
  const lab = inp.lab;
  const reg = mk.regime || null;
  const inc = reg ? reg.increased_checks : null;
  if (!hasResults && !screen)
    add("lab.report", "lab", "fix", "practice", "lab_missing", { pct: inc ? inc.pct : null }, inc ? inc.sources : [], null, { kind: "get_report", params: {} }, 10000);
  if (hasResults || screen) {
    const lf = (what) => ({ kind: "lab_fix", params: { what } });
    if (lab.accredited === true) add("lab.accreditation", "lab", "pass", "practice", "lab_accredited", {}, ["sante_11312"]);
    else if (lab.accredited === false) add("lab.accreditation", "lab", "fix", "practice", "lab_not_accredited", {}, ["sante_11312"], null, lf("accredited"));
    else add("lab.accreditation", "lab", "fix", "practice", "lab_accreditation_unknown", {}, ["sante_11312"], null, lf("accredited"));
    const ref = inp.lot.ship_date ? parseDate(inp.lot.ship_date) : parseDate(inp.as_of);
    const rep = lab.report_date ? parseDate(lab.report_date) : null;
    const maxAge = policy.report_max_age_days;
    if (rep === null) add("lab.freshness", "lab", "fix", "practice", "lab_date_missing", {}, [], null, lf("date"));
    else if (ref - rep < 0) add("lab.freshness", "lab", "fix", "practice", "lab_date_invalid", {}, [], null, lf("date"));
    else if (ref - rep > maxAge) add("lab.freshness", "lab", "fix", "practice", "lab_stale", { age: ref - rep, max: maxAge }, [], null, lf("fresh"));
    else add("lab.freshness", "lab", "pass", "practice", "lab_fresh", { age: ref - rep, max: maxAge }, []);
    if (lab.linked === true) add("lab.link", "lab", "pass", "practice", "lab_linked", {}, []);
    else if (lab.linked === false) add("lab.link", "lab", "fix", "practice", "lab_unlinked", {}, [], null, lf("linked"));
    else add("lab.link", "lab", "fix", "practice", "lab_link_unknown", {}, [], null, lf("linked"));
    if (lab.sampling === "third_party" || lab.sampling === "lab") add("lab.sampling", "lab", "pass", "guidance", "sampling_ok", {}, ["sante_11312"]);
    else if (lab.sampling === "self") add("lab.sampling", "lab", "fix", "guidance", "sampling_self", {}, ["sante_11312"], null, lf("sampling"));
    else add("lab.sampling", "lab", "fix", "guidance", "sampling_unknown", {}, ["sante_11312"], null, lf("sampling"));
    if (screen) add("lab.screen", "lab", "pass", "law", "screen_ok", {}, ["reg_2019_1793"]);
    else add("lab.screen", "lab", "fix", "law", "screen_missing", {}, ["reg_2019_1793"], null, { kind: "screen", params: {} });
  }

  // papers
  const docs = mk.docs || null;
  for (const d of docs || []) {
    const val = inp.docs[d.id] === undefined ? null : inp.docs[d.id];
    const fid = "doc." + d.id;
    if (val === true) add(fid, "papers", "pass", d.basis, "doc_ok", { doc: d.id }, d.sources);
    else {
      const sev = d.missing;
      add(fid, "papers", sev, d.basis, val === false ? "doc_missing" : "doc_unconfirmed", { doc: d.id }, d.sources, null,
        sev === "fix" ? { kind: "get_doc", params: { doc: d.id } } : null);
    }
  }

  // border regime + context notes
  if (inc) add("border.regime", "border", "note", "law", "regime_checks", { pct: inc.pct }, inc.sources);
  if (!docs || !inc) add("border.partial", "border", "note", "practice", "market_partial", { market });
  if (findings.some((f) => f.key === "limit_exceeded" && f.params.within_u))
    add("border.mu", "border", "note", "guidance", "mu_note", { mu: roundHalfUp(mu * 100) }, ["sante_11312", "rasff_wi_2_2"]);
  if (findings.some((f) => f.severity === "block")) add("border.no_blending", "border", "note", "law", "no_blending", {}, ["reg_2023_915"]);

  return finalize(findings, inp, bundle);
}

// ---- samples with relative dates (+18d / -6d) ----------------------------------------------------
export function resolveSample(sample, asOf) {
  const base = parseDate(asOf);
  const rel = (v) => (typeof v === "string" && /^[+-]\d+d$/.test(v) ? isoFromDays(base + parseInt(v.slice(0, -1), 10)) : v);
  const inp = JSON.parse(JSON.stringify(sample.input));
  inp.lot.ship_date = rel(inp.lot.ship_date);
  if (inp.lab && inp.lab.report_date !== undefined) inp.lab.report_date = rel(inp.lab.report_date);
  inp.as_of = asOf;
  return inp;
}

// ---- text rendering from the shared catalog (mirrors niryatsafe/render.py) -------------------------
export function fmtNum(x) {
  if (x === null || x === undefined) return "-";
  if (typeof x === "boolean") return String(x);
  if (typeof x === "number") {
    if (x === 0) return "0";
    if (Number.isInteger(x)) return String(x);
    let s = String(Number(x.toPrecision(4)));
    if (/e/i.test(s)) s = x.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
    return s;
  }
  return String(x);
}
export const fill = (t, p) => t.replace(/\{(\w+)\}/g, (_, k) => fmtNum(p[k] === undefined ? "" : p[k]));
export function analyteName(bundle, id, lang) {
  const a = bundle.analytes[id];
  return a ? a.names[lang] : id;
}
export function renderFinding(f, bundle, lang) {
  const cat = bundle.i18n[lang];
  const p = { ...f.params };
  if (f.analyte && bundle.analytes[f.analyte]) p.analyte = analyteName(bundle, f.analyte, lang);
  if (p.doc !== undefined) {
    const d = cat.docs[p.doc] || {};
    p.issuer = d.issuer || "";
    p.doc = d.name || p.doc;
  }
  const text = fill(cat.m[f.key], p);
  let actionText = null;
  if (f.action) {
    const ap = { ...f.action.params };
    if ("analyte" in ap && bundle.analytes[f.analyte]) ap.analyte = analyteName(bundle, f.analyte, lang);
    if ("doc" in ap) {
      const d = cat.docs[ap.doc] || {};
      ap.issuer = d.issuer || "";
      ap.doc = d.name || ap.doc;
    }
    const akey = f.action.kind === "lab_fix" ? "lab_fix_" + ap.what : f.action.kind;
    actionText = fill(cat.a[akey], ap);
  }
  return { ...f, text, actionText };
}

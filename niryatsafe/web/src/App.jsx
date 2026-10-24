import { useEffect, useMemo, useRef, useState } from "react";
import { evaluate, renderFinding, riskLevel, marketOf } from "./engine.js";
import { blankState, stateFromSample, summaryText, toInput } from "./model.js";
import { cx, load, makeT, save, todayISO, useOnline } from "./ui.js";
import { GapChart, GateStrip, Glyph, History, InkDefs, LimitBars, Stamp } from "./viz.jsx";
import { FarmForm, LabForm, LotForm, PapersForm, STATES } from "./forms.jsx";
import { Memo } from "./memo.jsx";

const stateName = (v, lang) => { const s = STATES.find((x) => x[0] === v); return s ? (lang === "hi" ? s[2] : s[1]) : ""; };

function Slip({ n, title, children, id, className }) {
  return (
    <section className={cx("slip", className)} id={id}>
      <header className="slip-head"><span className="kicker">{n}</span><h2>{title}</h2></header>
      {children}
    </section>
  );
}

function Finding({ f, bundle, lang, t, srcIndex }) {
  const x = renderFinding(f, bundle, lang);
  const cat = bundle.i18n[lang];
  const aid = f.analyte && bundle.analytes[f.analyte] ? f.analyte : null;
  const risk = aid ? riskLevel(bundle, aid) : null;
  const recent = aid && bundle.signals.by_analyte[aid] ? bundle.signals.by_analyte[aid].recent : 0;
  return (
    <li className={"finding sev-" + f.severity}>
      <span className="mark"><Glyph kind={f.severity} /></span>
      <div>
        <p className="ftext">{x.text}</p>
        {x.actionText && <p className="faction"><b>→</b> {x.actionText}</p>}
        <div className="fmeta">
          <span className={"basis b-" + f.basis} title={cat.basis_help[f.basis]}>{cat.basis[f.basis]}</span>
          {risk && <span className={"risk r-" + risk}>{t("risk_" + risk)} · {t("risk_alerts", { n: recent })}</span>}
          {f.sources.map((id) => (
            <a key={id} className="src" href={bundle.sources[id].url} target="_blank" rel="noopener noreferrer" title={bundle.sources[id].title}>[{srcIndex[id]}]</a>
          ))}
        </div>
      </div>
    </li>
  );
}

export default function App({ initialBundle, onPack }) {
  const [bundle, setBundle] = useState(initialBundle);
  const [lang, setLang] = useState(() => load("ns.lang", (navigator.language || "en").toLowerCase().startsWith("hi") ? "hi" : "en"));
  const t = useMemo(() => makeT(bundle, lang), [bundle, lang]);
  const online = useOnline();
  const asOf = todayISO();
  const [st, setSt0] = useState(() => load("ns.draft", null) || { ...stateFromSample(bundle, bundle.samples[0], asOf), sample: bundle.samples[0].id });
  const setSt = (fn) => setSt0((s) => ({ ...(typeof fn === "function" ? fn(s) : fn), sample: null }));
  const setLot = (patch, top) => setSt((s) => (top ? { ...s, ...patch } : { ...s, lot: { ...s.lot, ...patch } }));
  const [lots, setLots] = useState(() => load("ns.lots", []));
  const [verify, setVerify] = useState({ s: "idle" });
  const [swReady, setSwReady] = useState(false);
  const [open, setOpen] = useState({});
  const verdictRef = useRef(null);

  useEffect(() => { document.documentElement.lang = lang; save("ns.lang", lang); }, [lang]);
  useEffect(() => { const h = setTimeout(() => save("ns.draft", st), 250); return () => clearTimeout(h); }, [st]);
  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.ready.then(() => setSwReady(true)).catch(() => {});
  }, []);
  useEffect(() => {   // keep the latest rules pack cached: fetch it when online, use it if it is newer
    if (!online || !/^https?:/.test(location.protocol)) return;
    fetch("/api/rulebook", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((p) => {
      if (p && p.meta && p.meta.hash !== bundle.meta.hash && onPack(p, bundle)) setBundle(p);
    }).catch(() => {});
  }, [online]);

  const input = useMemo(() => toInput(st, asOf), [st, asOf]);
  const { result, ms } = useMemo(() => {
    const t0 = performance.now();
    const r = evaluate(input, bundle);
    return { result: r, ms: performance.now() - t0 };
  }, [input, bundle]);
  const cat = bundle.i18n[lang];
  const renderOne = (f) => renderFinding(f, bundle, lang);

  // source numbering, in order of first appearance
  const srcIndex = {};
  const srcOrder = [];
  for (const f of result.findings) for (const id of f.sources) if (!(id in srcIndex)) { srcIndex[id] = srcOrder.length + 1; srcOrder.push(id); }

  const groups = { block: [], fix: [], pass: [], note: [] };
  for (const f of result.findings) groups[f.severity].push(f);
  const todo = result.findings.filter((f) => (f.severity === "block" || f.severity === "fix") && f.action);
  const seen = new Set();
  const steps = todo.map((f) => renderOne(f)).filter((x) => (seen.has(x.actionText) ? false : (seen.add(x.actionText), true)));
  const headline = result.findings.find((f) => (f.severity === "block" || f.severity === "fix") && f.params.limit !== undefined && (f.params.value !== undefined || f.params.loq !== undefined));
  const headX = headline ? renderOne(headline) : null;
  const dest = marketOf(st.lot.dest, bundle) === null ? t("dest_other") : st.lot.dest && bundle.countries[st.lot.dest] ? bundle.countries[st.lot.dest][lang] : t("dest_eu_any");
  const origin = stateName(st.lot.origin, lang);
  const text = summaryText(result, bundle, lang, t);
  const stepsText = result.steps === 0 ? t("steps_none") : result.steps === 1 ? t("steps_one") : t("steps", { n: result.steps });

  const loadSample = (s) => setSt0({ ...stateFromSample(bundle, s, asOf), sample: s.id });
  const blank = () => setSt0({ ...blankState(bundle), sample: null });
  const saveLot = () => {
    const flagged = [...new Set(result.findings.filter((f) => (f.severity === "block" || f.severity === "fix") && f.analyte && bundle.analytes[f.analyte]).map((f) => f.analyte))];
    const rec = { id: Date.now(), at: asOf, title: st.lot.lot_id || t("lot_untitled"), verdict: result.verdict, memo: result.memo_id, flagged, source: st.source || "", origin: st.lot.origin, state: st };
    const next = [rec, ...lots].slice(0, 20);
    setLots(next); save("ns.lots", next);
  };
  const dropLot = (id) => { const next = lots.filter((l) => l.id !== id); setLots(next); save("ns.lots", next); };
  const patterns = useMemo(() => {
    const bySub = {}, bySrc = {};
    for (const l of lots) {
      for (const a of l.flagged) bySub[a] = (bySub[a] || 0) + 1;
      if (l.source && l.verdict !== "SHIP") bySrc[l.source] = (bySrc[l.source] || 0) + 1;
    }
    const top = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, 3);
    return { sub: top(bySub), src: top(bySrc) };
  }, [lots]);

  const doVerify = async () => {
    setVerify({ s: "busy" });
    try {
      const r = await fetch("/api/evaluate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
      const j = await r.json();
      setVerify(j.memo_id === result.memo_id && j.verdict === result.verdict ? { s: "ok", id: j.memo_id } : { s: "diff", id: j.memo_id, v: j.verdict });
    } catch (e) { setVerify({ s: "off" }); }
  };
  const listen = () => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/[•→]/g, ","));
    u.lang = lang === "hi" ? "hi-IN" : "en-IN";
    window.speechSynthesis.speak(u);
  };
  const toggle = (k) => setOpen((o) => ({ ...o, [k]: !(k in o ? o[k] : k === "block" || k === "fix") }));
  const isOpen = (k) => (k in open ? open[k] : k === "block" || k === "fix");
  const share = "https://wa.me/?text=" + encodeURIComponent(text);
  const gateLabels = cat.gates;
  const mk = bundle.markets[marketOf(st.lot.dest, bundle) || bundle.meta.default_market];
  const regime = mk && mk.regime ? mk.regime.increased_checks : null;

  return (
    <div className="app">
      <InkDefs />
      <header className="top">
        <div className="brand">
          <span className="wordmark">Niryat<b>Safe</b></span>
          <span className="by">{t("by")}</span>
        </div>
        <div className="tools">
          <span className={cx("pill", online ? "on" : "off")} title={swReady ? t("pill_ready") : ""}><i />{online ? t("online") : t("offline")}{swReady ? <span className="ready"> · {t("works_offline")}</span> : null}</span>
          <div className="lang" role="group" aria-label="Language">
            <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>EN</button>
            <button type="button" aria-pressed={lang === "hi"} onClick={() => setLang("hi")} lang="hi">हिं</button>
          </div>
        </div>
      </header>

      <section className="hero">
        <p className="kicker">{t("hero_kicker")}</p>
        <h1>{t("hero_h1")}</h1>
        <p className="hero-sub">{t("hero_sub")}</p>
        <div className="lotline">
          <span className="kicker">{t("lot")} {st.lot.lot_id || "—"}</span>
          <strong>{t("basmati")}</strong>
          <span>{origin || "—"} → {dest}</span>
        </div>
        <div className="samples" role="group" aria-label={t("samples")}>
          <span className="kicker">{t("samples")}</span>
          {bundle.samples.map((s) => (
            <button type="button" key={s.id} className={cx("sample", st.sample === s.id && "on")} onClick={() => loadSample(s)} title={s.blurb[lang]}>{s.title[lang]}</button>
          ))}
          <button type="button" className="sample ghost" onClick={blank}>{t("blank")}</button>
        </div>
        {st.sample && <p className="sample-note">{bundle.samples.find((s) => s.id === st.sample).blurb[lang]}</p>}
      </section>

      <main className="grid">
        <div className="col-forms">
          <Slip n="01" title={t("s_lot")}><LotForm st={st} setLot={setLot} bundle={bundle} lang={lang} t={t} /></Slip>
          <Slip n="02" title={t("s_lab")}><LabForm st={st} setSt={setSt} bundle={bundle} lang={lang} t={t} result={result} renderOne={renderOne} /></Slip>
          <Slip n="03" title={t("s_farm")}><FarmForm st={st} setSt={setSt} bundle={bundle} lang={lang} t={t} /></Slip>
          <Slip n="04" title={t("s_papers")}><PapersForm st={st} setSt={setSt} bundle={bundle} lang={lang} t={t} /></Slip>
        </div>

        <aside className="col-verdict" id="verdict" ref={verdictRef}>
          <section className="slip verdict" aria-live="polite">
            <header className="slip-head"><span className="kicker">05</span><h2>{t("s_verdict")}</h2><span className="memo-id">{result.memo_id}</span></header>
            <div className="stamp-wrap"><Stamp key={result.verdict} verdict={result.verdict} label={cat.verdict[result.verdict]} lang={lang} /></div>
            <p className="verdict-sub">{cat.verdict_sub[result.verdict]}</p>
            <p className="stepcount">{stepsText}</p>
            <GateStrip gates={result.gates} labels={gateLabels} />
            {headline && (
              <div className="headline">
                <p className="kicker">{t("kicker_in_rice", { analyte: (bundle.analytes[headline.analyte] ? bundle.analytes[headline.analyte].names[lang] : headline.analyte).toUpperCase() })}</p>
                <LimitBars limit={headline.params.limit} value={headline.params.value} loq={headline.params.value === undefined ? headline.params.loq : undefined}
                  unit={headline.params.unit} indiaLimit={headline.params.india_limit} state={headline.severity} t={t} />
                <p className="ftext strong">{headX.text}</p>
              </div>
            )}
            {steps.length > 0 && (
              <div className="path">
                <h3>{t("path")}</h3>
                <ol>{steps.slice(0, 10).map((x, i) => <li key={i}>{x.actionText}</li>)}</ol>
                {steps.length > 10 && <p className="fhint">{t("more", { n: steps.length - 10 })}</p>}
              </div>
            )}
            {["block", "fix", "pass", "note"].map((k) => groups[k].length > 0 && (
              <div className={"group g-" + k} key={k}>
                <button type="button" className="group-head" aria-expanded={isOpen(k)} onClick={() => toggle(k)}>
                  <Glyph kind={k} /><span>{cat.severity[k]}</span><b>{groups[k].length}</b><i aria-hidden="true">{isOpen(k) ? "–" : "+"}</i>
                </button>
                {isOpen(k) && <ul className="findings">{groups[k].map((f) => <Finding key={f.id} f={f} bundle={bundle} lang={lang} t={t} srcIndex={srcIndex} />)}</ul>}
              </div>
            ))}
            <div className="actions">
              <a className="btn" href={share} target="_blank" rel="noopener noreferrer">{t("share")}</a>
              <button type="button" className="btn" onClick={() => window.print()}>{t("print")}</button>
              {"speechSynthesis" in window && <button type="button" className="btn" onClick={listen}>{t("listen")}</button>}
              <button type="button" className="btn" onClick={saveLot}>{t("save")}</button>
              <button type="button" className="btn ghost" onClick={doVerify} disabled={!online || verify.s === "busy"}>{t("verify")}</button>
            </div>
            {verify.s !== "idle" && <p className={cx("verify", verify.s)} role="status">{t("verify_" + verify.s, { id: verify.id || "", v: verify.v || "" })}</p>}
            <p className="meta-line">{t("computed", { ms: ms < 1 ? "<1" : Math.round(ms) })} · {t("rulebook")} {result.rulebook.version} · {t("verified")} {result.rulebook.verified_on}</p>
            {result.rulebook.stale && <p className="warn">{t("stale", { d: result.rulebook.age_days })}</p>}
            <p className="boundary">{t("boundary")}</p>
            <details className="sources">
              <summary>{t("sources_used", { n: srcOrder.length })}</summary>
              <ol>{srcOrder.map((id) => (
                <li key={id}><a href={bundle.sources[id].url} target="_blank" rel="noopener noreferrer">{bundle.sources[id].title}</a> <small>({bundle.sources[id].verified})</small></li>
              ))}</ol>
            </details>
          </section>
        </aside>
      </main>

      <section className="evidence">
        <Slip n="06" title={t("s_evidence")}>
          <div className="ev-grid">
            <div>
              <h3>{t("gap_title")}</h3>
              <p className="lead">{t("gap_lead")}</p>
              <GapChart gap={bundle.signals.gap || []} bundle={bundle} lang={lang} t={t} />
              <p className="legend"><i className="dot eu" /> {t("bars_eu")} <i className="dot india" /> {t("bars_india")}</p>
              <p className="fhint">{t("gap_src")}</p>
            </div>
            <div>
              <h3>{t("hist_title")}</h3>
              <p className="lead">{t("hist_lead")}</p>
              <History signals={bundle.signals} bundle={bundle} lang={lang} t={t} />
              {bundle.signals.demo && <p className="warn">{t("demo_data")}</p>}
              {regime && <p className="regime">{t("regime_card", { pct: regime.pct })}</p>}
            </div>
          </div>
        </Slip>
        <div className="band"><b>{t("band_a")}</b> {t("band_b")}</div>
      </section>

      <Slip n="07" title={t("s_lots")} className="lots">
        {lots.length === 0 ? <p className="lead">{t("lots_empty")}</p> : (
          <>
            {(patterns.sub.length > 0 || patterns.src.length > 0) && (
              <div className="patterns">
                <h3>{t("patterns")}</h3>
                {patterns.sub.length > 0 && <p>{t("pat_sub")}: {patterns.sub.map(([a, n]) => `${bundle.analytes[a].names[lang]} ×${n}`).join(" · ")}</p>}
                {patterns.src.length > 0 && <p>{t("pat_src")}: {patterns.src.map(([a, n]) => `${a} ×${n}`).join(" · ")}</p>}
              </div>
            )}
            <ul className="lotlist">
              {lots.map((l) => (
                <li key={l.id}>
                  <span className={"vdot " + l.verdict.toLowerCase()} />
                  <button type="button" className="linklike" onClick={() => setSt0({ ...l.state, sample: null })}>{l.title}</button>
                  <small>{cat.verdict[l.verdict]} · {l.at}{l.source ? " · " + l.source : ""} · {l.memo}</small>
                  <button type="button" className="x" aria-label={t("remove")} onClick={() => dropLot(l.id)}>×</button>
                </li>
              ))}
            </ul>
            <p className="fhint">{t("lots_local")}</p>
          </>
        )}
      </Slip>

      <footer className="foot">
        <p className="kicker">GREENLIGHT · NIRYATSAFE · HACKTOBERFEST HACK DAY 2026</p>
        <p>{t("foot_open")}</p>
        <p className="fhint">{t("foot_limits")}</p>
        <p className="fhint">{t("foot_rules", { v: bundle.meta.version, h: bundle.meta.hash })}</p>
      </footer>

      <div className="vbar" role="button" tabIndex="0" onClick={() => verdictRef.current && verdictRef.current.scrollIntoView({ behavior: "smooth" })}
        onKeyDown={(e) => e.key === "Enter" && verdictRef.current && verdictRef.current.scrollIntoView()}>
        <span className={"vdot " + result.verdict.toLowerCase()} />
        <b>{cat.verdict[result.verdict]}</b>
        <span>{stepsText}</span>
        <em>{t("open_verdict")} ↓</em>
      </div>

      <Memo result={result} bundle={bundle} lang={lang} t={t} st={st} dest={dest} origin={origin} srcOrder={srcOrder} srcIndex={srcIndex} steps={steps} />
    </div>
  );
}

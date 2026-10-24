import { cx } from "./ui.js";

/* ---------- ink filter shared by every stamp ---------- */
export function InkDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
      <defs>
        <filter id="ink" x="-12%" y="-25%" width="124%" height="150%">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="4" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" result="d" />
          <feTurbulence type="fractalNoise" baseFrequency="0.035 0.7" numOctaves="2" seed="9" result="m" />
          <feColorMatrix in="m" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1.25 0 0 0 0.5" result="mask" />
          <feComposite in="d" in2="mask" operator="in" />
        </filter>
      </defs>
    </svg>
  );
}

const STAMP_SIZE = {
  en: { SHIP: 66, FIX_FIRST: 36, HOLD: 66 },
  hi: { SHIP: 64, FIX_FIRST: 36, HOLD: 66 },
};

export function Stamp({ verdict, label, lang, small }) {
  const size = STAMP_SIZE[lang][verdict];
  return (
    <svg viewBox="0 0 300 124" role="img" aria-label={label} className={cx("stamp", verdict.toLowerCase(), small && "small")}>
      <g filter="url(#ink)" transform="rotate(-4 150 62)">
        <rect x="6" y="6" width="288" height="112" rx="11" fill="none" stroke="currentColor" strokeWidth="5" />
        <rect x="17" y="17" width="266" height="90" rx="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <text x="150" y={62 + size * 0.34} textAnchor="middle" fontSize={size} fontWeight="700" fill="currentColor"
          className="stamp-text" letterSpacing={lang === "en" ? (verdict === "FIX_FIRST" ? 3 : 6) : 0}>{label}</text>
      </g>
    </svg>
  );
}

/* ---------- small glyphs, one stroke weight ---------- */
export function Glyph({ kind }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 2.2, strokeLinecap: "square" };
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" className={"glyph " + kind}>
      {kind === "block" && <path {...p} d="M4 4l12 12M16 4L4 16" />}
      {kind === "fix" && <path {...p} d="M10 3v9M10 16v1" />}
      {kind === "pass" && <path {...p} d="M3.5 10.5l4 4 9-9.5" />}
      {kind === "note" && <path {...p} d="M10 9v7M10 4v1" />}
      {kind === "info" && <circle cx="10" cy="10" r="3" {...p} />}
      {kind === "idle" && <circle cx="10" cy="10" r="2" {...p} strokeDasharray="1 3" />}
    </svg>
  );
}

/* ---------- the route a lot travels: farm, lab, papers, EU border ---------- */
export function GateStrip({ gates, labels }) {
  const order = ["farm", "lab", "papers", "border"];
  const xs = [34, 124, 214, 304];
  return (
    <svg viewBox="0 0 338 62" className="gates" role="img" aria-label={order.map((g) => `${labels[g]}: ${gates[g]}`).join(", ")}>
      <line x1="34" y1="20" x2="304" y2="20" className="route" />
      {order.map((g, i) => (
        <g key={g} className={"gate g-" + gates[g]} transform={`translate(${xs[i]} 20)`}>
          <circle r="13" className="gate-ring" />
          <g transform="translate(-9 -9)"><Glyph kind={gates[g]} /></g>
          <text y="38" textAnchor="middle" className="gate-label">{labels[g]}</text>
        </g>
      ))}
    </svg>
  );
}

/* ---------- the deck's result card: EU limit bar against what your lab can show ---------- */
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
export function LimitBars({ limit, value, loq, unit, indiaLimit, state, t }) {
  const lo = limit / 10, hi = limit * 1000;
  const pct = (x) => 100 * clamp((Math.log10(Math.max(x, lo)) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo)), 0.05, 1);
  const mine = value !== undefined && value !== null ? value : loq;
  const mineLabel = value !== undefined && value !== null ? t("bars_result") : t("bars_loq");
  const fmt = (x) => String(Number(Number(x).toPrecision(3)));
  return (
    <div className="bars" role="img" aria-label={`${t("bars_eu")} ${fmt(limit)} ${unit}; ${mineLabel} ${fmt(mine)} ${unit}`}>
      <div className="bar-row"><span className="bar-label">{t("bars_eu")} <b>{fmt(limit)} {unit}</b></span>
        <span className="bar-track"><i className="bar eu" style={{ width: pct(limit) + "%" }} /></span></div>
      {indiaLimit !== null && indiaLimit !== undefined && (
        <div className="bar-row"><span className="bar-label">{t("bars_india")} <b>{fmt(indiaLimit)} {unit}</b></span>
          <span className="bar-track"><i className="bar india" style={{ width: pct(indiaLimit) + "%" }} /></span></div>
      )}
      {mine !== null && mine !== undefined && (
        <div className="bar-row"><span className={cx("bar-label", "mine", state)}>{mineLabel} <b>{fmt(mine)} {unit}</b></span>
          <span className="bar-track"><i className={cx("bar", "mine", state)} style={{ width: pct(mine) + "%" }} /></span></div>
      )}
    </div>
  );
}

/* ---------- Pass India, fail the EU: limits side by side on a log scale ---------- */
export function GapChart({ gap, bundle, lang, t }) {
  const rows = gap.filter((g) => g.eu_now && g.fssai).map((g) => ({ ...g, x: g.fssai / g.eu_now }))
    .sort((a, b) => b.x - a.x);
  const W = 340, rowH = 30, left = 112, right = 52, top = 22;
  const lo = Math.log10(0.005), hi = Math.log10(5);
  const X = (v) => left + ((Math.log10(v) - lo) / (hi - lo)) * (W - left - right);
  const name = (id) => (bundle.analytes[id] ? bundle.analytes[id].names[lang] : id);
  return (
    <svg viewBox={`0 0 ${W} ${top + rows.length * rowH + 16}`} className="gapchart" role="img" aria-label={t("gap_title")}>
      {[0.01, 0.1, 1].map((v) => (
        <g key={v}><line x1={X(v)} x2={X(v)} y1={top - 8} y2={top + rows.length * rowH} className="tick" />
          <text x={X(v)} y={top - 11} textAnchor="middle" className="tick-label">{v}</text></g>
      ))}
      {rows.map((r, i) => {
        const y = top + i * rowH + rowH / 2;
        return (
          <g key={r.analyte}>
            <text x="0" y={y + 4} className="gap-name">{name(r.analyte)}</text>
            <line x1={X(r.eu_now)} x2={X(r.fssai)} y1={y} y2={y} className="gap-line" />
            <circle cx={X(r.eu_now)} cy={y} r="5.5" className="dot eu" />
            <circle cx={X(r.fssai)} cy={y} r="5.5" className="dot india" />
            <text x={W} y={y + 4} textAnchor="end" className="gap-x">×{Math.round(r.x)}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ---------- EU border alerts on Indian rice, by year (Government of India data) ---------- */
export function History({ signals, bundle, lang, t }) {
  const by = signals.by_analyte || {};
  const years = signals.years || [];
  const top = Object.entries(by).sort((a, b) => b[1].total - a[1].total).slice(0, 6);
  if (!top.length) return null;
  const max = Math.max(1, ...top.flatMap(([, v]) => Object.values(v.by_year)));
  const name = (id) => (bundle.analytes[id] ? bundle.analytes[id].names[lang] : id);
  const last = years[years.length - 1];
  return (
    <div className="history">
      {top.map(([id, v]) => (
        <div className="hist-row" key={id}>
          <div className="hist-name">{name(id)}<small>{t("hist_total", { n: v.total })}</small></div>
          <svg viewBox={`0 0 ${years.length * 14} 34`} preserveAspectRatio="none" className="spark" aria-hidden="true">
            {years.map((y, i) => {
              const n = v.by_year[String(y)] || 0;
              const h = n ? Math.max(2, (n / max) * 32) : 0;
              return <rect key={y} x={i * 14 + 2} y={34 - h} width="10" height={h} className={y === last ? "partial" : ""} />;
            })}
            <line x1="0" x2={years.length * 14} y1="33.5" y2="33.5" className="base" />
          </svg>
        </div>
      ))}
      <p className="hist-note">{years[0]}–{last} · {t("hist_partial", { y: last })}</p>
    </div>
  );
}

import { renderFinding } from "./engine.js";

/* One-page pre-shipment memo. Hidden on screen, shown by the print stylesheet. */
export function Memo({ result, bundle, lang, t, st, dest, origin, srcOrder, srcIndex, steps }) {
  const cat = bundle.i18n[lang];
  const rows = result.findings.filter((f) => f.severity !== "pass").map((f) => renderFinding(f, bundle, lang));
  const passed = result.findings.filter((f) => f.severity === "pass").length;
  return (
    <section className="memo" aria-hidden="true">
      <header>
        <div><b className="wordmark">Niryat<b>Safe</b></b><span> · {t("memo_title")}</span></div>
        <div className="memo-meta">{t("memo_id")} {result.memo_id}<br />{result.as_of}</div>
      </header>
      <h1>{t("lot")} {st.lot.lot_id || "—"} · {t("basmati")} · {origin || "—"} → {dest}</h1>
      <p className="memo-verdict"><span className={"vtag " + result.verdict.toLowerCase()}>{cat.verdict[result.verdict]}</span> {cat.verdict_sub[result.verdict]}</p>
      {steps.length > 0 && (<><h2>{t("path")}</h2><ol>{steps.map((x, i) => <li key={i}>{x.actionText}</li>)}</ol></>)}
      <h2>{t("memo_findings")} ({rows.length}) · {t("memo_passed", { n: passed })}</h2>
      <table>
        <tbody>
          {rows.map((x) => (
            <tr key={x.id}><td className={"sev " + x.severity}>{cat.severity[x.severity]}</td>
              <td>{x.text}{x.sources.length ? " " + x.sources.map((s) => `[${srcIndex[s]}]`).join("") : ""}</td></tr>
          ))}
        </tbody>
      </table>
      <h2>{t("memo_sources")}</h2>
      <ol className="memo-src">{srcOrder.map((id) => <li key={id}>{bundle.sources[id].title} — {bundle.sources[id].url}</li>)}</ol>
      <p className="memo-foot">{t("boundary")} {t("rulebook")} {result.rulebook.version} ({result.rulebook.hash}) · {t("verified")} {result.rulebook.verified_on}. {t("memo_nollm")}</p>
    </section>
  );
}

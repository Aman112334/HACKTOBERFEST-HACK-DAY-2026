# Demo script (3 minutes) and Q&A

**Before you go on:** phone in airplane mode with the app installed (open it once online first), laptop on `make run-lite`
as a spare, `web/dist/niryatsafe-standalone.html` open in a tab, the recording at `docs/demo/fallback-demo.webm` ready.
Test on the real phone: the build here was only checked in headless Chromium.

| time | who | what |
|---|---|---|
| 0:00 | Abdul | The problem in one line: a basmati lot can pass India's checks and still be refused whole at the EU border. |
| 0:20 | Aman | Phone, airplane mode, pill says OFFLINE. Open **Lot 402 · Punjab → Germany**. Verdict: FIX FIRST. Point at the two bars: the EU limit is 0.01 mg/kg, your lab tests only down to 0.05, "Compliance cannot be shown." |
| 0:50 | Aman | Do what the app says: in the Lab report, tricyclazole, change LOQ to 0.01. The stamp changes to **SHIP**. |
| 1:10 | Aman | Tap **हिं**: same screen in Hindi. Tap **Passes India, fails the EU**: HOLD, with the three bars (EU 0.01, India 3, your lab 0.18). |
| 1:35 | Aman | Scroll to "Pass India, fail the EU": the chart of India's limit against the EU's. "×300 for tricyclazole." |
| 1:55 | Abdul | Why trust it: no LLM in the decision. Open `rules/limits.csv`: one row per rule, every row has a source. Basis tags: only law can say HOLD. |
| 2:20 | Abdul | Open source: a new market is a pull request, a maintainer signs the rules pack before each release. Same engine in the app and on the server, tested to give identical answers. |
| 2:40 | Abdul | Scale: spices, sesame, groundnut, tea; then the US and UK. New rows, not new code. Pilot with exporters next. |

## Likely questions
- **Why no AI?** A refused lot is a legal and financial event. Every verdict has to trace to a limit and a source. Fixed rules do; a language model cannot promise that.
- **Where do the limits come from?** EU regulations and the EU Pesticides Database, plus the Government of India's published list of EU rice limits (24 Jul 2024). Each row names its source; `rules/rulebook.yaml` says what was read directly and what is secondary.
- **How do you keep it current?** `pipeline limits-diff` compares our rows with an EU Pesticides Database export before each release; a maintainer signs the pack; the app fetches newer packs when online and caches them.
- **What if the lab result is "not detected"?** Only counts if the lab's detection limit (LOQ) is at or below the EU limit. That is Lot 402.
- **What does the risk flag mean?** How many EU border alerts hit Indian rice for that substance in the last five years of data. It ranks tests; it never changes a verdict.
- **Measurement uncertainty?** Official labs subtract a default 50% before calling a result non-compliant, so a small exceedance may not be formally non-compliant. We still say HOLD, because exceeding an MRL is treated as a serious risk, and we show a note.
- **Is this legal advice?** No. Final clearance rests with the lab certificate and the authorities.
- **Back-test result?** Only quote one that you produced from a real RASFF export (`make backtest RASFF=...`). The repo's synthetic run proves the harness only.

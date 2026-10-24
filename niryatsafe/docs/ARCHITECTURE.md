# Architecture

```
 public sources                    pipeline (Python, pandas, SQLite)               rules pack                 app (React PWA)
 ─────────────                     ───────────────────────────────                 ──────────                 ───────────────
 EU law, EU Pesticides DB  ──┐
 Govt of India tables      ──┼──►  rules/limits.csv  (one row per rule)  ──┐
 RASFF export (yours)      ──┤                                             ├─►  rules/compiled/bundle.json ──►  web/src/engine.js   (offline verdicts)
 FDA refusals (yours)      ──┴──►  data/niryatsafe.db + signals.json  ─────┘     (versioned, hashed)       └─►  niryatsafe/engine.py (API, back-tests)
                                    limits, events, reference_counts                                              FastAPI: /api/evaluate, /api/rules-pack
```

## The rules pack
`python -m niryatsafe.rulebook build` merges `rules/limits.csv`, `rules/rulebook.yaml` (sources, analyte names, tiers, markets,
documents), `rules/i18n.json`, `rules/ui.json`, `rules/samples.json` and `signals.json` into **one** `bundle.json`.
It carries a version (`meta.version`) and a content hash (`meta.hash`). The hash covers the rules, not the translations.
The server publishes it at `/api/rules-pack`; the app uses the copy built into it, and when online it fetches the server's
pack and keeps a newer one in local storage for offline use.

## The engine (deterministic)
Inputs: lot (form, destination, ship date), lab (accreditation, report date, sampling, screen), results, spray diary, papers,
and an explicit `as_of` date. The engine never reads the clock, the network or a random number.

Every check ends in one of four severities:

| severity | meaning | effect |
|---|---|---|
| `block` | a quantified result above a **legal** limit | verdict HOLD |
| `fix` | evidence missing or too weak: untested analyte, LOQ above the limit, result in the 80-100% band, stale or unlinked report, missing paper | verdict FIX FIRST |
| `note` | context (border regime, measurement uncertainty, spray history) | none |
| `pass` | evidenced and compliant | none |

**Unknown is never a pass.** "Not detected" only counts when the lab's LOQ is at or below the limit. Any substance without a
specific limit gets the EU default of 0.01 mg/kg (Reg. 396/2005 Art. 18(1)(b)): if it is in our table the row is law;
if it is not, a detection above 0.01 sends you to verify the MRL (FIX FIRST), never to HOLD.
Each finding carries a `basis` (`law`, `guidance`, `practice`) and its source ids. Only `law` can block.

What the sprayed pesticides do: each one becomes a required test, ranked first, with the FSSAI-vs-EU gap.
What the refusal data does: it ranks tests and adds a **risk flag** (alerts in the last five years of data). It never changes a verdict.

## Two engines, one behaviour
`niryatsafe/engine.py` and `web/src/engine.js` are line-for-line ports. `scripts/gen_vectors.py` generates 550+ lots (random and
mutations of a clean lot) and hashes the full canonical output of the Python engine; `web/tests/parity.test.mjs` replays them
through the JS engine and requires identical hashes. `tests/test_parity.py` runs both from `python -m unittest`.

## Markets are data
Limits are looked up as `analyte.limits[market]`; the destination country maps to a market (`markets.EU.countries`).
A market with limit rows but no `docs` or `regime` still works: limits are checked and the verdict says the rest is not covered.
A destination outside every market returns FIX FIRST with "not covered yet". A test adds a synthetic market without touching code.

## Offline
The service worker precaches the app shell (cache name = hash of the build). `/api/rulebook` is network-first with the last copy kept.
Lots and drafts live in `localStorage`; nothing leaves the device unless you tap "Verify on server".

## API
`GET /api/health` · `GET /api/rules-pack` · `GET /api/signals` · `POST /api/evaluate?lang=en|hi` · `POST /api/parse-lab-table`.
`python -m niryatsafe.serve` (standard library only) and `uvicorn niryatsafe.api:app` (FastAPI, OpenAPI at `/docs`) expose the same routes.

## Performance
Median engine time per verdict in the back-test harness: about 0.3 ms in Python. The app prints its own measured time under the verdict.

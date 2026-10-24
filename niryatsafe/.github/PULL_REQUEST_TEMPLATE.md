## What changes
<!-- A new rule, a new market, a fix, a translation? -->

## If you touched `rules/limits.csv`
- [ ] One row per rule, first five columns unchanged: `product,substance,market,limit_mg_kg,source`
- [ ] `limit_mg_kg` is in mg/kg (a 2 µg/kg limit is `0.002`)
- [ ] `source` ids exist in `rules/rulebook.yaml` (add a new source there with its URL)
- [ ] I opened the source and checked the number myself. Link and date: 
- [ ] `basis` is right: `law` (binding), `guidance`, `practice` or `reported`
- [ ] `python -m niryatsafe.rulebook check` passes

## Checks
- [ ] `make check` passes (Python tests, JS tests, parity)
- [ ] If I changed the engine, I changed `niryatsafe/engine.py` and `web/src/engine.js` together and ran `make vectors`

A maintainer reviews rule changes before each release (`make sign REVIEWER="Name"`).

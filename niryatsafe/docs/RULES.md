# Rules


| product | substance | market | limit_mg_kg | source |
|---|---|---|---|---|
| rice | tricyclazole | EU | 0.01 | reg_2017_983;ls_1314_2024 |

Optional columns: `form` (`raw_white`, `sella`, `brown`; inorganic arsenic depends on it), `basis`, `note`.
`market` is `EU` or `IN` (India's own FSSAI limit, used for the "passes India, fails the EU" comparison).
`source` holds one or more ids from `rules/rulebook.yaml`; the compiler rejects unknown ids, bad numbers, duplicates and
unknown markets, with the line number.

## Basis: what a rule is allowed to do
| basis | meaning | can cause |
|---|---|---|
| `law` | binding EU or Indian rule | HOLD, FIX FIRST |
| `guidance` | official guidance or an accepted method (e.g. LOQ expectations, SANTE/11312) | FIX FIRST |
| `practice` | buyer or industry practice (report age, who drew the sample) | FIX FIRST |
| `reported` | a figure quoted by an authority for comparison (India's FSSAI limits) | nothing: shown, never judged |

Defaults that are **policy, not law** (change in `rules/rulebook.yaml`, `meta.policy`): results at 80% or more of a limit are
"too close" (`watch_fraction`), lab reports older than 60 days are flagged (`report_max_age_days`), risk flags at 3 and 10 alerts.

## Verification status
Each source has `verified: primary` (read in the official text on 2026-10-20), `secondary` (confirmed through reputable
summaries or reprints) or `unchecked`. Secondary and unchecked rows are the first thing a maintainer should re-open.
The EU rice list of pesticides at the LOQ is the Government of India's list **as on 24.07.2024**; re-check it against the EU Pesticides Database.
The pack deliberately leaves out unverified numbers: pesticides whose EU rice MRL is above 0.01 mg/kg (e.g. tebuconazole, thifluzamide)
have no EU row, so a detection sends the user to verify the limit instead of guessing.

## Adding a market
1. Add the country codes and a block under `markets:` in `rules/rulebook.yaml` (`countries`, `default_limit`, `default_source`; optionally `docs` and `regime`).
2. Add rows to `rules/limits.csv` with the new `market` code. New substances need no other entry.
3. `make check`. Limits work immediately; without `docs`/`regime` the verdict adds a note that those checks are not covered yet.
`tests/test_labparse_rulebook_pipeline.py::test_a_new_market_is_new_rows_not_new_code` shows the whole thing on a synthetic market.

## Review and release
`rules/REVIEW.json` records who reviewed which pack hash. It ships **unsigned**. After a maintainer has read the diff:
`make sign REVIEWER="Name"`. `make release-check` then fails whenever the rules changed after the sign-off.

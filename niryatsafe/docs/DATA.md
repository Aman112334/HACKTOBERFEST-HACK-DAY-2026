# Data pipeline

```
python -m pipeline build                    # reference tables + any exports in data/raw/  ->  data/niryatsafe.db, signals.json, rules pack
python -m pipeline inspect FILE             # shows how an export's columns are mapped
python -m pipeline audit                    # do the rulebook tiers still match the refusal signals?
python -m pipeline backtest --rasff FILE    # would we have flagged those refused lots?
python -m pipeline limits-diff EXPORT       # compare rules/limits.csv with an EU Pesticides Database export
```

## What is bundled, and what is not
- **Real:** `data/reference/rasff_india_rice_gov.csv` and `limits_gap.csv`, transcribed from the Government of India's Lok Sabha
  answer 2057 (11 Mar 2025): EU RASFF detections of pesticides above the EU limit in Indian rice, 2015 to early 2025, and the
  EU / Codex / FSSAI limits for the same pesticides. This is what the Gap chart and the risk flags use out of the box. 2025 is a partial year.
- **Not bundled:** raw RASFF and FDA exports. Download them yourself (below), drop them in `data/raw/`, run `make data`.
- **Synthetic:** `data/fixtures/*SYNTHETIC*` are invented, ids start with `SYN-`. They exist to test the loaders and the back-test.
  `make data-demo` loads them and the app then shows a "SYNTHETIC demo data" warning.

## Getting the real exports
- **RASFF Window:** search for rice, origin India, the period you want, and export the results. The loader matches columns by
  name, case-insensitively (Subject, Date of case, Country of origin, Hazards, Product category, Action taken, an analytical-result column if present).
  Run `python -m pipeline inspect your_file.csv` to see the mapping; unmapped files fail with the columns they found.
- **FDA import refusals:** download the refusals CSV from the FDA Data Dashboard (Refusal Date, Country, Product Code Description, Refusal Charges).
  Dates are read month-first for FDA and day-first for RASFF.
The loaders extract substances by matching the rulebook's own names and aliases (no ML), classify hazards by keywords, and pull
a measured value from text like `Tricyclazole (0.22 mg/kg)`.

## SQLite schema
`limits` (the rules, one row each) · `events` (normalised refusals) · `reference_counts` · `limit_gap` · `sources` ·
views `v_limits_and_refusals` (each EU limit next to the alerts on Indian rice), `v_india_rice_eu`, `v_signal_by_year`.

## Back-test (deck slides 5, 6, 9)
For each Indian-rice RASFF notification that names a substance **and** carries a measured value, the harness builds a one-analyte lot,
runs the real engine, and counts it as flagged if the result is HOLD or in the watch band. Notifications without a value
(live insects, labelling) cannot be tested by lab-value rules and are reported separately. On the synthetic fixture it prints 34/34,
which only proves the harness. **Run it on a real RASFF export before quoting a hit rate.**

## Release review
`limits-diff` reads an EU Pesticides Database export (substance, product, MRL), keeps rice, and lists rows that changed, rows only
the EU lists (candidates to add) and rows only we list. Exit code 1 when anything differs. `--write-candidates` writes proposed rows
in the CSV contract for a maintainer to review.

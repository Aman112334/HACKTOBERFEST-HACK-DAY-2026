# NiryatSafe: one repo for the app, the rules engine and the data pipeline.
PY ?= python3

.PHONY: help setup rules data data-demo web standalone test e2e run run-lite check sign release-check backtest vectors assets clean

help:            ## list the targets
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*##/\t/'

setup:           ## install Python dependencies (and the web build tools if you have Node)
	$(PY) -m pip install -r requirements.txt
	-cd web && npm install

rules:           ## compile rules/limits.csv + rulebook.yaml into the versioned rules pack
	$(PY) -m niryatsafe.rulebook build

data:            ## reference tables (+ any RASFF/FDA exports in data/raw/) -> SQLite + signals -> rules pack
	$(PY) -m pipeline build

data-demo:       ## same, plus the SYNTHETIC fixtures (demo only; the app shows a warning)
	$(PY) scripts/make_fixtures.py && $(PY) -m pipeline build --fixtures

web:             ## build the React PWA into web/dist
	cd web && node build.mjs

standalone:      ## build one HTML file that opens by double-click (fallback for the demo)
	cd web && node build.mjs --standalone

test:            ## Python tests, then JS tests (includes the Python<->JS parity check)
	$(PY) -m unittest discover -s tests -t .
	cd web && node --test

e2e:             ## headless-Chromium end-to-end check (needs: pip install playwright && playwright install chromium)
	$(PY) scripts/e2e.py

run:             ## FastAPI + the PWA on http://localhost:8000
	$(PY) -m uvicorn niryatsafe.api:app --port 8000

run-lite:        ## no pip needed: standard-library server with the same API and PWA
	$(PY) -m niryatsafe.serve --port 8000

check:           ## what CI runs: validate rules.csv, run all tests
	$(PY) -m niryatsafe.rulebook check
	$(MAKE) test

sign:            ## a maintainer signs off the current rules pack:  make sign REVIEWER="Name"
	$(PY) -m niryatsafe.rulebook sign --by "$(REVIEWER)"

release-check:   ## fails unless the current rules pack has been reviewed and signed
	$(PY) -m niryatsafe.rulebook release-check

backtest:        ## would we have flagged past refused lots?  make backtest RASFF=data/raw/rasff_export.csv
	$(PY) -m pipeline backtest --rasff $(RASFF)

vectors:         ## regenerate the Python<->JS parity vectors after changing the engine
	$(PY) scripts/gen_vectors.py

assets:          ## regenerate fonts and icons (needs fonttools + Pillow)
	$(PY) scripts/make_assets.py

clean:
	rm -rf web/dist web/.tmp data/niryatsafe.db

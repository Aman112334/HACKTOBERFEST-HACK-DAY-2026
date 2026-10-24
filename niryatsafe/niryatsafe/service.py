"""Framework-agnostic service layer. Both the FastAPI app and the zero-dependency server call these functions."""
from __future__ import annotations

import os
from datetime import date

from .engine import evaluate, load_bundle
from .labparse import parse_table
from .render import render_result
from .rulebook import COMPILED, write_bundle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "web", "dist")


class Service:
    def __init__(self, bundle_path: str = COMPILED):
        if not os.path.exists(bundle_path):
            write_bundle(bundle_path)
        self.bundle = load_bundle(bundle_path)

    # --- read-only data -------------------------------------------------------------------------
    def health(self) -> dict:
        m = self.bundle["meta"]
        sig = self.bundle.get("signals") or {}
        return {"ok": True, "rulebook": {"id": m["id"], "version": m["version"], "hash": m["hash"], "verified_on": m["verified_on"]},
                "analytes": len(self.bundle["analytes"]), "markets": list(self.bundle["markets"]),
                "signals": {"years": sig.get("years"), "demo": sig.get("demo"), "notifications": (sig.get("totals") or {}).get("notifications")}}

    def rulebook(self) -> dict:
        return {k: v for k, v in self.bundle.items() if not k.startswith("_")}

    def signals(self) -> dict:
        return self.bundle.get("signals") or {}

    # --- actions -----------------------------------------------------------------------------------
    def evaluate(self, payload: dict, lang: str | None = None) -> dict:
        payload = dict(payload or {})
        if not payload.get("as_of"):
            payload["as_of"] = date.today().isoformat()   # the engine itself never reads the clock
        result = evaluate(payload, self.bundle)
        return render_result(result, self.bundle, lang) if lang in ("en", "hi") else result

    def parse_lab_table(self, text: str) -> dict:
        return parse_table(text, self.bundle)

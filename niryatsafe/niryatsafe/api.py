"""FastAPI app: JSON API + the built PWA.   uvicorn niryatsafe.api:app --port 8000

Written for FastAPI >= 0.100 and Pydantic v1 or v2.  The engine itself has no web dependencies (see service.py)."""
from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .service import DIST, Service

svc = Service()
app = FastAPI(
    title="NiryatSafe",
    version=__version__,
    description="Pre-shipment border-readiness for Indian basmati exports to the EU. Deterministic rules engine: "
                "every limit is source-linked, and there is no LLM in the decision path.",
)


class ResultRow(BaseModel):
    analyte: str = Field(..., description="Analyte name as printed on the lab report; aliases are resolved")
    status: Literal["nd", "value"]
    value: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, description="mg/kg, ppm, ug/kg or ppb")
    loq: Optional[float] = Field(None, ge=0)


class Lot(BaseModel):
    form: Literal["raw_white", "sella", "brown"] = "raw_white"
    pack: Literal["bulk", "retail"] = "bulk"
    ship_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    origin: str = ""
    lot_id: str = ""


class Lab(BaseModel):
    accredited: Optional[bool] = None
    report_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    linked: Optional[bool] = Field(None, description="report names this lot or batch")
    sampling: Optional[Literal["third_party", "lab", "self"]] = None
    screen: Optional[bool] = Field(None, description="report includes a multi-residue pesticide screen")


class EvaluateIn(BaseModel):
    lot: Lot = Field(default_factory=Lot)
    lab: Lab = Field(default_factory=Lab)
    results: List[ResultRow] = Field(default_factory=list)
    sprays: List[str] = Field(default_factory=list, description="pesticides sprayed on this crop")
    docs: Dict[str, Optional[bool]] = Field(default_factory=dict, description="iec, rcac, phyto, coi, invoice_pl, ched_d, labels")
    as_of: Optional[str] = Field(None, description="YYYY-MM-DD; defaults to the server date")


class ParseIn(BaseModel):
    text: str


def _dump(m: BaseModel) -> dict:
    return m.model_dump() if hasattr(m, "model_dump") else m.dict()


@app.get("/api/health")
def health():
    return svc.health()


@app.get("/api/rules-pack")
@app.get("/api/rulebook")
def rulebook(response: Response):
    response.headers["ETag"] = svc.bundle["meta"]["hash"]
    return svc.rulebook()


@app.get("/api/signals")
def signals():
    return svc.signals()


@app.post("/api/evaluate")
def evaluate(payload: EvaluateIn, lang: Optional[str] = Query(None, pattern="^(en|hi)$")):
    try:
        return svc.evaluate(_dump(payload), lang)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/parse-lab-table")
def parse_lab_table(body: ParseIn):
    return svc.parse_lab_table(body.text)


if os.path.isdir(DIST):
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")

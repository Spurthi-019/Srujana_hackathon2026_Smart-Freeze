"""
FastAPI application for Smart Freeze backend.

SIMULATED DATA ONLY - prototype for banks, human approves every action.
Never exposes is_mule, role, mule_ids, or victim_ids.
"""

from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.service import BackendService, ALLOWED_DELAYS

app = FastAPI(title="Smart Freeze API", version="0.1.0")

# Enable CORS for http://localhost:5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = BackendService()


class WhatIfRequest(BaseModel):
    account_id: str
    scam_id: str
    delay: int
    lam: float = Field(default=0.05)
    evidence_count: int = Field(default=0)


@app.get("/api/scams", response_model=List[Dict[str, Any]])
def list_scams():
    """Returns list of scams [{scam_id, start_time, total_stolen}]."""
    return service.get_scams()


@app.get("/api/graph", response_model=Dict[str, Any])
def get_graph(
    scam_id: str = Query(..., description="ID of the scam"),
    delay: int = Query(..., description="Decision delay in minutes (60, 180, 300)"),
):
    """Returns money-flow graph nodes, edges, start_time, and as_of."""
    if delay not in ALLOWED_DELAYS:
        raise HTTPException(status_code=422, detail=f"Invalid delay {delay}. Allowed delays: {ALLOWED_DELAYS}")
    try:
        return service.get_graph(scam_id, delay)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/decisions", response_model=List[Dict[str, Any]])
def get_decisions(
    scam_id: str = Query(..., description="ID of the scam"),
    delay: int = Query(..., description="Decision delay in minutes (60, 180, 300)"),
    lam: float = Query(..., description="Trade-off parameter lambda"),
):
    """Returns recommendation rows for accounts with tainted_max > 1."""
    if delay not in ALLOWED_DELAYS:
        raise HTTPException(status_code=422, detail=f"Invalid delay {delay}. Allowed delays: {ALLOWED_DELAYS}")
    try:
        return service.get_decisions(scam_id, delay, lam)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/account", response_model=Dict[str, Any])
def get_account(
    account_id: str = Query(..., description="ID of the account"),
    scam_id: str = Query(..., description="ID of the scam"),
    delay: int = Query(..., description="Decision delay in minutes (60, 180, 300)"),
    lam: float = Query(..., description="Trade-off parameter lambda"),
):
    """Returns full details, priority components, harm features, decision, and comparison for an account."""
    if delay not in ALLOWED_DELAYS:
        raise HTTPException(status_code=422, detail=f"Invalid delay {delay}. Allowed delays: {ALLOWED_DELAYS}")
    try:
        return service.get_account(account_id, scam_id, delay, lam)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/whatif", response_model=Dict[str, Any])
def whatif(req: WhatIfRequest):
    """Simulates effect of evidence on priority score and recommended action."""
    if req.delay not in ALLOWED_DELAYS:
        raise HTTPException(status_code=422, detail=f"Invalid delay {req.delay}. Allowed delays: {ALLOWED_DELAYS}")
    try:
        return service.whatif(
            account_id=req.account_id,
            scam_id=req.scam_id,
            delay=req.delay,
            lam=req.lam,
            evidence_count=req.evidence_count,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/tradeoff", response_model=List[Dict[str, Any]])
def get_tradeoff(
    delay: int = Query(..., description="Decision delay in minutes (60, 180, 300)"),
):
    """Returns policy trade-off evaluation rows for the given delay."""
    if delay not in ALLOWED_DELAYS:
        raise HTTPException(status_code=422, detail=f"Invalid delay {delay}. Allowed delays: {ALLOWED_DELAYS}")
    return service.get_tradeoff(delay)

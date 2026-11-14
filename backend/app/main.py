"""
Backend entry point (Backend lead owns this file).

Run locally:   cd backend && uvicorn app.main:app --reload
UNTESTED STUB: written without FastAPI installed. Run it and check /health first.

Every endpoint returns mock data for now so the frontend can build against it.
Replace each mock with the real function as the other layers finish.
"""
import json
from pathlib import Path

from fastapi import FastAPI

from .contract import (
    AuditResult,
    Bill,
    ChatRequest,
    ChatResponse,
    EstimateRequest,
    EstimateResult,
    EstimateStep,
    Flag,
    PlanTerms,
)

MOCK = Path(__file__).parent / "mock_data"

app = FastAPI(title="MediFit API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload/plan", response_model=PlanTerms)
def upload_plan():
    """MOCK. Real version: accept PDF (size cap), call extraction, return PlanTerms
    with confirmed=False. Delete the file after the session."""
    data = json.loads((MOCK / "plan_terms.json").read_text())
    data["confirmed"] = False
    return PlanTerms(**data)


@app.post("/api/estimate", response_model=EstimateResult)
def estimate(req: EstimateRequest):
    """MOCK. Real version: refuse if req.plan.confirmed is False, then call the
    calculator function (pure Python)."""
    return EstimateResult(
        steps=[EstimateStep(label="Mock step", math="mock", amount=0.0)],
        member_pays=0.0,
        plan_pays=req.allowed_amount,
    )


@app.post("/api/audit", response_model=AuditResult)
def audit(bill: Bill):
    """MOCK. Real version: deterministic detection, then Gemini explains each flag."""
    return AuditResult(
        flags=[
            Flag(
                kind="exact_duplicate",
                line_ids=["L1", "L2"],
                detail="Same provider, date, code and amount appear twice.",
                explanation="(mock) These two lines look identical. Worth asking the provider about.",
            )
        ]
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """MOCK. Real version: scope check, grounded answer with citations, caps on tokens/turns."""
    return ChatResponse(answer="(mock) Your deductible is $2,000.", citations=[])

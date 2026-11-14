"""
Backend entry point (Backend lead owns this file).

Run locally:   cd backend && uvicorn app.main:app --reload
UNTESTED STUB: written without FastAPI installed. Run it and check /health first.

Every endpoint returns mock data for now so the frontend can build against it.
Replace each mock with the real function as the other layers finish.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contract import (
    AuditResult,
    Bill,
    ChatRequest,
    ChatResponse,
    EstimateRequest,
    EstimateResult,
    Flag,
    PlanTerms,
)
from .calculator import estimate as calculate_estimate

MOCK = Path(__file__).parent / "mock_data"

app = FastAPI(title="MediFit API")


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError):
    if request.url.path != "/api/estimate":
        return await request_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {key: error[key] for key in ("loc", "msg", "type") if key in error}
                for error in exc.errors()
            ]
        },
    )


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
    """Calculate a sourced estimate from the user's confirmed plan terms."""
    try:
        return calculate_estimate(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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

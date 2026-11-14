"""
Backend entry point (Backend lead owns this file).

Run locally:   cd backend && uvicorn app.main:app --reload
UNTESTED STUB: written without FastAPI installed. Run it and check /health first.

Every endpoint returns mock data for now so the frontend can build against it.
Replace each mock with the real function as the other layers finish.
"""
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
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
from .pdf_upload import PdfUploadError, extract_pdf_pages

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


@app.post(
    "/api/upload/plan",
    response_model=PlanTerms,
    responses={
        400: {"description": "The uploaded PDF is invalid or unreadable."},
        413: {"description": "The uploaded PDF exceeds MAX_UPLOAD_MB."},
        501: {"description": "Plan extraction is not connected yet."},
    },
)
async def upload_plan(file: UploadFile = File(...)):
    """Validate and read a plan PDF in memory pending extraction integration."""
    try:
        try:
            max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "5"))
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Invalid MAX_UPLOAD_MB configuration.") from exc
        if max_upload_mb <= 0:
            raise HTTPException(status_code=500, detail="MAX_UPLOAD_MB must be a positive integer.")

        max_upload_bytes = max_upload_mb * 1024 * 1024
        pdf_bytes = await file.read(max_upload_bytes + 1)
        if len(pdf_bytes) > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"PDF exceeds the {max_upload_mb} MB upload limit.",
            )

        try:
            extract_pdf_pages(pdf_bytes)
        except PdfUploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        raise HTTPException(status_code=501, detail="Plan extraction is not connected yet.")
    finally:
        await file.close()


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

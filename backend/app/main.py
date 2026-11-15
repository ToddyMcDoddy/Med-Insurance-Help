"""
Backend entry point (Backend lead owns this file).

Run locally:   cd backend && uvicorn app.main:app --reload
UNTESTED STUB: written without FastAPI installed. Run it and check /health first.

Every endpoint returns mock data for now so the frontend can build against it.
Replace each mock with the real function as the other layers finish.
"""
import json
import os
from pathlib import Path

from anyio import to_thread
from fastapi import FastAPI, File, HTTPException, Path as ApiPath, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contract import (
    AuditResult,
    Bill,
    ChatRequest,
    ChatSessionContextRequest,
    ChatResponse,
    EstimateRequest,
    EstimateResult,
    PlanTerms,
)
from .calculator import estimate as calculate_estimate
from .demo_extractor import DemoExtractionError, extract_demo_plan
from .pdf_upload import PdfUploadError, extract_pdf_pages
from .extract_terms import extract_plan_terms_from_pages
from .upload_rate_limit import UploadRateLimiter
from .chat_service import (
    ChatConfigurationError,
    ChatInputError,
    ChatLimits,
    ChatSessionLimitError,
    ChatSessionStore,
    ChatToolError,
    ChatTurnLimitError,
    GeminiConfigurationError,
    GeminiProviderError,
    create_gemini_adapter,
    is_audit_request,
    prepare_estimate,
    run_chat,
)
from .audit import audit as audit_bill
from .bill_explain import explain_flags
from .chat import answer_question
from .insurer_profiles import detect_insurer, observe

app = FastAPI(title="MediFit API")
upload_rate_limiter = UploadRateLimiter()
chat_sessions = ChatSessionStore()
chat_adapter_factory = create_gemini_adapter


@app.middleware("http")
async def limit_plan_uploads(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/upload/plan":
        try:
            limit = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
        except ValueError:
            return JSONResponse(
                status_code=500,
                content={"detail": "Invalid RATE_LIMIT_PER_MIN configuration."},
            )
        if limit <= 0:
            return JSONResponse(
                status_code=500,
                content={"detail": "RATE_LIMIT_PER_MIN must be a positive integer."},
            )

        client_address = request.client.host if request.client else "unknown"
        retry_after = upload_rate_limiter.check(client_address, limit)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "Upload rate limit exceeded. Try again later."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


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


@app.get("/api/services")
def services(q: str = ""):
    """Look up illustrative pricing by service ID, name, or alias."""
    catalog = json.loads((Path(__file__).parent / "mock_data" / "services.json").read_text())
    query = q.strip().casefold().replace("_", " ")
    if query:
        catalog["services"] = [
            service for service in catalog["services"]
            if any(
                query == name.casefold().replace("_", " ")
                for name in (service["service_id"], service["service_name"], *service["aliases"])
            )
        ]
    return catalog


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/api/upload/plan",
    response_model=PlanTerms,
    responses={
        400: {"description": "The uploaded PDF is invalid or unreadable."},
        413: {"description": "The uploaded PDF exceeds MAX_UPLOAD_MB."},
        429: {"description": "The upload rate limit was exceeded; see Retry-After."},
        501: {"description": "Plan extraction is not connected yet."},
    },
)
async def upload_plan(response: Response, file: UploadFile = File(...)):
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
            pages = extract_pdf_pages(pdf_bytes)
        except PdfUploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        extractor_mode = os.getenv("EXTRACTOR_MODE", "disabled")
        if extractor_mode == "demo":
            try:
                plan = extract_demo_plan(pdf_bytes)
            except DemoExtractionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            response.headers["X-MediFit-Extraction-Mode"] = "demo"
            return plan

        if extractor_mode == "gemini":
            try:
                plan = await to_thread.run_sync(
                    extract_plan_terms_from_pages,
                    [text for _, text in pages],
                )
            except Exception as exc:
                if os.getenv("EXTRACTOR_DEMO_FALLBACK") == "1":
                    try:
                        plan = extract_demo_plan(pdf_bytes)
                    except DemoExtractionError:
                        pass
                    else:
                        response.headers["X-MediFit-Extraction-Mode"] = "demo"
                        return plan
                if isinstance(exc, RuntimeError) and "GEMINI_API_KEY is not set" in str(exc):
                    raise HTTPException(
                        status_code=503,
                        detail="GEMINI_API_KEY is not configured on the server.",
                    ) from exc
                raise HTTPException(
                    status_code=502,
                    detail="Plan extraction provider request failed.",
                ) from exc
            return plan.model_copy(update={"confirmed": False})

        if extractor_mode != "disabled":
            raise HTTPException(
                status_code=500,
                detail="EXTRACTOR_MODE must be disabled, demo, or gemini.",
            )
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
    return explain_flags(bill, audit_bill(bill))


@app.put("/api/chat/sessions/{session_id}/context")
def set_chat_context(
    session_id: str = ApiPath(min_length=1, max_length=128),
    context: ChatSessionContextRequest = ...,
):
    """Associate human-confirmed terms and extracted source pages with a session."""
    try:
        limits = ChatLimits.from_env()
    except ChatConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if len(context.documents) > limits.document_pages:
        raise HTTPException(
            status_code=413,
            detail=f"Chat context exceeds the {limits.document_pages}-page limit.",
        )
    context_chars = sum(len(document.text) for document in context.documents)
    if context_chars > limits.context_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Chat context exceeds the {limits.context_chars}-character limit.",
        )
    try:
        state = chat_sessions.associate_context(session_id, context)
    except ChatSessionLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if state.plan is not None and state.plan.confirmed:
        first_pages = sorted(
            (page for page in context.documents
             if page.doc_id == context.plan_document_id and page.page <= 2),
            key=lambda page: page.page,
        )
        observe(detect_insurer([page.text for page in first_pages]), state.plan)
    return {
        "session_id": session_id,
        "confirmed": bool(state.plan and state.plan.confirmed),
        "document_count": len(state.documents),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Answer with session-grounded Gemini tools and deterministic Python estimates."""
    try:
        limits = ChatLimits.from_env()
        session = chat_sessions.begin_turn(req.session_id, limits.turns_per_session)
        if is_audit_request(req.message):
            return run_chat(
                req,
                session,
                adapter=None,
                limits=limits,
                prepared_estimate=None,
            )
        prepared_estimate = prepare_estimate(req, session)
        adapter = chat_adapter_factory()
        try:
            return run_chat(
                req, session, adapter, limits=limits, prepared_estimate=prepared_estimate
            )
        except GeminiProviderError as provider_error:
            if req.estimate_input is not None or session.plan is None or not session.plan.confirmed:
                raise
            pages = sorted(
                (page for page in session.documents if page.doc_id == session.plan_document_id),
                key=lambda page: page.page,
            )
            if not pages:
                raise
            try:
                return answer_question(
                    req.message, [page.text for page in pages], session.plan,
                    doc_id=session.plan_document_id,
                    page_numbers=[page.page for page in pages],
                    max_output_tokens=limits.output_tokens,
                )
            except Exception:
                raise provider_error from None
    except ChatConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except GeminiConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ChatInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ChatSessionLimitError, ChatTurnLimitError) as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except GeminiProviderError as exc:
        raise HTTPException(
            status_code=502, detail="Gemini provider request failed."
        ) from exc
    except ChatToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/upload/pages")
async def upload_pages(file: UploadFile = File(...)):
    """Return the text of each plan PDF page so chat answers can cite pages."""
    try:
        max_bytes = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024
        pdf_bytes = await file.read(max_bytes + 1)
        if len(pdf_bytes) > max_bytes:
            raise HTTPException(status_code=413, detail="PDF exceeds the upload limit.")
        try:
            pages = extract_pdf_pages(pdf_bytes)
        except PdfUploadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"pages": [{"doc_id": "plan", "page": n, "text": t} for n, t in pages]}
    finally:
        await file.close()

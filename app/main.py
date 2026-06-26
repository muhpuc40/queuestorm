"""
QueueStorm Investigator — HTTP service.

Endpoints (exactly as required by the Problem Statement, Section 4):
    GET  /health          -> {"status": "ok"}
    POST /analyze-ticket  -> structured analysis (Section 6 schema)

Design goals enforced here:
    * Never crash on malformed input. Bad JSON / missing fields -> 400, semantic
      problems (empty complaint) -> 422, unexpected internals -> 500, but the
      process always stays up and responds.
    * Never leak secrets, tokens, or stack traces in any response body.
    * Pure-Python, dependency-light, sub-second responses.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .analyzer import analyze
from .safety import audit
from .schemas import AnalyzeRequest, AnalyzeResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("queuestorm")

app = FastAPI(
    title="QueueStorm Investigator",
    version="1.0.0",
    description="Support copilot that investigates fintech complaints against "
    "transaction evidence and drafts safe replies.",
)


@app.get("/health")
def health():
    """Liveness probe. Must return {'status': 'ok'} fast (Section 9)."""
    return {"status": "ok"}


@app.post("/analyze-ticket")
async def analyze_ticket(request: Request):
    # ---- 1. Parse JSON defensively (do not let bad JSON crash the worker) ----
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json", "detail": "Request body is not valid JSON."},
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_body", "detail": "Expected a JSON object."},
        )

    # ---- 2. Validate against the request schema ----
    try:
        req = AnalyzeRequest(**body)
    except Exception as exc:  # pydantic ValidationError, etc.
        missing = "ticket_id/complaint required"
        return JSONResponse(
            status_code=400,
            content={"error": "schema_error", "detail": f"Invalid request fields ({missing})."},
        )

    # ---- 3. Semantic validation (encouraged 422) ----
    if not (req.complaint or "").strip():
        return JSONResponse(
            status_code=422,
            content={"error": "empty_complaint", "detail": "complaint must be non-empty."},
        )

    # ---- 4. Run the investigator. Any internal error -> safe 500. ----
    try:
        result = analyze(req.model_dump())
        # Validate our own output against the strict output schema before sending.
        validated = AnalyzeResponse(**result).model_dump()
    except Exception:
        logger.exception("internal error during analysis")
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "Analysis failed."},
        )

    # ---- 5. Final safety self-check (defence in depth; never blocks 200) ----
    safe, violations = audit(validated.get("customer_reply", ""))
    if not safe:
        logger.warning("safety audit flagged reply for %s: %s",
                       validated.get("ticket_id"), violations)

    return JSONResponse(status_code=200, content=validated)


# --------------------------------------------------------------------------- #
# Global handlers so the service NEVER returns an uncaught stack trace.
# --------------------------------------------------------------------------- #
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "validation_error", "detail": "Malformed request."},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception("unhandled error")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Unexpected server error."},
    )


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)

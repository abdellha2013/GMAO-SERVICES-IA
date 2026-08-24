"""FastAPI application entry point.

This module creates the FastAPI ``app`` instance, configures the
lifespan (startup / shutdown), registers exception handlers, and
mounts the v1 router.

Usage (from the repository root)::

    uv run --env-file GMAO-ML/.env uvicorn gmao_ml.api.main:app \\
        --host 127.0.0.1 --port 8100 --reload
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gmao_ml.api.deps import load_predictor
from gmao_ml.api.v1.health import router as health_router
from gmao_ml.api.v1.predictions import router as predictions_router
from gmao_ml.exceptions import (
    DataError,
    InferenceValidationError,
    MLError,
    ModelNotFoundError,
    ModelNotReadyError,
)

logger = logging.getLogger("gmao_ml.api")


# =====================================================================
# Lifespan (startup / shutdown)
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Load the model at startup.

    Missing artifacts are tolerated so that health checks keep working
    before the first training run.
    """
    logger.info("Starting GMAO-ML API -- loading model...")
    load_predictor()
    logger.info("GMAO-ML API startup complete.")
    yield
    logger.info("Shutting down GMAO-ML API.")


# =====================================================================
# Exception handlers
# =====================================================================

def _ml_error_status(exc: MLError) -> int:
    """Determine the HTTP status code for an MLError.

    Rules:
    - Validation errors → 400
    - Not found errors  → 404
    - Not ready         → 503
    - Other errors      → exc.http_status or 500
    """
    if isinstance(exc, (InferenceValidationError, DataError)):
        return 400
    if isinstance(exc, ModelNotFoundError):
        return 404
    if isinstance(exc, ModelNotReadyError):
        return 503
    return exc.http_status or 500


# =====================================================================
# Application
# =====================================================================

app = FastAPI(
    title="GMAO-ML API",
    description="REST API for predictive maintenance state classification (GMAO).",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS (allow all origins for development) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request timing middleware ---
@app.middleware("http")
async def add_process_time_header(request: Request, call: Any) -> Any:
    """Add X-Process-Time header to every response."""
    start = time.perf_counter()
    response = await call(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response


# --- MLError exception handler ---
@app.exception_handler(MLError)
async def ml_error_handler(request: Request, exc: MLError) -> JSONResponse:
    """Map MLError hierarchy to structured JSON error responses."""
    status = _ml_error_status(exc)
    body = exc.to_dict() if hasattr(exc, "to_dict") else {"message": str(exc)}
    logger.warning("MLError [%s]: %s", exc.__class__.__name__, body.get("message", ""))
    return JSONResponse(status_code=status, content=body)


# --- Mount v1 router ---
app.include_router(predictions_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")

"""FastAPI application entry point.

This module creates the FastAPI ``app`` instance, configures the
lifespan (startup / shutdown), registers exception handlers, and
mounts the v1 router.

Usage::

    uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import create_all_orchestrators, dispose_all_orchestrators
from app.api.v1.rag import router as rag_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.exceptions import (
    EmptyQueryError,
    GMAOError,
    RetrievalConnectionError,
    RetrievalValidationError,
    RerankerValidationError,
    LLMValidationError,
)

logger = logging.getLogger("gmao_rag.api")


# =====================================================================
# Lifespan (startup / shutdown)
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Create orchestrators at startup, dispose at shutdown.

    Orchestrators are expensive to create (embedding model loading,
    database connections) so we build them once and reuse for every
    request.
    """
    logger.info("Starting GMAO-RAG API -- creating orchestrators...")
    create_all_orchestrators()
    logger.info("All orchestrators ready.")
    yield
    logger.info("Shutting down GMAO-RAG API -- disposing orchestrators...")
    dispose_all_orchestrators()
    logger.info("Shutdown complete.")


# =====================================================================
# Exception handlers
# =====================================================================

def _gmao_status(exc: GMAOError) -> int:
    """Determine the HTTP status code for a GMAOError.

    Rules:
    - Validation errors → 400
    - Connection errors → 503
    - Other errors → exc.http_status or 500
    """
    if isinstance(exc, (
        RetrievalValidationError,
        EmptyQueryError,
        RerankerValidationError,
        LLMValidationError,
    )):
        return 400
    if isinstance(exc, RetrievalConnectionError):
        return 503
    return exc.http_status or 500


# =====================================================================
# Application
# =====================================================================

app = FastAPI(
    title="GMAO-RAG API",
    description="REST API for the GMAO RAG pipeline (retrieval, reranking, LLM generation, ingestion).",
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


# --- GMAOError exception handler ---
@app.exception_handler(GMAOError)
async def gmao_error_handler(request: Request, exc: GMAOError) -> JSONResponse:
    """Map GMAOError hierarchy to structured JSON error responses."""
    status = _gmao_status(exc)
    body = exc.to_dict() if hasattr(exc, "to_dict") else {"message": str(exc)}
    logger.warning("GMAOError [%s]: %s", exc.__class__.__name__, body.get("message", ""))
    return JSONResponse(status_code=status, content=body)


# --- Mount v1 router ---
app.include_router(rag_router, prefix="/api/v1")
app.include_router(ingest_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")

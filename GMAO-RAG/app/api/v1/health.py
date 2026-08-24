"""System endpoints — health check, strategies list, statistics.

These endpoints provide operational visibility into the RAG pipeline
without requiring authentication (health) or with auth (strategies, stats).
"""
from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import create_engine, text

from app.api.auth import verify_api_key
from app.api.deps import (
    get_embedding_orchestrator,
    get_llm_orchestrator,
    get_reranker_orchestrator,
    get_retrieval_orchestrator,
)
from app.api.schemas import (
    HealthResponse,
    StatsResponse,
    StrategyListResponse,
)

logger = logging.getLogger("gmao_rag.api.health")

router = APIRouter(tags=["System"])


# =====================================================================
# Helpers
# =====================================================================

def _check_qdrant() -> str:
    """Ping the Qdrant server and return status.

    Returns ``"ok"`` if reachable, or an error message string.
    """
    try:
        from qdrant_client import QdrantClient

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        client = QdrantClient(host=host, port=port, timeout=5)
        client.get_collections()
        return "ok"
    except Exception as exc:
        return str(exc)


def _check_mysql() -> str:
    """Ping the MySQL server and return status.

    Returns ``"ok"`` if reachable, or an error message string.
    """
    try:
        dsn = os.getenv("MYSQL_DSN")
        if not dsn:
            host = os.getenv("GMAO_DB_HOST", "localhost")
            port = os.getenv("GMAO_DB_PORT", "3306")
            user = os.getenv("GMAO_DB_USER", "root")
            password = os.getenv("GMAO_DB_PASSWORD", "")
            db = os.getenv("GMAO_DB_NAME", "gmao")
            dsn = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"

        engine = create_engine(dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return "ok"
    except Exception as exc:
        return str(exc)


def _count_mysql(table: str) -> int:
    """Return the row count for a MySQL table, or 0 on error."""
    try:
        dsn = os.getenv("MYSQL_DSN")
        if not dsn:
            host = os.getenv("GMAO_DB_HOST", "localhost")
            port = os.getenv("GMAO_DB_PORT", "3306")
            user = os.getenv("GMAO_DB_USER", "root")
            password = os.getenv("GMAO_DB_PASSWORD", "")
            db = os.getenv("GMAO_DB_NAME", "gmao")
            dsn = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"

        engine = create_engine(dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar() or 0
        engine.dispose()
        return count
    except Exception:
        return 0


def _count_qdrant_points() -> int | None:
    """Return the total point count in Qdrant, or None if unreachable."""
    try:
        from qdrant_client import QdrantClient

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        collection = os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks")
        client = QdrantClient(host=host, port=port, timeout=5)
        info = client.get_collection(collection)
        return info.points_count or 0
    except Exception:
        return None


# =====================================================================
# GET /api/v1/health — Health check (no auth required)
# =====================================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check connectivity to Qdrant and MySQL backends.",
)
async def health_check() -> HealthResponse:
    """Check the health of all backend services.

    This endpoint does **not** require authentication so that load
    balancers and monitoring tools can probe it freely.
    """
    qdrant_status = _check_qdrant()
    mysql_status = _check_mysql()

    if qdrant_status == "ok" and mysql_status == "ok":
        status = "healthy"
    elif qdrant_status == "ok" or mysql_status == "ok":
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        qdrant=qdrant_status,
        mysql=mysql_status,
        version="0.1.0",
    )


# =====================================================================
# GET /api/v1/strategies — List available strategies
# =====================================================================

@router.get(
    "/strategies",
    response_model=StrategyListResponse,
    summary="List available strategies",
    description="Return the names of all registered strategies per pipeline layer.",
)
async def list_strategies(
    _token: Annotated[str, Depends(verify_api_key)],
    retrieval = Depends(get_retrieval_orchestrator),
    reranker = Depends(get_reranker_orchestrator),
    llm = Depends(get_llm_orchestrator),
    embedding = Depends(get_embedding_orchestrator),
) -> StrategyListResponse:
    """List all registered strategy names for each pipeline layer."""
    return StrategyListResponse(
        retrieval=list(retrieval.registry.supported_strategies()),
        reranker=list(reranker.registry.supported_strategies()),
        llm=list(llm.registry.supported_strategies()),
        embedding=list(embedding.registry.supported_strategies()),
    )


# =====================================================================
# GET /api/v1/stats — Pipeline statistics
# =====================================================================

@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Pipeline statistics",
    description="Return counts of indexed documents, chunks, and Qdrant points.",
)
async def stats(
    _token: Annotated[str, Depends(verify_api_key)],
) -> StatsResponse:
    """Return high-level statistics about the pipeline state."""
    return StatsResponse(
        documents_count=_count_mysql("document"),
        chunks_count=_count_mysql("chunk_rag"),
        qdrant_points=_count_qdrant_points(),
    )

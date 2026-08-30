"""Dependency injection for FastAPI.

Orchestrators are **expensive** to create (embedding model loading,
database connections, …).  This module builds them once at startup and
exposes them as FastAPI dependencies.

Each ``get_*`` function returns a callable that FastAPI will invoke
per-request — but the underlying orchestrator instance is a singleton
created during the ``lifespan`` event.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

from app.chunker import build_default_orchestrator as build_chunker_orchestrator
from app.data_sources import DataSourceOrchestrator
from app.embedding import build_default_orchestrator as build_embedding_orchestrator
from app.llm import build_default_orchestrator as build_llm_orchestrator
from app.parser import build_default_orchestrator as build_parser_orchestrator
from app.reranker import build_default_orchestrator as build_reranker_orchestrator
from app.retrieval import build_default_orchestrator as build_retrieval_orchestrator
from app.storage import build_default_orchestrator as build_storage_orchestrator

from app.chunker.orchestrator import ChunkerOrchestrator
from app.data_sources.orchestrator import DataSourceOrchestrator as DataSourceOrch
from app.embedding.orchestrator import EmbeddingOrchestrator
from app.llm.orchestrator import LLMOrchestrator
from app.parser.orchestrator import ParserOrchestrator
from app.reranker.orchestrator import RerankerOrchestrator
from app.retrieval.orchestrator import RetrievalOrchestrator
from app.storage.orchestrator import StorageOrchestrator


# =====================================================================
# Singleton container (populated at startup, read at request time)
# =====================================================================

class _Container:
    """Holds singleton orchestrator instances.

    Instances are created once during the FastAPI ``lifespan`` event
    and stored here.  The ``get_*`` functions below read from this
    container — they never create new orchestrators.
    """

    retrieval: RetrievalOrchestrator | None = None
    reranker: RerankerOrchestrator | None = None
    llm: LLMOrchestrator | None = None
    data_source: DataSourceOrch | None = None
    parser: ParserOrchestrator | None = None
    chunker: ChunkerOrchestrator | None = None
    embedding: EmbeddingOrchestrator | None = None
    storage: StorageOrchestrator | None = None
    # Warmup state: per-layer status ("ready"/"disabled"/erreur) and load ms.
    warmup: dict[str, str] = {}
    warmup_ms: dict[str, float] = {}


_container = _Container()


# =====================================================================
# Startup / shutdown
# =====================================================================

def create_all_orchestrators(**retrieval_options: Any) -> None:
    """Build all orchestrators and store them in the container.

    Called once during the FastAPI ``lifespan`` event.  Keyword
    arguments are forwarded to the retrieval orchestrator (e.g.
    ``embedding_options``, ``score_threshold``).

    Notes
    -----
    The retrieval orchestrator requires ``embedding_options`` to match
    the indexation configuration.  These are typically read from
    ``.env`` and passed here at startup.
    """
    _container.retrieval = build_retrieval_orchestrator(**retrieval_options)
    _container.reranker = build_reranker_orchestrator()
    _container.llm = build_llm_orchestrator()
    _container.data_source = DataSourceOrch()
    _container.parser = build_parser_orchestrator()
    _container.chunker = build_chunker_orchestrator()
    _container.embedding = build_embedding_orchestrator()
    _container.storage = build_storage_orchestrator()


def dispose_all_orchestrators() -> None:
    """Reset the container (called at shutdown or in tests)."""
    for attr in vars(_container):
        setattr(_container, attr, None)


def warmup_all_orchestrators(*, force: bool = False) -> dict[str, str]:
    """Preload the ML models so every request is warm from the first call.

    Models are cached at class level by the strategies (embedding, reranker,
    LLM client), but without this step they load lazily on the *first*
    request — which forces the user to wait for a multi-GB download/parse
    before getting an answer.  Calling this at startup moves that cost to
    boot time and keeps the models resident.

    Non-fatal: a failing layer is recorded (e.g. missing LLM API key) and
    does not prevent startup — the layer then degrades at request time.

    The warmup is skipped unless ``RAG_WARMUP_MODELS`` is truthy
    (default: enabled) or ``force=True`` — tests disable it to stay offline.

    Returns
    -------
    dict[str, str]
        Per-layer status: ``"ready"``, ``"disabled"``, ``"skipped"``, or
        ``"error: <message>"``.
    """
    enabled = force or os.getenv("RAG_WARMUP_MODELS", "1").strip().lower() in {
        "1", "true", "yes", "on",
    }

    layers = [
        ("retrieval", _container.retrieval),
        ("reranker", _container.reranker),
        ("llm", _container.llm),
        ("embedding", _container.embedding),
    ]

    result: dict[str, str] = {}
    for name, orchestrator in layers:
        if orchestrator is None:
            result[name] = "skipped"
            continue
        if not enabled:
            result[name] = "disabled"
            continue

        start = time.perf_counter()
        try:
            target = getattr(orchestrator, "warmup", None)
            if callable(target):
                target()
            result[name] = "ready"
        except Exception as exc:  # noqa: BLE001 - warmup must never block startup
            result[name] = f"error: {exc}"
            logger.warning("Warmup failed for layer '%s': %s", name, exc)
        _container.warmup_ms[name] = round((time.perf_counter() - start) * 1000, 1)

    _container.warmup = result
    logger.info("Model warmup: %s", result)
    return result


def get_warmup_status() -> tuple[dict[str, str], dict[str, float]]:
    """Return (per-layer status, per-layer load ms) from the startup warmup."""
    return dict(_container.warmup or {}), dict(_container.warmup_ms or {})


# =====================================================================
# FastAPI dependency functions
# =====================================================================

def get_retrieval_orchestrator() -> RetrievalOrchestrator:
    """Return the singleton retrieval orchestrator.

    Raises
    ------
    RuntimeError
        If called before ``create_all_orchestrators()``.
    """
    if _container.retrieval is None:
        raise RuntimeError(
            "Retrieval orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.retrieval


def get_reranker_orchestrator() -> RerankerOrchestrator:
    """Return the singleton reranker orchestrator."""
    if _container.reranker is None:
        raise RuntimeError(
            "Reranker orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.reranker


def get_llm_orchestrator() -> LLMOrchestrator:
    """Return the singleton LLM orchestrator."""
    if _container.llm is None:
        raise RuntimeError(
            "LLM orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.llm


def get_data_source_orchestrator() -> DataSourceOrch:
    """Return the singleton data source orchestrator."""
    if _container.data_source is None:
        raise RuntimeError(
            "Data source orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.data_source


def get_parser_orchestrator() -> ParserOrchestrator:
    """Return the singleton parser orchestrator."""
    if _container.parser is None:
        raise RuntimeError(
            "Parser orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.parser


def get_chunker_orchestrator() -> ChunkerOrchestrator:
    """Return the singleton chunker orchestrator."""
    if _container.chunker is None:
        raise RuntimeError(
            "Chunker orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.chunker


def get_embedding_orchestrator() -> EmbeddingOrchestrator:
    """Return the singleton embedding orchestrator."""
    if _container.embedding is None:
        raise RuntimeError(
            "Embedding orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.embedding


def get_storage_orchestrator() -> StorageOrchestrator:
    """Return the singleton storage orchestrator."""
    if _container.storage is None:
        raise RuntimeError(
            "Storage orchestrator not initialized. "
            "Call create_all_orchestrators() during startup."
        )
    return _container.storage

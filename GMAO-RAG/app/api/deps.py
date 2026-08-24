"""Dependency injection for FastAPI.

Orchestrators are **expensive** to create (embedding model loading,
database connections, …).  This module builds them once at startup and
exposes them as FastAPI dependencies.

Each ``get_*`` function returns a callable that FastAPI will invoke
per-request — but the underlying orchestrator instance is a singleton
created during the ``lifespan`` event.
"""
from __future__ import annotations

from typing import Any

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

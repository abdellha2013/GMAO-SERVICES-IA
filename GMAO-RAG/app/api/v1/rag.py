"""RAG endpoints — search, retrieve, rerank.

These endpoints expose the retrieval, reranking, and LLM generation
layers as HTTP APIs consumed by the Laravel backend.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.auth import verify_api_key
from app.api.deps import (
    get_llm_orchestrator,
    get_reranker_orchestrator,
    get_retrieval_orchestrator,
)
from app.api.schemas import (
    CitationSchema,
    FilterParams,
    RankedChunkSchema,
    RerankRequest,
    RerankResponse,
    RetrievedChunkSchema,
    RetrieveRequest,
    RetrieveResponse,
    SearchRequest,
    SearchResponse,
    StrategyInfo,
)
from app.exceptions import GMAOError, LLMError
from app.llm.orchestrator import LLMOrchestrator
from app.models.retrieval import RetrievedChunk, RetrievalFilter
from app.reranker.orchestrator import RerankerOrchestrator
from app.retrieval.orchestrator import RetrievalOrchestrator

logger = logging.getLogger("gmao_rag.api.rag")

router = APIRouter(prefix="/rag", tags=["RAG"])


# =====================================================================
# Helpers: domain model ↔ Pydantic schema conversion
# =====================================================================

def _chunk_to_schema(chunk: RetrievedChunk) -> RetrievedChunkSchema:
    """Convert a domain ``RetrievedChunk`` to a Pydantic response schema."""
    return RetrievedChunkSchema(**dataclasses.asdict(chunk))


def _ranked_to_schema(chunk: object) -> RankedChunkSchema:
    """Convert a domain ``RankedChunk`` to a Pydantic response schema."""
    return RankedChunkSchema(**dataclasses.asdict(chunk))


def _citation_to_schema(citation: object) -> CitationSchema:
    """Convert a domain ``Citation`` to a Pydantic response schema."""
    return CitationSchema(**dataclasses.asdict(citation))


def _schema_to_retrieved_chunk(schema: RetrievedChunkSchema) -> RetrievedChunk:
    """Convert a Pydantic schema back to a domain ``RetrievedChunk``."""
    return RetrievedChunk(
        chunk_id=schema.chunk_id,
        content=schema.content,
        score=schema.score,
        rank=schema.rank,
        source_name=schema.source_name,
        source_type=schema.source_type,
        id_document=schema.id_document,
        id_panne=schema.id_panne,
        id_equipement=schema.id_equipement,
        retrieval_strategy=schema.retrieval_strategy or "unknown",
    )


def _filters_to_domain(filters: FilterParams | None) -> RetrievalFilter | None:
    """Convert a Pydantic ``FilterParams`` to a domain ``RetrievalFilter``."""
    if filters is None:
        return None
    return RetrievalFilter(
        id_document=filters.id_document,
        id_panne=filters.id_panne,
        id_equipement=filters.id_equipement,
        source_type=filters.source_type,
        min_score=filters.min_score,
    )


# =====================================================================
# POST /api/v1/rag/search — Full RAG pipeline
# =====================================================================

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Full RAG pipeline",
    description="Retrieve relevant chunks, optionally rerank them, and generate an LLM answer.",
)
async def search(
    request: SearchRequest,
    _token: Annotated[str, Depends(verify_api_key)],
    retrieval: RetrievalOrchestrator = Depends(get_retrieval_orchestrator),
    reranker: RerankerOrchestrator = Depends(get_reranker_orchestrator),
    llm: LLMOrchestrator = Depends(get_llm_orchestrator),
) -> SearchResponse:
    """Execute the full RAG pipeline: retrieve → rerank → generate.

    The pipeline is configurable per request:
    - ``rerank=false`` skips the reranking step (faster).
    - ``generate=false`` returns chunks without an LLM answer.
    - ``llm_strategy`` overrides the default LLM (e.g. "gemini").
    """
    start = time.perf_counter()
    domain_filters = _filters_to_domain(request.filters)

    # --- Step 1: Retrieval ---
    report = retrieval.retrieve(
        request.query,
        top_k=request.top_k,
        filters=domain_filters,
    )

    ranked_chunks: list[object] = []
    reranker_name: str | None = None

    # --- Step 2: Reranking (optional) ---
    if request.rerank and report.results:
        ranked_chunks = reranker.rerank(
            request.query,
            report.results,
            top_k=request.top_k,
        )
        reranker_name = reranker.strategy_name
    else:
        # Passthrough: adapt RetrievedChunk → RankedChunk for response schema
        from app.models.reranking import RankedChunk

        ranked_chunks = [
            RankedChunk(
                chunk_id=c.chunk_id,
                content=c.content,
                source_name=c.source_name,
                source_type=c.source_type,
                retrieval_score=c.score,
                rerank_score=c.score,
                rank=c.rank,
                id_document=c.id_document,
                id_panne=c.id_panne,
                id_equipement=c.id_equipement,
                retrieval_strategy=c.retrieval_strategy,
                reranker_strategy="none",
            )
            for c in report.results
        ]

    # --- Step 3: LLM generation (optional, failure is non-fatal) ---
    answer = ""
    citations: list[CitationSchema] = []
    llm_name: str | None = None
    llm_error: str | None = None

    if request.generate and ranked_chunks:
        # LLM expects RankedChunk — if we skipped reranking, we still
        # need to provide the right type.  The orchestrator accepts
        # Sequence[RankedChunk], but we have RetrievedChunk.  We build
        # minimal RankedChunk-like objects.
        from app.models.reranking import RankedChunk

        llm_candidates: list[RankedChunk] = []
        for c in ranked_chunks:
            if isinstance(c, RankedChunk):
                llm_candidates.append(c)
            elif isinstance(c, RetrievedChunk):
                # Adapt RetrievedChunk → RankedChunk for LLM consumption
                llm_candidates.append(RankedChunk(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    source_name=c.source_name,
                    source_type=c.source_type,
                    retrieval_score=c.score,
                    rerank_score=c.score,
                    rank=c.rank,
                    id_document=c.id_document,
                    id_panne=c.id_panne,
                    id_equipement=c.id_equipement,
                    retrieval_strategy=c.retrieval_strategy,
                    reranker_strategy="none",
                ))

        # Catch LLM failures gracefully: the client still gets
        # retrieved/reranked chunks with an empty answer, plus
        # an llm_error field explaining what went wrong.
        try:
            response = llm.generate(
                request.query,
                llm_candidates,
                strategy_name=request.llm_strategy,
            )
            answer = response.answer
            llm_name = response.strategy_name
            citations = [_citation_to_schema(c) for c in response.citations]
        except LLMError as exc:
            llm_error = exc.message
            logger.warning("LLM generation failed (graceful degradation): %s", exc.message)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    # --- Build response ---
    results_schema = [_ranked_to_schema(c) for c in ranked_chunks]

    return SearchResponse(
        answer=answer,
        query=request.query,
        citations=citations,
        results=results_schema,
        strategy_info=StrategyInfo(
            retrieval=report.strategy_name,
            reranker=reranker_name,
            llm=llm_name,
        ),
        duration_ms=elapsed_ms,
        llm_error=llm_error,
    )


# =====================================================================
# POST /api/v1/rag/retrieve — Retrieval only
# =====================================================================

@router.post(
    "/retrieve",
    response_model=RetrieveResponse,
    summary="Retrieve relevant chunks",
    description="Search for chunks relevant to the query without reranking or LLM generation.",
)
async def retrieve(
    request: RetrieveRequest,
    _token: Annotated[str, Depends(verify_api_key)],
    retrieval: RetrievalOrchestrator = Depends(get_retrieval_orchestrator),
) -> RetrieveResponse:
    """Execute retrieval and return matching chunks ordered by relevance."""
    domain_filters = _filters_to_domain(request.filters)

    report = retrieval.retrieve(
        request.query,
        top_k=request.top_k,
        filters=domain_filters,
    )

    return RetrieveResponse(
        query=report.query,
        results=[_chunk_to_schema(c) for c in report.results],
        total_candidates=report.total_candidates,
        strategy_name=report.strategy_name,
    )


# =====================================================================
# POST /api/v1/rag/rerank — Reranking only
# =====================================================================

@router.post(
    "/rerank",
    response_model=RerankResponse,
    summary="Rerank pre-retrieved chunks",
    description="Apply cross-encoder reranking to a list of candidates.",
)
async def rerank(
    request: RerankRequest,
    _token: Annotated[str, Depends(verify_api_key)],
    reranker: RerankerOrchestrator = Depends(get_reranker_orchestrator),
) -> RerankResponse:
    """Rerank the provided candidates and return the top results."""
    # Convert Pydantic schemas back to domain models
    candidates = [_schema_to_retrieved_chunk(c) for c in request.candidates]

    ranked = reranker.rerank(
        request.query,
        candidates,
        top_k=request.top_k,
    )

    return RerankResponse(
        query=request.query,
        results=[_ranked_to_schema(c) for c in ranked],
    )

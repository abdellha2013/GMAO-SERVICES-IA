"""Pydantic schemas for request validation and JSON responses.

This module defines **all** Pydantic models used by the API layer.
Domain models (``RetrievedChunk``, ``RankedChunk``, …) live in
``app.models`` as frozen dataclasses — the schemas here mirror those
fields for serialization, adding FastAPI-specific validation (``Field``
constraints, examples, descriptions).

Naming convention
-----------------
- ``*Request``  — body of a POST endpoint (input).
- ``*Response`` — body returned to the caller (output).
- ``*Schema``   — reusable sub-object embedded in requests or responses.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# =====================================================================
# Shared sub-schemas
# =====================================================================

class FilterParams(BaseModel):
    """Optional constraints applied to retrieved chunks.

    All fields are optional.  When several are provided, they are
    combined with AND logic.
    """

    id_document: int | None = Field(
        None, gt=0,
        description="Filter chunks belonging to this document ID.",
    )
    id_panne: int | None = Field(
        None, gt=0,
        description="Filter chunks belonging to this panne ID.",
    )
    id_equipement: int | None = Field(
        None, gt=0,
        description="Filter chunks linked to this equipment ID.",
    )
    source_type: str | None = Field(
        None,
        description='Source type filter, e.g. "document" or "panne".',
    )
    min_score: float | None = Field(
        None,
        description="Minimum relevance score (inclusive).",
    )


class StrategyInfo(BaseModel):
    """Information about the strategies used during a request."""

    retrieval: str | None = Field(
        None, description="Name of the retrieval strategy used.",
    )
    reranker: str | None = Field(
        None, description="Name of the reranker strategy used.",
    )
    llm: str | None = Field(
        None, description="Name of the LLM strategy used.",
    )


# =====================================================================
# Retrieval schemas
# =====================================================================

class RetrievedChunkSchema(BaseModel):
    """One chunk returned by the retrieval layer.

    Mirrors ``app.models.retrieval.RetrievedChunk`` for JSON
    serialization.
    """

    chunk_id: str = Field(..., description="Unique chunk identifier.")
    content: str = Field(..., description="Text content of the chunk.")
    score: float = Field(..., description="Relevance score from the retrieval strategy.")
    rank: int = Field(..., description="Final rank (1-indexed).")
    source_name: str = Field(..., description="Name of the source file or panne.")
    source_type: str = Field(..., description='Type of source ("document", "panne", …).')
    id_document: int | None = Field(None, description="Parent document ID, if applicable.")
    id_panne: int | None = Field(None, description="Parent panne ID, if applicable.")
    id_equipement: int | None = Field(None, description="Linked equipment ID.")
    retrieval_strategy: str = Field("", description="Strategy that produced this chunk.")


# =====================================================================
# Reranker schemas
# =====================================================================

class RankedChunkSchema(BaseModel):
    """One chunk after reranking.

    Extends the retrieval chunk with a cross-encoder reranking score.
    Mirrors ``app.models.reranking.RankedChunk``.
    """

    chunk_id: str = Field(..., description="Unique chunk identifier.")
    content: str = Field(..., description="Text content of the chunk.")
    source_name: str = Field(..., description="Name of the source file or panne.")
    source_type: str = Field(..., description='Type of source ("document", "panne", …).')
    retrieval_score: float = Field(..., description="Original retrieval score.")
    rerank_score: float = Field(..., description="Cross-encoder reranking score.")
    rank: int = Field(..., description="Final rank after reranking (1-indexed).")
    id_document: int | None = Field(None, description="Parent document ID, if applicable.")
    id_panne: int | None = Field(None, description="Parent panne ID, if applicable.")
    id_equipement: int | None = Field(None, description="Linked equipment ID.")
    retrieval_strategy: str = Field("", description="Strategy that produced this chunk.")
    reranker_strategy: str = Field("", description="Strategy that reranked this chunk.")


# =====================================================================
# LLM schemas
# =====================================================================

class CitationSchema(BaseModel):
    """A source chunk cited by the LLM in its answer.

    Mirrors ``app.models.llm.Citation``.
    """

    chunk_id: str = Field(..., description="Cited chunk identifier.")
    source_name: str = Field(..., description="Name of the cited source.")
    source_type: str = Field(..., description="Type of the cited source.")
    rerank_score: float = Field(..., description="Reranking score of the cited chunk.")


# =====================================================================
# RAG request schemas
# =====================================================================

class SearchRequest(BaseModel):
    """Full RAG pipeline: retrieve → rerank → generate.

    Example::

        {
            "query": "Pourquoi la pompe vibre-t-elle ?",
            "filters": {"id_equipement": 42},
            "top_k": 10,
            "rerank": true,
            "generate": true
        }
    """

    query: str = Field(
        ..., min_length=1,
        description="User question (free text).",
        examples=["Pourquoi la pompe vibre-t-elle ?"],
    )
    filters: FilterParams | None = Field(
        None,
        description="Optional constraints on retrieved chunks.",
    )
    top_k: int | None = Field(
        None, ge=1, le=50,
        description="Number of results to return (default: 5, max: 50).",
    )
    rerank: bool = Field(
        True,
        description="Whether to apply reranking after retrieval.",
    )
    generate: bool = Field(
        True,
        description="Whether to generate an LLM answer.",
    )
    llm_strategy: str | None = Field(
        None,
        description='LLM strategy name (e.g. "openai", "gemini").  '
                    "None uses the default.",
    )


class RetrieveRequest(BaseModel):
    """Retrieval only — returns relevant chunks without reranking or LLM.

    Example::

        {
            "query": "pompe vibration",
            "filters": {"source_type": "panne"},
            "top_k": 10
        }
    """

    query: str = Field(
        ..., min_length=1,
        description="Search query (free text).",
        examples=["pompe vibration"],
    )
    filters: FilterParams | None = Field(
        None,
        description="Optional constraints on retrieved chunks.",
    )
    top_k: int | None = Field(
        None, ge=1, le=50,
        description="Number of results to return (default: 5, max: 50).",
    )


class RerankRequest(BaseModel):
    """Rerank a list of pre-retrieved candidates.

    Example::

        {
            "query": "pompe vibration",
            "candidates": [...],
            "top_k": 5
        }
    """

    query: str = Field(
        ..., min_length=1,
        description="Original user query (used as context by the reranker).",
    )
    candidates: list[RetrievedChunkSchema] = Field(
        ..., min_length=1,
        description="Chunks to rerank (as returned by /retrieve).",
    )
    top_k: int | None = Field(
        None, ge=1, le=50,
        description="Number of results to return after reranking.",
    )


# =====================================================================
# RAG response schemas
# =====================================================================

class SearchResponse(BaseModel):
    """Response for the full RAG pipeline (search endpoint).

    When the LLM step fails (rate limit, connection error, etc.),
    the response still returns a valid ``SearchResponse`` with an
    empty ``answer`` and a non-null ``llm_error`` field.  This lets
    the frontend display the retrieved/reranked chunks even when
    generation is unavailable.
    """

    answer: str = Field(..., description="LLM-generated answer (empty if LLM failed).")
    query: str = Field(..., description="Original user query.")
    citations: list[CitationSchema] = Field(
        default_factory=list,
        description="Source chunks cited by the LLM.",
    )
    results: list[RankedChunkSchema] = Field(
        default_factory=list,
        description="Reranked chunks (empty if rerank=false).",
    )
    strategy_info: StrategyInfo = Field(
        ...,
        description="Strategies used during the request.",
    )
    duration_ms: float = Field(
        ..., ge=0,
        description="Total request duration in milliseconds.",
    )
    llm_error: str | None = Field(
        None,
        description="Error message if LLM generation failed (null on success).",
    )


class RetrieveResponse(BaseModel):
    """Response for the retrieval-only endpoint."""

    query: str = Field(..., description="Original search query.")
    results: list[RetrievedChunkSchema] = Field(
        default_factory=list,
        description="Retrieved chunks, ordered by relevance.",
    )
    total_candidates: int = Field(
        ..., ge=0,
        description="Number of candidates before score_threshold filtering.",
    )
    strategy_name: str = Field(
        ..., description="Name of the retrieval strategy used.",
    )


class RerankResponse(BaseModel):
    """Response for the reranking-only endpoint."""

    query: str = Field(..., description="Original user query.")
    results: list[RankedChunkSchema] = Field(
        default_factory=list,
        description="Reranked chunks, ordered by rerank_score.",
    )


# =====================================================================
# Ingest request schemas
# =====================================================================

class IngestFileRequest(BaseModel):
    """Ingest a single file through the full pipeline.

    The file is uploaded as multipart/form-data.  This schema defines
    the optional metadata accompanying the upload.
    """

    id_equipement: int | None = Field(
        None, gt=0,
        description="Equipment ID to link the ingested chunks to.",
    )
    source_type: str | None = Field(
        None,
        description='Override source type (e.g. "document").  '
                    "Auto-detected from file extension if omitted.",
    )
    chunk_size: int = Field(
        500, ge=100, le=5000,
        description="Maximum chunk size in characters.",
    )
    chunk_overlap: int = Field(
        50, ge=0, le=500,
        description="Overlap between consecutive chunks.",
    )


class IngestDatabaseRequest(BaseModel):
    """Ingest data from a MySQL table or custom query.

    Example::

        {
            "host": "localhost",
            "database": "gmao",
            "user": "root",
            "password": "***",
            "table": "interventions",
            "id_equipement": 42
        }
    """

    driver: str = Field("mysql", description="Database driver.")
    host: str = Field(..., min_length=1, description="Database host.")
    port: int = Field(3306, gt=0, description="Database port.")
    database: str = Field(..., min_length=1, description="Database name.")
    user: str = Field(..., min_length=1, description="Database user.")
    password: str = Field(..., min_length=0, description="Database password.")
    table: str = Field(..., min_length=1, description="Table to ingest.")
    query: str | None = Field(
        None,
        description="Custom SQL query (overrides table if provided).",
    )
    id_equipement: int | None = Field(
        None, gt=0,
        description="Equipment ID to link the ingested chunks to.",
    )
    chunk_size: int = Field(
        500, ge=100, le=5000,
        description="Maximum chunk size in characters.",
    )
    chunk_overlap: int = Field(
        50, ge=0, le=500,
        description="Overlap between consecutive chunks.",
    )


class IngestMultipleRequest(BaseModel):
    """Batch ingestion — list of file paths already on disk.

    For uploading files via multipart, use ``/ingest/file`` in a loop.
    This endpoint is for bulk ingestion from a known directory.
    """

    paths: list[str] = Field(
        ..., min_length=1,
        description="Absolute paths to files on the server.",
    )
    id_equipement: int | None = Field(
        None, gt=0,
        description="Equipment ID to link all ingested chunks to.",
    )
    chunk_size: int = Field(
        500, ge=100, le=5000,
        description="Maximum chunk size in characters.",
    )
    chunk_overlap: int = Field(
        50, ge=0, le=500,
        description="Overlap between consecutive chunks.",
    )


# =====================================================================
# Ingest response schemas
# =====================================================================

class IngestResult(BaseModel):
    """Result of ingesting a single file."""

    status: str = Field(
        ..., description='"ok", "partial", or "error".',
    )
    document_name: str = Field(..., description="Name of the ingested file.")
    chunks_count: int = Field(
        ..., ge=0,
        description="Number of chunks created and stored.",
    )
    duration_ms: float = Field(
        ..., ge=0,
        description="Ingestion duration in milliseconds.",
    )
    error: str | None = Field(
        None,
        description="Error message if status is not 'ok'.",
    )


class IngestResponse(BaseModel):
    """Response for batch ingestion endpoints."""

    status: str = Field(
        ..., description='"ok" if all succeeded, "partial" if some failed.',
    )
    results: list[IngestResult] = Field(
        ..., description="Per-file ingestion results.",
    )
    total_files: int = Field(..., ge=0, description="Total files processed.")
    success_count: int = Field(..., ge=0, description="Files ingested successfully.")
    error_count: int = Field(..., ge=0, description="Files that failed ingestion.")


# =====================================================================
# Document management schemas
# =====================================================================

class DocumentSummary(BaseModel):
    """Summary of an indexed document."""

    id: int = Field(..., description="Document ID.")
    name: str = Field(..., description="Document name (filename).")
    source_type: str = Field(..., description='Source type ("document", "panne", …).')
    chunks_count: int = Field(..., ge=0, description="Number of indexed chunks.")
    indexed: bool = Field(..., description="Whether the document is fully indexed in Qdrant.")


class DocumentListResponse(BaseModel):
    """List of indexed documents."""

    documents: list[DocumentSummary] = Field(
        default_factory=list,
        description="Indexed documents.",
    )
    total: int = Field(..., ge=0, description="Total number of documents.")


class DocumentDetailResponse(BaseModel):
    """Detailed view of a single document with its chunks."""

    document: DocumentSummary = Field(..., description="Document metadata.")
    chunks: list[RetrievedChunkSchema] = Field(
        default_factory=list,
        description="Chunks belonging to this document.",
    )


class DeleteResponse(BaseModel):
    """Response after deleting a document."""

    status: str = Field("ok", description='"ok" on success.')
    deleted_chunks: int = Field(
        ..., ge=0,
        description="Number of chunks removed from storage.",
    )


# =====================================================================
# System schemas
# =====================================================================

class HealthResponse(BaseModel):
    """Health check response.

    Each backend reports ``"ok"`` or an error message.  The overall
    ``status`` is ``"healthy"`` only when all backends are reachable.
    """

    status: str = Field(
        ...,
        description='"healthy", "degraded", or "unhealthy".',
    )
    qdrant: str = Field(..., description='"ok" or error message.')
    mysql: str = Field(..., description='"ok" or error message.')
    version: str = Field("0.1.0", description="API version.")


class StrategyListResponse(BaseModel):
    """Available strategies per pipeline layer."""

    retrieval: list[str] = Field(..., description="Registered retrieval strategies.")
    reranker: list[str] = Field(..., description="Registered reranker strategies.")
    llm: list[str] = Field(..., description="Registered LLM strategies.")
    embedding: list[str] = Field(..., description="Registered embedding strategies.")


class StatsResponse(BaseModel):
    """Pipeline statistics."""

    documents_count: int = Field(..., ge=0, description="Total indexed documents.")
    chunks_count: int = Field(..., ge=0, description="Total indexed chunks.")
    qdrant_points: int | None = Field(
        None,
        description="Total points in Qdrant (None if unreachable).",
    )

"""Document management endpoints — list, detail, delete.

These endpoints provide document metadata and management operations
by querying MySQL directly (the source of truth for document records).

Real MySQL schema:
    document:       id_document, titre, nom_fichier, type_fichier,
                    chemin_fichier, taille, version, date_importation,
                    statut_indexation (En_attente/Indexe/Echec),
                    description, id_equipement
    chunk_rag:      id_chunk, contenu, ordre_chunk, nombre_tokens,
                    type_source (Document/Panne), statut_embedding,
                    date_indexation
    document_chunk: id_chunk, id_document  (junction table)
    panne_chunk:    id_chunk, id_panne     (junction table)
"""
from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, text

from app.api.auth import verify_api_key
from app.api.schemas import (
    DeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSummary,
    RetrievedChunkSchema,
)

logger = logging.getLogger("gmao_rag.api.documents")

router = APIRouter(prefix="/documents", tags=["Documents"])


# =====================================================================
# MySQL connection helper
# =====================================================================

def _get_mysql_engine():
    """Create a SQLAlchemy engine from environment variables.

    Reads ``MYSQL_DSN`` first, falls back to constructing DSN from
    individual ``GMAO_DB_*`` variables.
    """
    dsn = os.getenv("MYSQL_DSN")
    if not dsn:
        host = os.getenv("GMAO_DB_HOST", "localhost")
        port = os.getenv("GMAO_DB_PORT", "3306")
        user = os.getenv("GMAO_DB_USER", "root")
        password = os.getenv("GMAO_DB_PASSWORD", "")
        db = os.getenv("GMAO_DB_NAME", "gmao")
        dsn = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db}"
    return create_engine(dsn, pool_pre_ping=True)


# =====================================================================
# GET /api/v1/documents — List indexed documents
# =====================================================================

@router.get(
    "/",
    response_model=DocumentListResponse,
    summary="List indexed documents",
    description="Return all documents with their chunk counts.",
)
async def list_documents(
    _token: Annotated[str, Depends(verify_api_key)],
) -> DocumentListResponse:
    """List all documents in the database with their chunk counts.

    Joins through ``document_chunk`` to count chunks per document.
    The ``indexed`` field is derived from ``statut_indexation = 'Indexe'``.
    """
    engine = _get_mysql_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    d.id_document,
                    d.nom_fichier,
                    COALESCE(d.type_fichier, 'document') AS type_fichier,
                    d.statut_indexation,
                    COUNT(dc.id_chunk) AS chunks_count
                FROM document d
                LEFT JOIN document_chunk dc ON dc.id_document = d.id_document
                GROUP BY d.id_document, d.nom_fichier, d.type_fichier, d.statut_indexation
                ORDER BY d.id_document DESC
            """))
            rows = result.fetchall()

            documents = [
                DocumentSummary(
                    id=row[0],
                    name=row[1] or "unknown",
                    source_type=row[2] or "document",
                    chunks_count=row[4] or 0,
                    indexed=(row[3] == "Indexe"),
                )
                for row in rows
            ]

            return DocumentListResponse(
                documents=documents,
                total=len(documents),
            )
    except Exception as exc:
        logger.error("Failed to list documents: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    finally:
        engine.dispose()


# =====================================================================
# GET /api/v1/documents/{document_id} — Document detail
# =====================================================================

@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document detail",
    description="Return document metadata and its chunks.",
)
async def get_document(
    document_id: int,
    _token: Annotated[str, Depends(verify_api_key)],
) -> DocumentDetailResponse:
    """Fetch a single document and all its chunks from MySQL.

    Joins through ``document_chunk`` to find chunks belonging to this
    document, then enriches each chunk with parent metadata (id_document,
    id_panne) and equipment info.
    """
    engine = _get_mysql_engine()
    try:
        with engine.connect() as conn:
            # --- Fetch document metadata ---
            doc_result = conn.execute(text("""
                SELECT
                    d.id_document,
                    d.nom_fichier,
                    COALESCE(d.type_fichier, 'document') AS type_fichier,
                    d.statut_indexation,
                    d.titre,
                    d.description
                FROM document d
                WHERE d.id_document = :doc_id
            """), {"doc_id": document_id})
            doc_row = doc_result.fetchone()

            if doc_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document {document_id} not found.",
                )

            document = DocumentSummary(
                id=doc_row[0],
                name=doc_row[1] or "unknown",
                source_type=doc_row[2] or "document",
                chunks_count=0,  # updated below
                indexed=(doc_row[3] == "Indexe"),
            )

            # --- Fetch chunks via document_chunk junction table ---
            chunks_result = conn.execute(text("""
                SELECT
                    c.id_chunk,
                    c.contenu,
                    c.ordre_chunk,
                    c.type_source,
                    dc.id_document
                FROM chunk_rag c
                INNER JOIN document_chunk dc ON dc.id_chunk = c.id_chunk
                WHERE dc.id_document = :doc_id
                ORDER BY c.ordre_chunk ASC
            """), {"doc_id": document_id})
            chunk_rows = chunks_result.fetchall()

            chunks = [
                RetrievedChunkSchema(
                    chunk_id=str(row[0]),
                    content=row[1] or "",
                    score=0.0,
                    rank=int(row[2] or 0),
                    source_name=document.name,
                    source_type=row[3] or "document",
                    id_document=row[4],
                    id_panne=None,
                    id_equipement=None,
                    retrieval_strategy="",
                )
                for row in chunk_rows
            ]

            document.chunks_count = len(chunks)

            return DocumentDetailResponse(
                document=document,
                chunks=chunks,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get document %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    finally:
        engine.dispose()


# =====================================================================
# DELETE /api/v1/documents/{document_id} — Delete document
# =====================================================================

@router.delete(
    "/{document_id}",
    response_model=DeleteResponse,
    summary="Delete a document",
    description="Delete a document and all its chunks from storage.",
)
async def delete_document(
    document_id: int,
    _token: Annotated[str, Depends(verify_api_key)],
) -> DeleteResponse:
    """Delete a document and its associated chunks.

    Removes chunk associations from ``document_chunk``, then deletes
    the chunks from ``chunk_rag`` and the document record from
    ``document``.
    """
    engine = _get_mysql_engine()
    try:
        with engine.begin() as conn:
            # --- Check document exists ---
            result = conn.execute(
                text("SELECT COUNT(*) FROM document WHERE id_document = :doc_id"),
                {"doc_id": document_id},
            )
            if result.scalar() == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document {document_id} not found.",
                )

            # --- Find chunk IDs linked to this document ---
            chunk_ids_result = conn.execute(
                text("SELECT id_chunk FROM document_chunk WHERE id_document = :doc_id"),
                {"doc_id": document_id},
            )
            chunk_ids = [row[0] for row in chunk_ids_result.fetchall()]

            # --- Delete junction rows ---
            conn.execute(
                text("DELETE FROM document_chunk WHERE id_document = :doc_id"),
                {"doc_id": document_id},
            )

            # --- Delete chunk_rag rows ---
            deleted_chunks = 0
            if chunk_ids:
                # Use IN clause with bound parameters
                placeholders = ", ".join(f":id_{i}" for i in range(len(chunk_ids)))
                params = {f"id_{i}": cid for i, cid in enumerate(chunk_ids)}
                delete_result = conn.execute(
                    text(f"DELETE FROM chunk_rag WHERE id_chunk IN ({placeholders})"),
                    params,
                )
                deleted_chunks = delete_result.rowcount

            # --- Delete document record ---
            conn.execute(
                text("DELETE FROM document WHERE id_document = :doc_id"),
                {"doc_id": document_id},
            )

            logger.info(
                "Deleted document %s and %d chunks.",
                document_id,
                deleted_chunks,
            )

            return DeleteResponse(
                status="ok",
                deleted_chunks=deleted_chunks,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete document %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    finally:
        engine.dispose()

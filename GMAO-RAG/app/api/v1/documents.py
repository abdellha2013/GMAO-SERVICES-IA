"""Document management endpoints — list, detail, delete.

These endpoints provide document metadata and management operations
by querying MySQL directly (the source of truth for document records).

Local MySQL schema (base ``gmao``) — schema fusionné, documents uniquement:
    documents:       id_document, titre, nom_fichier, type_fichier,
                     chemin_fichier, taille, version, date_importation,
                     description, id_equipement
    document_chunks: id_chunk, contenu, ordre_chunk, nombre_tokens,
                     id_document  (contenu + rattachement fusionnés)

Il n'existe ni table ``chunk_rag``, ni jonction ``document_chunk``,
ni colonne ``statut_indexation`` : l'état ``indexed`` est dérivé de la
présence des chunks du document dans Qdrant.
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


def _delete_qdrant_points(chunk_ids: list[int]) -> None:
    """Delete the Qdrant points for ``chunk_ids``.

    The point id equals the chunk's ``id_chunk`` (same convention as the
    ingestion pipeline).  Qdrant failures are logged but do not abort the
    MySQL deletion, mirroring the tolerant behaviour of
    :func:`_qdrant_present_chunk_ids`.
    """
    if not chunk_ids:
        return
    try:
        from qdrant_client import QdrantClient

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        collection = os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks")
        client = QdrantClient(host=host, port=port, timeout=5)
        client.delete(
            collection_name=collection,
            points_selector=list(chunk_ids),
        )
    except Exception as exc:
        logger.warning(
            "Qdrant unreachable while deleting points: %s", exc
        )


def _qdrant_present_chunk_ids(chunk_ids: list[int]) -> set[int]:
    """Return the subset of ``chunk_ids`` that exist in Qdrant.

    Since the ``gmao`` schema has no ``statut_indexation`` column, the
    ``indexed`` flag is derived from vector presence: a chunk is indexed
    when its Qdrant point (id == ``id_chunk``) exists.
    """
    if not chunk_ids:
        return set()
    try:
        from qdrant_client import QdrantClient

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        collection = os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks")
        client = QdrantClient(host=host, port=port, timeout=5)
        points = client.retrieve(
            collection_name=collection,
            ids=list(chunk_ids),
            with_payload=False,
        )
        return {int(point.id) for point in points}
    except Exception as exc:
        logger.warning(
            "Qdrant unreachable while computing 'indexed' flag: %s", exc
        )
        return set()


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

    Joins through ``document_chunks`` to count chunks per document.
    The ``indexed`` field is derived from the presence of the document's
    chunks in Qdrant (the ``gmao`` schema has no ``statut_indexation``).
    """
    engine = _get_mysql_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    d.id_document,
                    d.nom_fichier,
                    COALESCE(d.type_fichier, 'document') AS type_fichier,
                    COUNT(dc.id_chunk) AS chunks_count,
                    d.id_equipement
                FROM documents d
                LEFT JOIN document_chunks dc ON dc.id_document = d.id_document
                GROUP BY d.id_document, d.nom_fichier, d.type_fichier, d.id_equipement
                ORDER BY d.id_document DESC
            """))
            rows = result.fetchall()

            # Collect each document's chunk ids, then check which exist
            # in Qdrant to derive the ``indexed`` flag.
            chunk_map: dict[int, list[int]] = {}
            chunk_rows = conn.execute(text(
                "SELECT id_document, id_chunk FROM document_chunks"
            )).fetchall()
            for doc_id, chunk_id in chunk_rows:
                chunk_map.setdefault(doc_id, []).append(chunk_id)

            all_chunk_ids = [
                cid for ids in chunk_map.values() for cid in ids
            ]
            present = _qdrant_present_chunk_ids(all_chunk_ids)

            documents = []
            for row in rows:
                doc_id = row[0]
                doc_chunk_ids = chunk_map.get(doc_id, [])
                documents.append(
                    DocumentSummary(
                        id=doc_id,
                        name=row[1] or "unknown",
                        source_type=row[2] or "document",
                        id_equipement=row[4],
                        chunks_count=row[3] or 0,
                        indexed=bool(doc_chunk_ids)
                        and all(cid in present for cid in doc_chunk_ids),
                    )
                )

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

    The ``gmao`` schema stores chunk content directly in
    ``document_chunks`` (no ``chunk_rag``/junction split), so the chunks
    are read straight from that table.  ``indexed`` is derived from
    Qdrant presence.
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
                    d.titre,
                    d.description,
                    d.id_equipement
                FROM documents d
                WHERE d.id_document = :doc_id
            """), {"doc_id": document_id})
            doc_row = doc_result.fetchone()

            if doc_row is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document {document_id} not found.",
                )

            # --- Fetch chunks directly from document_chunks ---
            chunks_result = conn.execute(text("""
                SELECT
                    c.id_chunk,
                    c.contenu,
                    c.ordre_chunk,
                    c.id_document
                FROM document_chunks c
                WHERE c.id_document = :doc_id
                ORDER BY c.ordre_chunk ASC
            """), {"doc_id": document_id})
            chunk_rows = chunks_result.fetchall()

            chunk_ids = [row[0] for row in chunk_rows]
            present = _qdrant_present_chunk_ids(chunk_ids)

            document = DocumentSummary(
                id=doc_row[0],
                name=doc_row[1] or "unknown",
                source_type=doc_row[2] or "document",
                id_equipement=doc_row[5],
                chunks_count=len(chunk_rows),
                indexed=bool(chunk_ids)
                and all(cid in present for cid in chunk_ids),
            )

            chunks = [
                RetrievedChunkSchema(
                    chunk_id=str(row[0]),
                    content=row[1] or "",
                    score=0.0,
                    rank=int(row[2] or 0),
                    source_name=document.name,
                    source_type="document",
                    id_document=row[3],
                    id_panne=None,
                    id_equipement=doc_row[5],
                    retrieval_strategy="",
                )
                for row in chunk_rows
            ]

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
# Document deletion helper (shared with the ingest layer)
# =====================================================================

def delete_document_by_id(engine: object, document_id: int) -> int:
    """Delete a document row and its chunks (MySQL + Qdrant).

    In the ``gmao`` schema chunk content lives directly in
    ``document_chunks`` (``id_chunk``, ``contenu``, ... ``id_document``).
    The chunk rows are deleted explicitly (to keep an accurate count)
    and the corresponding Qdrant points as well; deleting the document
    row cascades to any remaining chunks.

    Returns the number of chunks deleted from ``document_chunks``.
    """
    with engine.begin() as conn:
        chunk_ids_result = conn.execute(
            text("SELECT id_chunk FROM document_chunks WHERE id_document = :doc_id"),
            {"doc_id": document_id},
        )
        chunk_ids = [row[0] for row in chunk_ids_result.fetchall()]

        deleted_chunks = 0
        if chunk_ids:
            placeholders = ", ".join(f":id_{i}" for i in range(len(chunk_ids)))
            params = {f"id_{i}": cid for i, cid in enumerate(chunk_ids)}
            delete_result = conn.execute(
                text(f"DELETE FROM document_chunks WHERE id_chunk IN ({placeholders})"),
                params,
            )
            deleted_chunks = delete_result.rowcount

    # Qdrant deletion is tolerant — a failure does not abort the MySQL work.
    _delete_qdrant_points(chunk_ids)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM documents WHERE id_document = :doc_id"),
            {"doc_id": document_id},
        )

    return deleted_chunks


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

    In the ``gmao`` schema chunk content lives directly in
    ``document_chunks`` (id_chunk, contenu, ...  id_document) with an
    ``ON DELETE CASCADE`` from ``documents``, so deleting the document
    row removes its chunks; the explicit delete below keeps the
    ``deleted_chunks`` count accurate and is FK-safe either way.
    """
    engine = _get_mysql_engine()
    try:
        with engine.begin() as conn:
            # --- Check document exists ---
            result = conn.execute(
                text("SELECT COUNT(*) FROM documents WHERE id_document = :doc_id"),
                {"doc_id": document_id},
            )
            if result.scalar() == 0:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document {document_id} not found.",
                )

        deleted_chunks = delete_document_by_id(engine, document_id)

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

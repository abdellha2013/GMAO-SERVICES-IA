"""Qdrant-based vector retrieval with MySQL hydration."""
from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from threading import RLock
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.engine import Engine

from app.exceptions import (
    IncompatibleEmbeddingModelError,
    RetrievalConnectionError,
    RetrievalExecutionError,
    RetrievalValidationError,
)
from app.models.retrieval import RetrievalFilter, RetrievedChunk
from app.retrieval.base import RetrievalStrategy

logger = logging.getLogger(__name__)

# Load env once at import time, not per strategy instantiation.
load_dotenv()


# ---------------------------------------------------------------------------
# Connection caches (§1.5 — mirror SentenceTransformerEmbedding._model_cache)
# ---------------------------------------------------------------------------
_qdrant_lock = RLock()
_qdrant_clients: dict[str, QdrantClient] = {}

_engine_lock = RLock()
_engines: dict[str, Engine] = {}


def _get_qdrant_client(host: str, port: int) -> QdrantClient:
    key = f"{host}:{port}"
    client = _qdrant_clients.get(key)
    if client is not None:
        return client
    with _qdrant_lock:
        client = _qdrant_clients.get(key)
        if client is not None:
            return client
        client = QdrantClient(host=host, port=port)
        _qdrant_clients[key] = client
        logger.info("Qdrant client cached for %s.", key)
        return client


def _get_engine(dsn: str) -> Engine:
    engine = _engines.get(dsn)
    if engine is not None:
        return engine
    with _engine_lock:
        engine = _engines.get(dsn)
        if engine is not None:
            return engine
        engine = create_engine(dsn)
        _engines[dsn] = engine
        logger.info("SQLAlchemy engine cached for DSN (truncated).")
        return engine


def chunk_from_row(
    row: dict, score: float, rank: int, strategy_name: str
) -> RetrievedChunk:
    """Build a :class:`RetrievedChunk` from a hydrated MySQL row.

    This is the shared helper used by ``QdrantVectorRetrieval`` and
    ``HybridRetrieval`` (avoids accessing private members cross-class).
    """
    return RetrievedChunk(
        chunk_id=str(row["id_chunk"]),
        content=row["contenu"],
        score=score,
        rank=rank,
        source_name=row["source_name"],
        source_type=row["source_type"],
        id_document=row["id_document"],
        id_panne=row["id_panne"],
        id_equipement=row["id_equipement"],
        metadata={"id_chunk": row["id_chunk"]},
        retrieval_strategy=strategy_name,
    )


class QdrantVectorRetrieval(RetrievalStrategy):
    """Vector search with read-only MySQL hydration.

    MySQLStorage stores chunks in the fused ``document_chunks`` table of
    the local ``gmao`` schema (content + ``id_document`` in one row);
    Qdrant stores ``id_chunk``, ``type_source`` and ``id_equipement``.
    Candidates are hydrated in one MySQL ``SELECT``.  Filters unavailable
    in Qdrant are applied by that SELECT.  Pannes are not indexed in the
    local schema, so ``id_panne`` filtered queries always return nothing.

    .. note::

       Filtering by ``id_document`` is applied **after**
       Qdrant has already truncated to ``top_k`` candidates.  When
       combined with a small ``top_k`` this can silently drop relevant
       chunks that belong to the requested document but were ranked below
       the cutoff by the vector search.  Oversampling (×4) mitigates this
       but does not guarantee completeness.  See RETRIEVAL.md for details.
    """

    name = "qdrant"

    OVERSAMPLE_FACTOR = 4

    def __init__(
        self,
        *,
        collection_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        dsn: str | None = None,
        **_: object,
    ) -> None:
        self.collection_name = (
            collection_name
            or os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks")
        )

        self.dsn = dsn or os.getenv("MYSQL_DSN") or self._dsn_from_env()

        _host = host or os.getenv("QDRANT_HOST", "localhost")
        _port = port or int(os.getenv("QDRANT_PORT", "6333"))
        try:
            self.client = _get_qdrant_client(_host, _port)
        except Exception as exc:
            raise RetrievalConnectionError(
                message="Unable to connect to Qdrant.",
                original=exc,
            ) from exc

    @staticmethod
    def _dsn_from_env() -> str | None:
        host = os.getenv("GMAO_DB_HOST")
        user = os.getenv("GMAO_DB_USER")
        database = os.getenv("GMAO_DB_NAME")
        if not all((host, user, database)):
            return None
        password = os.getenv("GMAO_DB_PASSWORD", "")
        port = os.getenv("GMAO_DB_PORT", "3306")
        return (
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        )

    # ------------------------------------------------------------------
    # supports
    # ------------------------------------------------------------------
    def supports(self, filters: RetrievalFilter) -> bool:
        """Qdrant supports every filter defined in ``RetrievalFilter``.

        Filters that are absent from the Qdrant payload (``id_document``)
        are forwarded to MySQL during hydration.
        """
        return True

    # ------------------------------------------------------------------
    # filter builder
    # ------------------------------------------------------------------
    def _filter(self, filters: RetrievalFilter) -> Filter | None:
        must: list[FieldCondition] = []

        if filters.id_equipement is not None:
            must.append(
                FieldCondition(
                    key="id_equipement",
                    match=MatchValue(value=filters.id_equipement),
                )
            )

        if filters.source_type is not None:
            qdrant_source = (
                "Document" if filters.source_type == "document" else "Panne"
            )
            must.append(
                FieldCondition(
                    key="type_source",
                    match=MatchValue(value=qdrant_source),
                )
            )
        elif filters.id_document is not None and filters.id_panne is None:
            must.append(
                FieldCondition(
                    key="type_source",
                    match=MatchValue(value="Document"),
                )
            )
        elif filters.id_panne is not None and filters.id_document is None:
            must.append(
                FieldCondition(
                    key="type_source",
                    match=MatchValue(value="Panne"),
                )
            )

        return Filter(must=must) if must else None

    # ------------------------------------------------------------------
    # dimension check helper (§1.11)
    # ------------------------------------------------------------------
    def _check_dimension(
        self, query_vector: Sequence[float]
    ) -> None:
        info = self.client.get_collection(self.collection_name)
        vectors = info.config.params.vectors

        # Named vectors: dict[str, VectorParams]
        if isinstance(vectors, dict):
            if not vectors:
                raise RetrievalExecutionError(
                    message=(
                        "Collection has no vector definitions."
                    ),
                    details={"collection": self.collection_name},
                )
            # Check the first (and typically only) named vector.
            first_vp = next(iter(vectors.values()))
            size = getattr(first_vp, "size", None)
        else:
            size = getattr(vectors, "size", None)

        if size is not None and size != len(query_vector):
            raise IncompatibleEmbeddingModelError(
                details={
                    "collection_dimension": size,
                    "query_dimension": len(query_vector),
                },
            )

    # ------------------------------------------------------------------
    # retrieve
    # ------------------------------------------------------------------
    def retrieve(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int,
        filters: RetrievalFilter,
        query_text: str,
    ) -> list[RetrievedChunk]:
        oversampled_k = top_k * self.OVERSAMPLE_FACTOR

        try:
            self._check_dimension(query_vector)

            points = self.client.query_points(
                collection_name=self.collection_name,
                query=list(query_vector),
                query_filter=self._filter(filters),
                limit=oversampled_k,
                with_payload=True,
            ).points
        except IncompatibleEmbeddingModelError:
            raise
        except ResponseHandlingException as exc:
            raise RetrievalExecutionError(
                message="Qdrant query failed.",
                original=exc,
            ) from exc

        # Build IDs — wrap conversion errors.
        try:
            ids = [
                int((point.payload or {}).get("id_chunk", point.id))
                for point in points
            ]
        except (ValueError, TypeError) as exc:
            raise RetrievalExecutionError(
                message="Failed to extract chunk IDs from Qdrant response.",
                original=exc,
            ) from exc

        rows = self._hydrate(ids, filters)
        by_id: dict[int, dict] = {row["id_chunk"]: row for row in rows}

        result: list[RetrievedChunk] = []
        for point in points:
            chunk_id_raw = (point.payload or {}).get(
                "id_chunk", point.id
            )
            try:
                chunk_id_int = int(chunk_id_raw)
            except (ValueError, TypeError):
                continue

            row = by_id.get(chunk_id_int)
            if row is None:
                continue

            # §1.2/1.3: apply min_score AFTER oversampling, not after
            # Qdrant's native limit.
            if (
                filters.min_score is not None
                and point.score < filters.min_score
            ):
                continue

            result.append(
                chunk_from_row(
                    row,
                    float(point.score),
                    len(result) + 1,
                    self.name,
                )
            )

        # Truncate to original top_k *after* filtering.
        return result[:top_k]

    # ------------------------------------------------------------------
    # MySQL hydration
    # ------------------------------------------------------------------
    def _hydrate(
        self, ids: list[int], filters: RetrievalFilter
    ) -> list[dict]:
        if not ids:
            return []

        # §1.10: missing DSN is a configuration error, not a connection error.
        if not self.dsn:
            raise RetrievalValidationError(
                message=(
                    "MYSQL_DSN must be configured to hydrate "
                    "Qdrant results."
                ),
            )

        clauses: list[str] = ["c.id_chunk IN :ids"]
        params: dict[str, Any] = {"ids": tuple(ids)}

        if filters.id_document is not None:
            clauses.append("c.id_document = :id_document")
            params["id_document"] = filters.id_document
        if filters.id_equipement is not None:
            clauses.append("d.id_equipement = :id_equipement")
            params["id_equipement"] = filters.id_equipement
        if filters.source_type is not None:
            clauses.append(
                "LOWER(COALESCE(d.type_fichier, 'document')) "
                "= :source_type"
            )
            params["source_type"] = filters.source_type

        sql = (
            "SELECT c.id_chunk, c.contenu, "
            "c.id_document, NULL AS id_panne, "
            "d.id_equipement, "
            "d.nom_fichier source_name, "
            "COALESCE(LOWER(d.type_fichier), 'document') source_type "
            "FROM document_chunks c "
            "LEFT JOIN documents d ON d.id_document = c.id_document "
            "WHERE " + " AND ".join(clauses)
        )

        try:
            engine = _get_engine(self.dsn)
            with engine.connect() as connection:
                statement = text(sql).bindparams(
                    bindparam("ids", expanding=True)
                )
                return [
                    dict(row)
                    for row in connection.execute(
                        statement, params
                    ).mappings()
                ]
        except OperationalError as exc:
            raise RetrievalConnectionError(
                message="Unable to connect to MySQL.",
                original=exc,
            ) from exc
        except SQLAlchemyError as exc:
            raise RetrievalExecutionError(
                message="Unable to hydrate Qdrant results from MySQL.",
                original=exc,
            ) from exc

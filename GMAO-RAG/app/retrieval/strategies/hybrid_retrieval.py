"""Hybrid retrieval fusing vector and lexical results via RRF."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.exceptions import (
    RetrievalConnectionError,
    RetrievalExecutionError,
    RetrievalValidationError,
)
from app.models.retrieval import RetrievalFilter, RetrievedChunk
from app.retrieval.base import RetrievalStrategy
from app.retrieval.strategies.qdrant_retrieval import (
    QdrantVectorRetrieval,
    _get_engine,
    chunk_from_row,
)

logger = logging.getLogger(__name__)


class HybridRetrieval(RetrievalStrategy):
    """Fuse vector and lexical results with Reciprocal Rank Fusion.

    Degrades to pure vector search when MySQL is unreachable (connection or
    execution error only — validation errors propagate as-is).
    """

    name = "hybrid"

    OVERSAMPLE_FACTOR = 4

    def __init__(
        self,
        *,
        rrf_k: int = 60,
        **options: object,
    ) -> None:
        self.rrf_k = rrf_k
        self.vector = QdrantVectorRetrieval(**options)

    def supports(self, filters: RetrievalFilter) -> bool:
        return self.vector.supports(filters)

    def retrieve(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int,
        filters: RetrievalFilter,
        query_text: str,
    ) -> list[RetrievedChunk]:
        oversampled_k = top_k * self.OVERSAMPLE_FACTOR

        vector = self.vector.retrieve(
            query_vector,
            top_k=oversampled_k,
            filters=filters,
            query_text=query_text,
        )

        # §1.7: only catch connection/execution errors, not all
        # RetrievalError (which includes validation errors).
        try:
            lexical = self._lexical(
                query_text, top_k=oversampled_k, filters=filters
            )
        except (RetrievalConnectionError, RetrievalExecutionError):
            logger.warning(
                "MySQL unavailable — degrading to vector-only search."
            )
            lexical = []

        merged: dict[str, tuple[RetrievedChunk, float, dict[str, Any]]] = {}

        for label, items in (
            ("vector_rank", vector),
            ("lexical_rank", lexical),
        ):
            for item in items:
                base, score, debug = merged.get(
                    item.chunk_id, (item, 0.0, {})
                )
                debug[label] = item.rank
                merged[item.chunk_id] = (
                    base,
                    score + 1.0 / (self.rrf_k + item.rank),
                    debug,
                )

        ordered = sorted(
            merged.values(), key=lambda value: value[1], reverse=True
        )[:top_k]

        return [
            replace(
                item,
                score=score,
                rank=index,
                metadata={
                    **item.metadata,
                    "retrieval_debug": debug,
                },
                retrieval_strategy=self.name,
            )
            for index, (item, score, debug) in enumerate(ordered, 1)
        ]

    def _lexical(
        self,
        query_text: str,
        *,
        top_k: int,
        filters: RetrievalFilter,
    ) -> list[RetrievedChunk]:
        """Perform a read-only lexical lookup on ``chunk_rag.contenu``."""
        # §1.10: missing DSN → RetrievalValidationError, not ConnectionError.
        if not self.vector.dsn:
            raise RetrievalValidationError(
                message=(
                    "MYSQL_DSN must be configured for "
                    "hybrid retrieval."
                ),
            )

        # §1.9: escape LIKE meta-characters.
        escaped = (
            query_text.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        clauses: list[str] = ["c.contenu LIKE :query ESCAPE '\\\\'"]
        params: dict[str, Any] = {
            "query": f"%{escaped}%",
            "limit": top_k,
        }

        if filters.id_document is not None:
            clauses.append("d.id_document = :id_document")
            params["id_document"] = filters.id_document
        if filters.id_panne is not None:
            clauses.append("p.id_panne = :id_panne")
            params["id_panne"] = filters.id_panne
        if filters.id_equipement is not None:
            clauses.append(
                "COALESCE(d.id_equipement, p.id_equipement) "
                "= :id_equipement"
            )
            params["id_equipement"] = filters.id_equipement
        if filters.source_type is not None:
            clauses.append(
                "LOWER(COALESCE(d.type_fichier, 'panne')) "
                "= :source_type"
            )
            params["source_type"] = filters.source_type

        sql = (
            "SELECT c.id_chunk, c.contenu, "
            "d.id_document, p.id_panne, "
            "COALESCE(d.id_equipement, p.id_equipement) id_equipement, "
            "COALESCE(d.nom_fichier, CONCAT('panne:', p.id_panne)) "
            "source_name, "
            "COALESCE(LOWER(d.type_fichier), 'panne') source_type "
            "FROM chunk_rag c "
            "LEFT JOIN document_chunk dc ON dc.id_chunk = c.id_chunk "
            "LEFT JOIN document d ON d.id_document = dc.id_document "
            "LEFT JOIN panne_chunk pc ON pc.id_chunk = c.id_chunk "
            "LEFT JOIN panne p ON p.id_panne = pc.id_panne "
            "WHERE " + " AND ".join(clauses) + " LIMIT :limit"
        )

        try:
            engine = _get_engine(self.vector.dsn)
            with engine.connect() as connection:
                rows = [
                    dict(row)
                    for row in connection.execute(
                        text(sql), params
                    ).mappings()
                ]
        except OperationalError as exc:
            raise RetrievalConnectionError(
                message="Unable to connect to MySQL.",
                original=exc,
            ) from exc
        except SQLAlchemyError as exc:
            raise RetrievalExecutionError(
                message="MySQL lexical query failed.",
                original=exc,
            ) from exc

        return [
            chunk_from_row(
                row, 1.0 / index, index, self.name
            )
            for index, row in enumerate(rows, 1)
        ]

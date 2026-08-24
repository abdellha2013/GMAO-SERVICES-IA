"""Orchestrator that wires embedding + retrieval strategies."""
from __future__ import annotations

import math
import logging
from typing import Any

from app.embedding.registry import EmbeddingRegistry
from app.exceptions import (
    EmptyQueryError,
    GMAOError,
    RetrievalExecutionError,
    RetrievalValidationError,
)
from app.models.retrieval import RetrievalFilter, RetrievalReport
from app.retrieval.registry import RetrievalRegistry

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """Retrieve chunks using the query encoder, never the passage encoder.

    .. important::

       ``embedding_options`` **must** match the options used at indexation
       (model, revision, device, prefixes, …).  A mismatch produces query
       vectors in a different space from the stored vectors, yielding silent
       ranking degradation that ``IncompatibleEmbeddingModelError`` cannot
       detect (dimension stays the same while semantics diverge).

       Ideally both ``app.embedding`` and ``app.retrieval`` read from a
       single source of truth (e.g. shared env vars) to avoid manual
       duplication.
    """

    def __init__(
        self,
        registry: RetrievalRegistry,
        embedding_registry: EmbeddingRegistry,
        *,
        strategy_name: str = "qdrant",
        embedding_strategy_name: str = "sentence-transformer",
        embedding_options: dict[str, Any] | None = None,
        default_top_k: int = 5,
        max_top_k: int = 50,
        score_threshold: float | None = None,
        **strategy_options: Any,
    ) -> None:
        # --- type guards ---------------------------------------------------
        if (
            not isinstance(registry, RetrievalRegistry)
            or not isinstance(embedding_registry, EmbeddingRegistry)
        ):
            raise RetrievalValidationError(
                message=(
                    "registry arguments must be retrieval and embedding "
                    "registries."
                ),
            )
        if (
            not isinstance(default_top_k, int)
            or isinstance(default_top_k, bool)
            or default_top_k <= 0
            or not isinstance(max_top_k, int)
            or isinstance(max_top_k, bool)
            or max_top_k <= 0
        ):
            raise RetrievalValidationError(
                message="top_k defaults must be positive integers.",
            )
        if score_threshold is not None and (
            isinstance(score_threshold, bool)
            or not isinstance(score_threshold, (int, float))
            or not math.isfinite(score_threshold)
        ):
            raise RetrievalValidationError(
                message="score_threshold must be a finite number or None.",
            )
        if (
            not isinstance(strategy_name, str)
            or not strategy_name.strip()
            or not isinstance(embedding_strategy_name, str)
            or not embedding_strategy_name.strip()
        ):
            raise RetrievalValidationError(
                message="strategy names must be non-empty strings.",
            )
        if embedding_options is not None and not isinstance(
            embedding_options, dict
        ):
            raise RetrievalValidationError(
                message="embedding_options must be a dict or None.",
            )

        # --- store ---------------------------------------------------------
        self.registry = registry
        self.embedding_registry = embedding_registry
        self.strategy_name = strategy_name.strip().lower()
        self.embedding_strategy_name = embedding_strategy_name.strip().lower()
        self.embedding_options = dict(embedding_options) if embedding_options else {}
        self.default_top_k = default_top_k
        self.max_top_k = max_top_k
        self.score_threshold = score_threshold
        self.options = dict(strategy_options)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: RetrievalFilter | None = None,
        strategy_name: str | None = None,
    ) -> RetrievalReport:
        if not isinstance(query, str) or not query.strip():
            raise EmptyQueryError()
        if top_k is not None and (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or top_k <= 0
        ):
            raise RetrievalValidationError(
                message="top_k must be a positive integer.",
            )
        if filters is not None and not isinstance(filters, RetrievalFilter):
            raise RetrievalValidationError(
                message="filters must be a RetrievalFilter or None.",
            )
        if strategy_name is not None and (
            not isinstance(strategy_name, str)
            or not strategy_name.strip()
        ):
            raise RetrievalValidationError(
                message="strategy_name must be a non-empty string or None.",
            )

        effective_filters = filters or RetrievalFilter()
        effective_top_k = min(
            top_k or self.default_top_k, self.max_top_k
        )
        name = (strategy_name or self.strategy_name).strip().lower()

        try:
            encoder_cls = self.embedding_registry.get(
                self.embedding_strategy_name
            )
            encoder = encoder_cls(**self.embedding_options)
            embed_query = getattr(encoder, "embed_query", None)
            if not callable(embed_query):
                raise RetrievalValidationError(
                    message=(
                        "Embedding strategy does not support "
                        "query encoding."
                    ),
                )
            vector = embed_query(query.strip())

            strategy_cls = self.registry.get(name)
            strategy = strategy_cls(**self.options)
            if not strategy.supports(effective_filters):
                raise RetrievalValidationError(
                    message="Retrieval strategy does not support these filters.",
                    details={"strategy": name},
                )

            candidates = strategy.retrieve(
                vector,
                top_k=effective_top_k,
                filters=effective_filters,
                query_text=query.strip(),
            )
        except GMAOError:
            raise
        except Exception as exc:
            raise RetrievalExecutionError(
                message=f"Retrieval failed for strategy '{name}'.",
                details={"strategy": name},
                original=exc,
            ) from exc

        results = tuple(
            item
            for item in candidates
            if self.score_threshold is None
            or item.score >= self.score_threshold
        )

        logger.info(
            "Retrieval done (strategy=%s, candidates=%d, returned=%d).",
            name,
            len(candidates),
            len(results),
        )

        return RetrievalReport(
            query=query.strip(),
            strategy_name=name,
            results=results,
            total_candidates=len(candidates),
        )

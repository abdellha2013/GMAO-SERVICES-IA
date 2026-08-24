"""High-level orchestration for candidate reranking."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from app.exceptions import (
    GMAOError,
    RerankerValidationError,
    RerankingError,
)
from app.models.reranking import RankedChunk
from app.models.retrieval import RetrievedChunk
from app.reranker.base import RerankerStrategy
from app.reranker.registry import RerankerRegistry

logger = logging.getLogger(__name__)


class RerankerOrchestrator:
    """Resolve a reranker strategy and rerank retrieved candidates.

    The orchestrator validates inputs, resolves the strategy from the
    registry, instantiates it with stored options, and delegates the
    actual reranking.  It must not contain Cross-Encoder implementation
    details.
    """

    def __init__(
        self,
        registry: RerankerRegistry,
        *,
        strategy_name: str = "cross-encoder",
        default_top_k: int = 10,
        max_top_k: int = 50,
        **strategy_options: Any,
    ) -> None:
        if not isinstance(registry, RerankerRegistry):
            raise RerankerValidationError(
                message="registry must be a RerankerRegistry instance.",
                details={"received_type": type(registry).__name__},
            )
        if not isinstance(strategy_name, str) or not strategy_name.strip():
            raise RerankerValidationError(message="strategy_name must be a non-empty string.")
        if not isinstance(default_top_k, int) or isinstance(default_top_k, bool) or default_top_k <= 0:
            raise RerankerValidationError(message="default_top_k must be a positive integer.")
        if not isinstance(max_top_k, int) or isinstance(max_top_k, bool) or max_top_k <= 0:
            raise RerankerValidationError(message="max_top_k must be a positive integer.")

        self._registry = registry
        self._strategy_name = strategy_name.strip().lower()
        self._default_top_k = default_top_k
        self._max_top_k = max_top_k
        self._strategy_options = dict(strategy_options)

    @property
    def registry(self) -> RerankerRegistry:
        return self._registry

    @property
    def strategy_name(self) -> str:
        return self._strategy_name

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        *,
        top_k: int | None = None,
        strategy_name: str | None = None,
    ) -> list[RankedChunk]:
        if not isinstance(query, str) or not query.strip():
            raise RerankerValidationError(message="query must be a non-empty string.")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise RerankerValidationError(message="candidates must be a sequence of RetrievedChunk.")
        if top_k is not None and (isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0):
            raise RerankerValidationError(message="top_k must be a positive integer.")
        if strategy_name is not None and (not isinstance(strategy_name, str) or not strategy_name.strip()):
            raise RerankerValidationError(message="strategy_name must be a non-empty string or None.")

        effective_top_k = min(top_k or self._default_top_k, self._max_top_k)
        name = (strategy_name or self._strategy_name).strip().lower()

        if not candidates:
            logger.info("No candidates to rerank — returning empty list.")
            return []

        try:
            strategy_cls = self._registry.get(name)
            strategy: RerankerStrategy = strategy_cls(**self._strategy_options)

            if not strategy.supports(query, candidates):
                raise RerankerValidationError(
                    message="Reranker strategy does not support these inputs.",
                    details={"strategy": name},
                )

            results = strategy.rerank(query, candidates, top_k=effective_top_k)
        except GMAOError:
            raise
        except Exception as exc:
            raise RerankingError(
                message="Reranking strategy execution failed.",
                details={"strategy_name": name},
                original=exc,
            ) from exc

        if not isinstance(results, list):
            raise RerankerValidationError(
                message="rerank() must return a list of RankedChunk.",
                details={"received_type": type(results).__name__},
            )

        for index, item in enumerate(results):
            if not isinstance(item, RankedChunk):
                raise RerankerValidationError(
                    message="rerank() must return only RankedChunk objects.",
                    details={"index": index, "received_type": type(item).__name__},
                )

        return results

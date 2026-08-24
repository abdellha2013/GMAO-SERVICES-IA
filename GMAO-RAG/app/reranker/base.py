"""Abstract contract for reranker strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from app.exceptions import InvalidRerankerStrategyError
from app.models.reranking import RankedChunk
from app.models.retrieval import RetrievedChunk


class RerankerStrategy(ABC):
    """Base class every reranker strategy must inherit from."""

    name: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.name, str) or not cls.name.strip():
            raise InvalidRerankerStrategyError(
                message=f"{cls.__name__} must define a non-empty class attribute 'name'.",
                details={"strategy_class": cls.__name__},
            )

    @abstractmethod
    def supports(self, query: str, candidates: Sequence[RetrievedChunk]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        *,
        top_k: int,
        **kwargs: Any,
    ) -> list[RankedChunk]:
        raise NotImplementedError

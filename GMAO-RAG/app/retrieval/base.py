"""Base ABC for retrieval strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.exceptions import InvalidRetrievalStrategyError
from app.models.retrieval import RetrievalFilter, RetrievedChunk


class RetrievalStrategy(ABC):
    """Abstract contract every retrieval strategy must satisfy."""

    name: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.name, str) or not cls.name.strip():
            raise InvalidRetrievalStrategyError(
                message=(
                    f"{cls.__name__} must define a non-empty "
                    "class attribute 'name'."
                ),
                details={"strategy_class": cls.__name__},
            )

    @abstractmethod
    def supports(self, filters: RetrievalFilter) -> bool:
        """Return True if this strategy can handle the given filters."""
        raise NotImplementedError

    @abstractmethod
    def retrieve(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int,
        filters: RetrievalFilter,
        query_text: str,
    ) -> list[RetrievedChunk]:
        """Execute a retrieval query and return ranked chunks."""
        raise NotImplementedError

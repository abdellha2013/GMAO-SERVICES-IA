"""Abstract contract for LLM strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from app.exceptions import InvalidLLMStrategyError
from app.models.llm import LLMResponse
from app.models.reranking import RankedChunk


class LLMStrategy(ABC):
    """Base class every LLM strategy must inherit from."""

    name: str = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.name, str) or not cls.name.strip():
            raise InvalidLLMStrategyError(
                message=f"{cls.__name__} must define a non-empty class attribute 'name'.",
                details={"strategy_class": cls.__name__},
            )

    @abstractmethod
    def supports(self, query: str, candidates: Sequence[RankedChunk]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        query: str,
        candidates: Sequence[RankedChunk],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> LLMResponse:
        raise NotImplementedError

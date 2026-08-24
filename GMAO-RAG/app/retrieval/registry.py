"""Registry for retrieval strategies."""
from __future__ import annotations

from app.exceptions import (
    InvalidRetrievalStrategyError,
    RetrievalStrategyNotRegisteredError,
    RetrievalValidationError,
)
from app.retrieval.base import RetrievalStrategy


class RetrievalRegistry:
    """Mapping from strategy name to its class (not an instance)."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[RetrievalStrategy]] = {}

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise RetrievalValidationError(
                message="strategy name must be a non-empty string.",
            )
        return name.strip().lower()

    def register(self, strategy: type[RetrievalStrategy]) -> None:
        if not isinstance(strategy, type) or not issubclass(
            strategy, RetrievalStrategy
        ):
            raise InvalidRetrievalStrategyError(
                details={"received_type": type(strategy).__name__},
            )
        name = self._name(strategy.name)
        if name in self._strategies:
            raise RetrievalValidationError(
                message="A retrieval strategy is already registered for this name.",
                details={"name": name},
            )
        self._strategies[name] = strategy

    def get(self, name: str) -> type[RetrievalStrategy]:
        normalized = self._name(name)
        try:
            return self._strategies[normalized]
        except KeyError as exc:
            raise RetrievalStrategyNotRegisteredError(
                details={"name": normalized},
            ) from exc

    def has(self, name: object) -> bool:
        return (
            isinstance(name, str)
            and bool(name.strip())
            and name.strip().lower() in self._strategies
        )

    def unregister(self, name: str) -> None:
        normalized = self._name(name)
        if normalized not in self._strategies:
            raise RetrievalStrategyNotRegisteredError(
                details={"name": normalized},
            )
        del self._strategies[normalized]

    def clear(self) -> None:
        self._strategies.clear()

    def supported_strategies(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

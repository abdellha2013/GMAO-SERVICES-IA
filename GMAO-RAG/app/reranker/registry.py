"""Registry mapping reranker strategy names to strategy classes."""
from __future__ import annotations

from app.exceptions import (
    InvalidRerankerStrategyError,
    RerankerStrategyNotRegisteredError,
    RerankerValidationError,
)
from app.reranker.base import RerankerStrategy


class RerankerRegistry:
    """Store reranker strategy classes under their normalized names."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[RerankerStrategy]] = {}

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise RerankerValidationError(message="strategy name must be a non-empty string.")
        return name.strip().lower()

    def register(self, strategy: type[RerankerStrategy]) -> None:
        if not isinstance(strategy, type) or not issubclass(strategy, RerankerStrategy):
            raise InvalidRerankerStrategyError(details={"received_type": type(strategy).__name__})
        name = self._name(strategy.name)
        if name in self._strategies:
            raise RerankerValidationError(
                message="A reranker strategy is already registered for this name.",
                details={"name": name},
            )
        self._strategies[name] = strategy

    def get(self, name: str) -> type[RerankerStrategy]:
        normalized = self._name(name)
        try:
            return self._strategies[normalized]
        except KeyError as exc:
            raise RerankerStrategyNotRegisteredError(details={"name": normalized}) from exc

    def has(self, name: object) -> bool:
        return isinstance(name, str) and bool(name.strip()) and name.strip().lower() in self._strategies

    def unregister(self, name: str) -> None:
        normalized = self._name(name)
        if normalized not in self._strategies:
            raise RerankerStrategyNotRegisteredError(details={"name": normalized})
        del self._strategies[normalized]

    def clear(self) -> None:
        self._strategies.clear()

    def supported_strategies(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

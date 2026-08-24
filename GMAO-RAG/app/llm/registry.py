"""Registry mapping LLM strategy names to strategy classes."""
from __future__ import annotations

from app.exceptions import (
    InvalidLLMStrategyError,
    LLMStrategyNotRegisteredError,
    LLMValidationError,
)
from app.llm.base import LLMStrategy


class LLMRegistry:
    """Store LLM strategy classes under their normalized names."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[LLMStrategy]] = {}

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise LLMValidationError(message="strategy name must be a non-empty string.")
        return name.strip().lower()

    def register(self, strategy: type[LLMStrategy]) -> None:
        if not isinstance(strategy, type) or not issubclass(strategy, LLMStrategy):
            raise InvalidLLMStrategyError(details={"received_type": type(strategy).__name__})
        name = self._name(strategy.name)
        if name in self._strategies:
            raise LLMValidationError(
                message="An LLM strategy is already registered for this name.",
                details={"name": name},
            )
        self._strategies[name] = strategy

    def get(self, name: str) -> type[LLMStrategy]:
        normalized = self._name(name)
        try:
            return self._strategies[normalized]
        except KeyError as exc:
            raise LLMStrategyNotRegisteredError(details={"name": normalized}) from exc

    def has(self, name: object) -> bool:
        return isinstance(name, str) and bool(name.strip()) and name.strip().lower() in self._strategies

    def unregister(self, name: str) -> None:
        normalized = self._name(name)
        if normalized not in self._strategies:
            raise LLMStrategyNotRegisteredError(details={"name": normalized})
        del self._strategies[normalized]

    def clear(self) -> None:
        self._strategies.clear()

    def supported_strategies(self) -> tuple[str, ...]:
        return tuple(sorted(self._strategies))

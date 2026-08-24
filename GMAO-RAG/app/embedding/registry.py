"""Registry mapping embedding strategy names to strategy classes."""

from __future__ import annotations

from app.embedding.base import EmbeddingStrategy
from app.exceptions import (
    EmbeddingStrategyNotRegisteredError,
    EmbeddingValidationError,
    InvalidEmbeddingStrategyError,
)


class EmbeddingRegistry:
    """Store embedding strategy classes under their normalized names."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[EmbeddingStrategy]] = {}

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not isinstance(name, str):
            raise EmbeddingValidationError(
                message="strategy name must be a string.",
                details={"received_type": type(name).__name__},
            )

        normalized = name.strip().lower()
        if not normalized:
            raise EmbeddingValidationError(
                message="strategy name must not be empty.",
            )

        return normalized

    @staticmethod
    def _validate_strategy(strategy: type[EmbeddingStrategy]) -> None:
        if not isinstance(strategy, type):
            raise InvalidEmbeddingStrategyError(
                message="strategy must be a class.",
                details={"received_type": type(strategy).__name__},
            )

        if not issubclass(strategy, EmbeddingStrategy):
            raise InvalidEmbeddingStrategyError(
                message="strategy must inherit from EmbeddingStrategy.",
                details={
                    "strategy": getattr(strategy, "__name__", type(strategy).__name__),
                    "expected_base": "EmbeddingStrategy",
                },
            )

    def register(self, strategy: type[EmbeddingStrategy]) -> None:
        """Register a strategy class using its default instance name."""
        self._validate_strategy(strategy)

        try:
            instance = strategy()
            name = self._normalize_name(instance.name)
        except (EmbeddingValidationError, InvalidEmbeddingStrategyError):
            raise
        except Exception as exc:
            raise InvalidEmbeddingStrategyError(
                message="Unable to instantiate embedding strategy.",
                details={"strategy": strategy.__name__},
                original=exc,
            ) from exc

        if name in self._strategies:
            raise EmbeddingValidationError(
                message=f"An embedding strategy is already registered as '{name}'.",
                details={
                    "strategy": strategy.__name__,
                    "existing_strategy": self._strategies[name].__name__,
                },
            )

        self._strategies[name] = strategy

    def get(self, name: str) -> type[EmbeddingStrategy]:
        """Return the strategy class registered under ``name``."""
        normalized = self._normalize_name(name)
        try:
            return self._strategies[normalized]
        except KeyError:
            raise EmbeddingStrategyNotRegisteredError(
                message=f"No embedding strategy registered as '{normalized}'.",
                details={
                    "strategy_name": normalized,
                    "supported_strategies": self.supported_strategies(),
                },
            ) from None

    def has(self, name: str) -> bool:
        """Return ``False`` instead of raising for an invalid name."""
        return isinstance(name, str) and bool(name.strip()) and name.strip().lower() in self._strategies

    def unregister(self, name: str) -> None:
        """Remove the class associated with ``name``."""
        normalized = self._normalize_name(name)
        if normalized not in self._strategies:
            raise EmbeddingStrategyNotRegisteredError(
                message=f"No embedding strategy registered as '{normalized}'.",
                details={
                    "strategy_name": normalized,
                    "supported_strategies": self.supported_strategies(),
                },
            )
        del self._strategies[normalized]

    def clear(self) -> None:
        """Remove all registered strategies."""
        self._strategies.clear()

    def supported_strategies(self) -> tuple[str, ...]:
        """Return registered strategy names in deterministic order."""
        return tuple(sorted(self._strategies))

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __len__(self) -> int:
        return len(self._strategies)

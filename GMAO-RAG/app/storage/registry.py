"""Registry of available storage strategies.

The registry maps a normalized strategy name (lower-case, stripped) to
its strategy *class*. Classes are intentionally never instantiated by
the registry: instantiating a strategy such as
:class:`~app.storage.strategies.mysql_storage.MySQLStorage` opens a
database connection and validates environment variables, which must
not be a side effect of simply registering or unregistering a strategy
(for example at import time, in tests, or in a local environment
without a configured database).
"""
from __future__ import annotations

from app.exceptions import (
    InvalidStorageStrategyError,
    StorageStrategyNotRegisteredError,
    StorageValidationError,
)
from .base import StorageStrategy


class StorageRegistry:
    """Simple name-to-class registry for :class:`StorageStrategy` subclasses."""

    def __init__(self) -> None:
        self._strategies: dict[str, type[StorageStrategy]] = {}

    def register(self, strategy: type[StorageStrategy]) -> None:
        """Register a storage strategy class under its normalized name.

        Parameters
        ----------
        strategy:
            A concrete subclass of :class:`StorageStrategy`. The class
            is registered as-is and is never instantiated here.
        """
        if not isinstance(strategy, type) or not issubclass(strategy, StorageStrategy):
            raise InvalidStorageStrategyError(
                details={"strategy": getattr(strategy, "__name__", type(strategy).__name__)}
            )
        name = self._normalize(strategy.name)
        if not name:
            raise InvalidStorageStrategyError(
                message="Storage strategy classes must define a non-empty 'name'.",
                details={"strategy": strategy.__name__},
            )
        if name in self._strategies:
            raise StorageValidationError(
                message=f"A storage strategy is already registered as '{name}'."
            )
        self._strategies[name] = strategy

    def get(self, name: str) -> type[StorageStrategy]:
        """Return the strategy class registered under ``name``."""
        normalized = self._normalize(name)
        try:
            return self._strategies[normalized]
        except KeyError:
            raise StorageStrategyNotRegisteredError(
                details={
                    "strategy_name": name,
                    "supported_strategies": self.supported_strategies(),
                }
            ) from None

    def has(self, name: str) -> bool:
        """Return ``True`` when a strategy is registered under ``name``."""
        return isinstance(name, str) and self._normalize(name) in self._strategies

    def unregister(self, name: str) -> None:
        """Remove the strategy registered under ``name``.

        Uses the same normalization rule as :meth:`get` directly on the
        provided name, instead of instantiating the registered class to
        read its ``.name`` back.
        """
        normalized = self._normalize(name)
        if normalized not in self._strategies:
            raise StorageStrategyNotRegisteredError(
                details={
                    "strategy_name": name,
                    "supported_strategies": self.supported_strategies(),
                }
            )
        del self._strategies[normalized]

    def clear(self) -> None:
        """Remove every registered strategy."""
        self._strategies.clear()

    def supported_strategies(self) -> tuple[str, ...]:
        """Return the sorted tuple of currently registered strategy names."""
        return tuple(sorted(self._strategies))

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower() if isinstance(name, str) else ""

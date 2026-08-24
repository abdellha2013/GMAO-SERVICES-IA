"""Public entry points for the storage layer.

Exposes the storage primitives (:class:`StorageOutcome`,
:class:`StorageReport`, :class:`StorageStrategy`, :class:`StorageRegistry`,
:class:`StorageOrchestrator`) plus two convenience factories that wire the
default strategies (MySQL, Qdrant) together.
"""
from __future__ import annotations

from .base import StorageOutcome, StorageReport, StorageStrategy
from .orchestrator import StorageOrchestrator
from .registry import StorageRegistry

__all__ = [
    "StorageOutcome",
    "StorageReport",
    "StorageStrategy",
    "StorageRegistry",
    "StorageOrchestrator",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> StorageRegistry:
    """Build a :class:`StorageRegistry` pre-populated with every known strategy.

    Registering a strategy only stores its class (see
    :meth:`StorageRegistry.register`), so this never opens a database
    connection or validates environment variables -- it is safe to call
    in tests or in a local environment without a configured database.
    """
    from .strategies import ALL_STRATEGIES

    registry = StorageRegistry()
    for strategy_class in ALL_STRATEGIES:
        registry.register(strategy_class)
    return registry


def build_default_orchestrator(**options: object) -> StorageOrchestrator:
    """Build a :class:`StorageOrchestrator` using :func:`build_default_registry`."""
    return StorageOrchestrator(build_default_registry(), **options)

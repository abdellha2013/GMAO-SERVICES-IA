"""Public API for the reranker layer."""
from __future__ import annotations

from .base import RerankerStrategy
from .orchestrator import RerankerOrchestrator
from .registry import RerankerRegistry
from .strategies import ALL_STRATEGIES

__all__ = [
    "RerankerStrategy",
    "RerankerRegistry",
    "RerankerOrchestrator",
    "ALL_STRATEGIES",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> RerankerRegistry:
    """Build a registry containing every default reranker strategy."""
    registry = RerankerRegistry()
    for strategy in ALL_STRATEGIES:
        registry.register(strategy)
    return registry


def build_default_orchestrator(**options: object) -> RerankerOrchestrator:
    """Build a reranker orchestrator configured with default strategies."""
    return RerankerOrchestrator(build_default_registry(), **options)

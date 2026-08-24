"""Public API for the LLM layer."""
from __future__ import annotations

from .base import LLMStrategy
from .orchestrator import LLMOrchestrator
from .registry import LLMRegistry
from .strategies import ALL_STRATEGIES

__all__ = [
    "LLMStrategy",
    "LLMRegistry",
    "LLMOrchestrator",
    "ALL_STRATEGIES",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> LLMRegistry:
    """Build a registry containing every default LLM strategy."""
    registry = LLMRegistry()
    for strategy in ALL_STRATEGIES:
        registry.register(strategy)
    return registry


def build_default_orchestrator(**options: object) -> LLMOrchestrator:
    """Build an LLM orchestrator configured with default strategies."""
    return LLMOrchestrator(build_default_registry(), **options)

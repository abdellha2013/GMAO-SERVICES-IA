"""Public API for the embedding layer."""

from app.embedding.base import EmbeddingStrategy
from app.embedding.orchestrator import EmbeddingOrchestrator
from app.embedding.registry import EmbeddingRegistry
from app.embedding.strategies import ALL_STRATEGIES, SentenceTransformerEmbedding

__all__ = [
    "EmbeddingStrategy",
    "EmbeddingRegistry",
    "EmbeddingOrchestrator",
    "SentenceTransformerEmbedding",
    "ALL_STRATEGIES",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> EmbeddingRegistry:
    """Build a registry containing every default embedding strategy.

    Strategies are sourced from ``app.embedding.strategies.ALL_STRATEGIES``,
    so adding a new default strategy only requires updating that tuple —
    this function never needs to change.
    """
    registry = EmbeddingRegistry()
    for strategy in ALL_STRATEGIES:
        registry.register(strategy)
    return registry


def build_default_orchestrator(**strategy_options) -> EmbeddingOrchestrator:
    """Build an embedding orchestrator configured with default strategies."""
    return EmbeddingOrchestrator(
        registry=build_default_registry(),
        **strategy_options,
    )

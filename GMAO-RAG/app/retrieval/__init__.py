"""app.retrieval — Vector search layer for the GMAO RAG pipeline.

Public API
----------
- ``build_default_registry()`` → ``RetrievalRegistry``
- ``build_default_orchestrator(**options)`` → ``RetrievalOrchestrator``

.. important::

   ``embedding_options`` passed to ``build_default_orchestrator`` (or
   ``RetrievalOrchestrator`` directly) **must** match the options used
   at indexation (model, revision, device, prefixes).  A silent mismatch
   produces query vectors in a different space from the stored ones.
"""
from app.embedding import build_default_registry as build_embedding_registry

from .base import RetrievalStrategy
from .orchestrator import RetrievalOrchestrator
from .registry import RetrievalRegistry
from .strategies import ALL_STRATEGIES

__all__ = [
    "RetrievalStrategy",
    "RetrievalRegistry",
    "RetrievalOrchestrator",
    "ALL_STRATEGIES",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> RetrievalRegistry:
    """Return a registry pre-populated with every built-in strategy."""
    registry = RetrievalRegistry()
    for strategy in ALL_STRATEGIES:
        registry.register(strategy)
    return registry


def build_default_orchestrator(**options: object) -> RetrievalOrchestrator:
    """Return an orchestrator wired to the default registries.

    Keyword arguments are forwarded to ``RetrievalOrchestrator``.  Pass
    ``embedding_options`` to mirror the indexation configuration.
    """
    return RetrievalOrchestrator(
        build_default_registry(),
        build_embedding_registry(),
        **options,
    )

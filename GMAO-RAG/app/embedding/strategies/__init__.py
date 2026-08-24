"""Public concrete embedding strategies."""

from __future__ import annotations

from app.embedding.base import EmbeddingStrategy
from app.embedding.strategies.sentence_transformer import SentenceTransformerEmbedding

#: Strategies registered by default by ``build_default_registry()``.
#: Add a new strategy class here to make it available out of the box —
#: no change to ``app.embedding.build_default_registry`` is needed.
ALL_STRATEGIES: tuple[type[EmbeddingStrategy], ...] = (
    SentenceTransformerEmbedding,
)

__all__ = ["SentenceTransformerEmbedding", "ALL_STRATEGIES"]

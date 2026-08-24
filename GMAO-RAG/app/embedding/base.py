"""Abstract contract for embedding strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.models.chunk import Chunk
from app.models.embedding import Embedding


class EmbeddingStrategy(ABC):
    """Transform chunks into normalized vector representations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the stable registry name of the strategy."""
        raise NotImplementedError

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the identifier of the model used by the strategy."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of vectors emitted by the strategy."""
        raise NotImplementedError

    @abstractmethod
    def supports(self, chunks: Sequence[Chunk]) -> bool:
        """Return whether the supplied chunks can be embedded."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, chunks: Sequence[Chunk]) -> list[Embedding]:
        """Encode chunks and return embeddings in the same order."""
        raise NotImplementedError

"""Normalized embedding model produced by the embedding layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(slots=True)
class Embedding:
    """Vector representation of one chunk.

    The model deliberately stores only the chunk identifier rather than a
    second copy of the chunk content or source fields. Those remain owned by
    :class:`app.models.chunk.Chunk` and can be joined through ``chunk_id``.
    """

    chunk_id: str
    vector: tuple[float, ...]
    model_name: str
    dimension: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chunk_id, str) or not self.chunk_id.strip():
            raise ValueError("chunk_id must be a non-empty string.")
        self.chunk_id = self.chunk_id.strip()

        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name must be a non-empty string.")
        self.model_name = self.model_name.strip()

        if isinstance(self.dimension, bool) or not isinstance(self.dimension, int):
            raise ValueError("dimension must be an integer.")
        if self.dimension <= 0:
            raise ValueError("dimension must be greater than zero.")

        if not isinstance(self.vector, tuple):
            if isinstance(self.vector, Sequence) and not isinstance(self.vector, str):
                self.vector = tuple(self.vector)
            else:
                raise ValueError("vector must be a sequence of numbers.")

        if len(self.vector) != self.dimension:
            raise ValueError("vector length must match dimension.")

        try:
            self.vector = tuple(float(value) for value in self.vector)
        except (TypeError, ValueError) as exc:
            raise ValueError("vector must contain only numeric values.") from exc

        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary.")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the embedding."""
        return {
            "chunk_id": self.chunk_id,
            "vector": list(self.vector),
            "model_name": self.model_name,
            "dimension": self.dimension,
            "metadata": dict(self.metadata),
        }

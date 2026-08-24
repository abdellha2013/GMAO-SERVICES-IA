"""High-level orchestration for chunk embedding."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.embedding.registry import EmbeddingRegistry
from app.exceptions import EmbeddingError, EmbeddingValidationError
from app.models.chunk import Chunk
from app.models.embedding import Embedding


class EmbeddingOrchestrator:
    """Resolve an embedding strategy and embed a batch of chunks."""

    def __init__(
        self,
        registry: EmbeddingRegistry,
        *,
        strategy_name: str = "sentence-transformer",
        **strategy_options: Any,
    ) -> None:
        if not isinstance(registry, EmbeddingRegistry):
            raise EmbeddingValidationError(
                message="registry must be an EmbeddingRegistry instance.",
                details={"received_type": type(registry).__name__},
            )

        if not isinstance(strategy_name, str) or not strategy_name.strip():
            raise EmbeddingValidationError(
                message="strategy_name must be a non-empty string.",
            )

        self._registry = registry
        self._strategy_name = strategy_name.strip().lower()
        self._strategy_options = dict(strategy_options)

    @property
    def registry(self) -> EmbeddingRegistry:
        return self._registry

    @property
    def strategy_name(self) -> str:
        return self._strategy_name

    @staticmethod
    def _validate_chunks(chunks: Sequence[Chunk]) -> None:
        if not isinstance(chunks, Sequence) or isinstance(chunks, (str, bytes)):
            raise EmbeddingValidationError(
                message="chunks must be a sequence of Chunk objects.",
                details={"received_type": type(chunks).__name__},
            )

        if not chunks:
            raise EmbeddingValidationError(message="chunks must not be empty.")

        for index, chunk in enumerate(chunks):
            if not isinstance(chunk, Chunk):
                raise EmbeddingValidationError(
                    message="chunks must contain only Chunk objects.",
                    details={"index": index, "received_type": type(chunk).__name__},
                )

    def embed(self, chunks: Sequence[Chunk]) -> list[Embedding]:
        """Embed ``chunks`` while preserving their order."""
        self._validate_chunks(chunks)
        strategy_cls = self._registry.get(self._strategy_name)

        try:
            strategy = strategy_cls(**self._strategy_options)
            if not strategy.supports(chunks):
                raise EmbeddingValidationError(
                    message="Resolved embedding strategy does not support these chunks.",
                    details={"strategy": strategy.name},
                )
            embeddings = strategy.embed(chunks)
        except EmbeddingError:
            raise
        except Exception as exc:
            raise EmbeddingError(
                message="Embedding strategy execution failed.",
                details={"strategy_name": self._strategy_name},
                original=exc,
            ) from exc

        if not isinstance(embeddings, list):
            raise EmbeddingValidationError(
                message="embedding strategy must return a list of Embedding objects.",
                details={"received_type": type(embeddings).__name__},
            )

        if len(embeddings) != len(chunks):
            raise EmbeddingValidationError(
                message="embedding strategy must return one embedding per chunk.",
                details={"chunks_count": len(chunks), "embeddings_count": len(embeddings)},
            )

        for index, embedding in enumerate(embeddings):
            if not isinstance(embedding, Embedding):
                raise EmbeddingValidationError(
                    message="embedding strategy returned an invalid embedding.",
                    details={"index": index, "received_type": type(embedding).__name__},
                )

        return embeddings

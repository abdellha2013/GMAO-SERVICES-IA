"""
Chunker orchestrator.

This module selects the appropriate chunker strategy for a
ParsedDocument and executes the chunking operation.

Strategy registration and lookup are handled by ChunkerRegistry.

The orchestrator is responsible for:
    - validating the ParsedDocument;
    - resolving the appropriate strategy;
    - configuring the strategy;
    - checking strategy compatibility;
    - executing the chunking operation;
    - validating the generated chunks.

Pipeline:

    ParsedDocument
        ↓
    ChunkerOrchestrator
        ↓
    ChunkerRegistry
        ↓
    ChunkerStrategy
        ↓
    list[Chunk]
"""

from __future__ import annotations

from app.exceptions import (
    ChunkerError,
    ChunkerValidationError,
    ChunkingError,
    ChunkSizeError,
)
from app.models.chunk import Chunk
from app.models.parsing import ParsedDocument
from app.chunker.registry import ChunkerRegistry


class ChunkerOrchestrator:
    """
    Resolve and execute a chunker strategy for a ParsedDocument.

    Parameters
    ----------
    registry : ChunkerRegistry
        Registry containing the available chunker strategies.

    chunk_size : int
        Maximum size of a generated chunk.

    chunk_overlap : int
        Number of characters shared between consecutive chunks.
    """

    def __init__(
        self,
        registry: ChunkerRegistry,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        """
        Initialize the chunker orchestrator.

        Parameters
        ----------
        registry : ChunkerRegistry
            Registry used to resolve chunker strategies.

        chunk_size : int
            Maximum chunk size.

        chunk_overlap : int
            Overlap between consecutive chunks.

        Raises
        ------
        ChunkerValidationError
            If the configuration is invalid.
        """

        # ======================================================
        # Registry validation
        # ======================================================

        if not isinstance(registry, ChunkerRegistry):
            raise ChunkerValidationError(
                message="registry must be a ChunkerRegistry instance.",
                details={
                    "received_type": type(registry).__name__,
                    "expected_type": "ChunkerRegistry",
                },
            )

        # ======================================================
        # Chunk size validation
        # ======================================================

        # Guard against bool being accepted as int (bool is a
        # subclass of int in Python), so chunk_size=True is not
        # silently treated as chunk_size=1 — see
        # FIX_CHUNKER_MODULE.md §4, applied here too for
        # consistency (§5/§6: chunk_size/overlap errors use the
        # dedicated ChunkSizeError).
        if (
            isinstance(chunk_size, bool)
            or not isinstance(chunk_size, int)
        ):
            raise ChunkSizeError(
                message="chunk_size must be an integer.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if chunk_size <= 0:
            raise ChunkSizeError(
                message="chunk_size must be greater than zero.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        # ======================================================
        # Chunk overlap validation
        # ======================================================

        if (
            isinstance(chunk_overlap, bool)
            or not isinstance(chunk_overlap, int)
        ):
            raise ChunkSizeError(
                message="chunk_overlap must be an integer.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if chunk_overlap < 0:
            raise ChunkSizeError(
                message="chunk_overlap must not be negative.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if chunk_overlap >= chunk_size:
            raise ChunkSizeError(
                message=(
                    "chunk_overlap must be smaller than chunk_size."
                ),
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        self._registry = registry
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def registry(self) -> ChunkerRegistry:
        """Return the active chunker registry."""
        return self._registry

    @property
    def chunk_size(self) -> int:
        """Return the configured chunk size."""
        return self._chunk_size

    @property
    def chunk_overlap(self) -> int:
        """Return the configured chunk overlap."""
        return self._chunk_overlap

    # ==========================================================
    # Validation
    # ==========================================================

    @staticmethod
    def _validate_document(
        document: ParsedDocument,
    ) -> None:
        """
        Validate the ParsedDocument before chunking.
        """

        if not isinstance(document, ParsedDocument):
            raise ChunkerValidationError(
                message="document must be a ParsedDocument instance.",
                details={
                    "received_type": type(document).__name__,
                    "expected_type": "ParsedDocument",
                },
            )

        if not isinstance(document.source_type, str):
            raise ChunkerValidationError(
                message="document.source_type must be a string.",
                details={
                    "field": "source_type",
                    "received_type": (
                        type(document.source_type).__name__
                    ),
                },
            )

        if not document.source_type.strip():
            raise ChunkerValidationError(
                message="document.source_type must not be empty.",
                details={
                    "field": "source_type",
                },
            )

        if not isinstance(document.content, str):
            raise ChunkerValidationError(
                message="document.content must be a string.",
                details={
                    "field": "content",
                    "received_type": type(document.content).__name__,
                },
            )

        if not document.content.strip():
            raise ChunkerValidationError(
                message="document.content must not be empty.",
                details={
                    "source_name": document.source_name,
                    "source_type": document.source_type,
                },
            )

    # ==========================================================
    # Strategy creation
    # ==========================================================

    def _create_strategy(self, strategy_cls):
        """
        Instantiate a chunker strategy with the configured parameters.

        The strategy must accept:

            chunk_size
            chunk_overlap
        """

        try:

            return strategy_cls(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )

        except ChunkerError:
            raise

        except TypeError as exc:

            raise ChunkingError(
                message=(
                    f"Chunker strategy '{strategy_cls.__name__}' "
                    "does not accept the required chunking "
                    "configuration."
                ),
                details={
                    "strategy": strategy_cls.__name__,
                    "chunk_size": self._chunk_size,
                    "chunk_overlap": self._chunk_overlap,
                },
                original=exc,
            ) from exc

        except Exception as exc:

            raise ChunkingError(
                message=(
                    f"Unable to instantiate chunker strategy "
                    f"'{strategy_cls.__name__}'."
                ),
                details={
                    "strategy": strategy_cls.__name__,
                },
                original=exc,
            ) from exc

    # ==========================================================
    # Chunk
    # ==========================================================

    def chunk(
        self,
        document: ParsedDocument,
    ) -> list[Chunk]:
        """
        Chunk a ParsedDocument using the registered strategy.

        Parameters
        ----------
        document : ParsedDocument
            Parsed document to split.

        Returns
        -------
        list[Chunk]
            Generated chunks.
        """

        # ======================================================
        # 1. Validate document
        # ======================================================

        self._validate_document(document)

        source_type = (
            document.source_type
            .strip()
            .lower()
        )

        # ======================================================
        # 2. Resolve strategy
        # ======================================================

        strategy_cls = self._registry.get(source_type)

        # ======================================================
        # 3. Instantiate configured strategy
        # ======================================================

        strategy = self._create_strategy(
            strategy_cls
        )

        # ======================================================
        # 4. Check support
        # ======================================================

        try:

            supported = strategy.supports(
                document
            )

        except ChunkerError:
            raise

        except Exception as exc:

            raise ChunkingError(
                message=(
                    f"Chunker strategy '{strategy_cls.__name__}' "
                    "failed while checking document support."
                ),
                details={
                    "strategy": strategy_cls.__name__,
                    "source_type": source_type,
                    "source_name": document.source_name,
                },
                original=exc,
            ) from exc

        if not supported:

            raise ChunkerError(
                message=(
                    f"Chunker strategy '{strategy.name}' "
                    f"does not support source type "
                    f"'{source_type}'."
                ),
                details={
                    "strategy": strategy.name,
                    "source_type": source_type,
                    "source_name": document.source_name,
                },
            )

        # ======================================================
        # 5. Execute chunking
        # ======================================================

        try:

            chunks = strategy.chunk(
                document
            )

        except ChunkerError:
            raise

        except Exception as exc:

            raise ChunkingError(
                message=(
                    f"Chunker strategy '{strategy.name}' "
                    "failed while chunking the document."
                ),
                details={
                    "strategy": strategy.name,
                    "source_type": source_type,
                    "source_name": document.source_name,
                    "chunk_size": self._chunk_size,
                    "chunk_overlap": self._chunk_overlap,
                },
                original=exc,
            ) from exc

        # ======================================================
        # 6. Validate result
        # ======================================================

        if not isinstance(chunks, list):

            raise ChunkerValidationError(
                message=(
                    f"Chunker strategy '{strategy.name}' "
                    "must return a list of Chunk objects."
                ),
                details={
                    "strategy": strategy.name,
                    "received_type": type(chunks).__name__,
                    "expected_type": "list",
                },
            )

        for index, chunk in enumerate(chunks):

            if not isinstance(chunk, Chunk):

                raise ChunkerValidationError(
                    message=(
                        f"Chunker strategy '{strategy.name}' "
                        f"returned an invalid chunk at index "
                        f"{index}."
                    ),
                    details={
                        "strategy": strategy.name,
                        "index": index,
                        "received_type": type(chunk).__name__,
                        "expected_type": "Chunk",
                    },
                )

        return chunks
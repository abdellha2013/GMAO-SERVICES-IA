"""
app/exceptions/chunker.py
==========================

Exceptions for the Chunker layer.

This module defines the exception hierarchy used by the chunking
pipeline.

All Chunker-specific exceptions inherit from ChunkerError, which
itself inherits from GMAOError. This keeps error handling consistent
with the other layers of the application (data source, file, database,
parser).

Hierarchy
---------
GMAOError
└── ChunkerError
    ├── ChunkerValidationError
    │       └── ChunkSizeError
    ├── InvalidChunkerStrategyError
    ├── ChunkerStrategyNotRegisteredError
    ├── ChunkingError
    └── EmptyChunkError

Note on this corrected version
-------------------------------
Like the original ``parser.py``, this module used to repeat the same
``__init__`` boilerplate in every subclass and never set
``error_code``/``http_status``, which made chunker errors behave
differently from the rest of the pipeline once serialized via
``to_dict()``. It now follows the same ``DEFAULT_MESSAGE`` /
``DEFAULT_ERROR_CODE`` / ``DEFAULT_HTTP_STATUS`` convention as
``data_source.py`` and ``parser.py`` for a consistent, predictable API
across all three pipeline stages (loading, parsing, chunking).
"""

from __future__ import annotations

from typing import Any

from .base_exception import GMAOError

__all__ = [
    "ChunkerError",
    "ChunkerValidationError",
    "InvalidChunkerStrategyError",
    "ChunkerStrategyNotRegisteredError",
    "ChunkingError",
    "EmptyChunkError",
    "ChunkSizeError",
]


class ChunkerError(GMAOError):
    """
    Base exception for all errors raised by the Chunker layer.

    Parameters
    ----------
    message : str, optional
        Human-readable description of the error.
    details : dict[str, Any] | None, optional
        Additional structured information about the error.
    original : Exception | None, optional
        Original exception that caused this error, when applicable.
    """

    DEFAULT_MESSAGE = "An error occurred in the chunker layer."
    DEFAULT_ERROR_CODE = "CHUNKER_ERROR"
    DEFAULT_HTTP_STATUS = 422
    DEFAULT_RETRYABLE = False

    def __init__(
        self,
        message: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop(
                "error_code",
                self.DEFAULT_ERROR_CODE,
            ),
            http_status=kwargs.pop(
                "http_status",
                self.DEFAULT_HTTP_STATUS,
            ),
            **kwargs,
        )


class ChunkerValidationError(ChunkerError):
    """
    Raised when Chunker input or configuration is invalid.

    Typical cases include:

    - invalid ParsedDocument;
    - invalid source type;
    - invalid chunk size;
    - invalid overlap;
    - invalid strategy configuration.
    """

    DEFAULT_MESSAGE = "Invalid input or configuration for the chunker."
    DEFAULT_ERROR_CODE = "CHUNKER_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class InvalidChunkerStrategyError(ChunkerError):
    """
    Raised when a chunker strategy does not respect the expected
    ChunkerStrategy contract.

    Typical cases include:

    - object is not a class;
    - class does not inherit from ChunkerStrategy;
    - strategy cannot be instantiated;
    - strategy exposes an invalid configuration.
    """

    DEFAULT_MESSAGE = "Invalid chunker strategy."
    DEFAULT_ERROR_CODE = "CHUNKER_INVALID_STRATEGY"
    DEFAULT_HTTP_STATUS = 500


class ChunkerStrategyNotRegisteredError(ChunkerError):
    """
    Raised when no chunker strategy is registered for a requested
    source type.
    """

    DEFAULT_MESSAGE = (
        "No chunker strategy is registered for this source type."
    )
    DEFAULT_ERROR_CODE = "CHUNKER_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 500


class ChunkingError(ChunkerError):
    """
    Raised when a strategy fails during the chunking operation.

    This exception represents an execution failure rather than an
    invalid configuration.
    """

    DEFAULT_MESSAGE = "Unable to chunk the document."
    DEFAULT_ERROR_CODE = "CHUNKING_ERROR"
    DEFAULT_HTTP_STATUS = 422


class EmptyChunkError(ChunkerError):
    """
    Raised when the chunking process produces an invalid empty chunk.

    Empty chunks should normally not be propagated to downstream
    components such as embedding or vector storage.
    """

    DEFAULT_MESSAGE = "The chunk contains no meaningful content."
    DEFAULT_ERROR_CODE = "CHUNKER_EMPTY_CHUNK"
    DEFAULT_HTTP_STATUS = 422


class ChunkSizeError(ChunkerValidationError):
    """
    Raised when chunk size configuration is invalid.

    Examples
    --------
    Invalid configurations include:

    - chunk_size <= 0
    - overlap < 0
    - overlap >= chunk_size
    """

    DEFAULT_MESSAGE = "Invalid chunk size configuration."
    DEFAULT_ERROR_CODE = "CHUNKER_INVALID_CHUNK_SIZE"

    def __init__(
        self,
        message: str | None = None,
        *,
        chunk_size: int | None = None,
        overlap: int | None = None,
        details: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        error_details = dict(details or {})

        if chunk_size is not None:
            error_details["chunk_size"] = chunk_size

        if overlap is not None:
            error_details["overlap"] = overlap

        super().__init__(
            message=message,
            details=error_details,
            **kwargs,
        )

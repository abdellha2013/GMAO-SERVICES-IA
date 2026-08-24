"""app/exceptions/retrieval.py
=============================

Exception hierarchy dedicated to the retrieval layer.

Hierarchy
---------
- RetrievalError (base)
  ├── RetrievalValidationError
  │   └── EmptyQueryError
  ├── InvalidRetrievalStrategyError
  ├── RetrievalStrategyNotRegisteredError
  ├── RetrievalConnectionError
  ├── RetrievalExecutionError
  └── IncompatibleEmbeddingModelError
"""
from __future__ import annotations

from typing import Any
from .base_exception import GMAOError


class RetrievalError(GMAOError):
    """Base class for all retrieval-layer errors."""

    DEFAULT_MESSAGE = "A retrieval error occurred."
    DEFAULT_ERROR_CODE = "RETRIEVAL_ERROR"
    DEFAULT_HTTP_STATUS = 500

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop("error_code", self.DEFAULT_ERROR_CODE),
            http_status=kwargs.pop("http_status", self.DEFAULT_HTTP_STATUS),
            **kwargs,
        )


class RetrievalValidationError(RetrievalError):
    """Raised when retrieval input or configuration is invalid."""

    DEFAULT_MESSAGE = "Invalid retrieval input or configuration."
    DEFAULT_ERROR_CODE = "RETRIEVAL_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class EmptyQueryError(RetrievalValidationError):
    """Raised when the query string is empty or whitespace-only."""

    DEFAULT_MESSAGE = "Query must not be empty."
    DEFAULT_ERROR_CODE = "RETRIEVAL_EMPTY_QUERY"


class InvalidRetrievalStrategyError(RetrievalError):
    """Raised when a strategy class does not meet required interface."""

    DEFAULT_MESSAGE = "Invalid retrieval strategy."
    DEFAULT_ERROR_CODE = "RETRIEVAL_INVALID_STRATEGY"


class RetrievalStrategyNotRegisteredError(RetrievalError):
    """Raised when looking up a strategy name not in the registry."""

    DEFAULT_MESSAGE = "No retrieval strategy is registered for this name."
    DEFAULT_ERROR_CODE = "RETRIEVAL_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 400


class RetrievalConnectionError(RetrievalError):
    """Raised on network / connection failures to a retrieval backend."""

    DEFAULT_MESSAGE = "Unable to connect to a retrieval backend."
    DEFAULT_ERROR_CODE = "RETRIEVAL_CONNECTION_ERROR"


class RetrievalExecutionError(RetrievalError):
    """Raised when a retrieval operation fails at execution time."""

    DEFAULT_MESSAGE = "Retrieval execution failed."
    DEFAULT_ERROR_CODE = "RETRIEVAL_EXECUTION_ERROR"


class IncompatibleEmbeddingModelError(RetrievalError):
    """Raised when the query vector dimension mismatches the collection."""

    DEFAULT_MESSAGE = "Embedding model is incompatible with the vector collection."
    DEFAULT_ERROR_CODE = "RETRIEVAL_INCOMPATIBLE_EMBEDDING_MODEL"

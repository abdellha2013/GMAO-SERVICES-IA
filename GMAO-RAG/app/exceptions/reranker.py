"""Exceptions for the reranker layer of the RAG pipeline (``app.reranker``).

Hierarchy::

    GMAOError
    └── RerankerError
        ├── RerankerValidationError
        ├── RerankerModelError
        ├── RerankingError
        ├── RerankerStrategyNotRegisteredError
        └── InvalidRerankerStrategyError
"""
from __future__ import annotations

from .base_exception import GMAOError


class RerankerError(GMAOError):
    """Base class for every exception raised by ``app.reranker``."""

    DEFAULT_MESSAGE = "A reranker error occurred."
    DEFAULT_ERROR_CODE = "RERANKER_ERROR"
    DEFAULT_HTTP_STATUS = 500

    def __init__(self, message: str | None = None, **kwargs: object) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop("error_code", self.DEFAULT_ERROR_CODE),
            http_status=kwargs.pop("http_status", self.DEFAULT_HTTP_STATUS),
            **kwargs,
        )


class RerankerValidationError(RerankerError):
    """Invalid input supplied to the reranker layer."""

    DEFAULT_MESSAGE = "Invalid reranker input."
    DEFAULT_ERROR_CODE = "RERANKER_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class RerankerModelError(RerankerError):
    """The underlying cross-encoder model could not be loaded or executed."""

    DEFAULT_MESSAGE = "Reranker model failure."
    DEFAULT_ERROR_CODE = "RERANKER_MODEL_ERROR"
    DEFAULT_HTTP_STATUS = 500


class RerankingError(RerankerError):
    """General reranking operation failure."""

    DEFAULT_MESSAGE = "Reranking operation failed."
    DEFAULT_ERROR_CODE = "RERANKING_ERROR"
    DEFAULT_HTTP_STATUS = 500


class RerankerStrategyNotRegisteredError(RerankerError):
    """No reranker strategy is registered under the requested name."""

    DEFAULT_MESSAGE = "Reranker strategy not registered."
    DEFAULT_ERROR_CODE = "RERANKER_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 400


class InvalidRerankerStrategyError(RerankerError):
    """A strategy class does not conform to the ``RerankerStrategy`` contract."""

    DEFAULT_MESSAGE = "Invalid reranker strategy."
    DEFAULT_ERROR_CODE = "RERANKER_INVALID_STRATEGY"
    DEFAULT_HTTP_STATUS = 500

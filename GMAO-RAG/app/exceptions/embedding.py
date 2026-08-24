"""Exceptions for the embedding stage of the RAG pipeline (``app.embedding``).

Mirrors the conventions established by ``app/exceptions/chunker.py`` and
``app/exceptions/parser.py``: every concrete exception here inherits from
``EmbeddingError`` (itself a ``GMAOError``), follows the ``DEFAULT_MESSAGE`` /
``DEFAULT_ERROR_CODE`` / ``DEFAULT_HTTP_STATUS`` pattern, and can be raised
either bare (``raise EmbeddingModelError()``) or with an overridden message
and/or ``details``.

Hierarchy


---------
::

    GMAOError
    └── EmbeddingError
        ├── EmbeddingValidationError
        ├── InvalidEmbeddingStrategyError
        ├── EmbeddingStrategyNotRegisteredError
        ├── EmbeddingModelError
        └── EmbeddingEncodingError

``InvalidEmbeddingStrategyError`` and ``EmbeddingStrategyNotRegisteredError``
are direct children of ``EmbeddingError`` (siblings of
``EmbeddingValidationError``, not descendants of it) — this matches how
``app/embedding/registry.py`` already catches them as two independent
branches: ``except (EmbeddingValidationError, InvalidEmbeddingStrategyError)``.
"""

from __future__ import annotations

from app.exceptions.base_exception import GMAOError

__all__ = [
    "EmbeddingError",
    "EmbeddingValidationError",
    "InvalidEmbeddingStrategyError",
    "EmbeddingStrategyNotRegisteredError",
    "EmbeddingModelError",
    "EmbeddingEncodingError",
]


class EmbeddingError(GMAOError):
    """Base class for every exception raised by ``app.embedding``."""

    DEFAULT_MESSAGE = "Embedding error."
    DEFAULT_ERROR_CODE = "EMBEDDING_ERROR"
    DEFAULT_HTTP_STATUS = 500

    def __init__(self, message: str | None = None, **kwargs: object) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop("error_code", self.DEFAULT_ERROR_CODE),
            http_status=kwargs.pop("http_status", self.DEFAULT_HTTP_STATUS),
            **kwargs,
        )


class EmbeddingValidationError(EmbeddingError):
    """Invalid input supplied to the embedding layer.

    Raised for malformed chunks, an invalid registry/orchestrator
    configuration, or a strategy that rejects the supplied chunks via
    ``EmbeddingStrategy.supports()``.
    """

    DEFAULT_MESSAGE = "Invalid embedding input."
    DEFAULT_ERROR_CODE = "EMBEDDING_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class InvalidEmbeddingStrategyError(EmbeddingError):
    """A strategy class does not conform to the ``EmbeddingStrategy`` contract.

    Raised by ``EmbeddingRegistry.register()`` when the supplied class is not
    a ``type``, does not subclass ``EmbeddingStrategy``, or cannot be
    instantiated with its default constructor.
    """

    DEFAULT_MESSAGE = "Invalid embedding strategy."
    DEFAULT_ERROR_CODE = "EMBEDDING_INVALID_STRATEGY"
    DEFAULT_HTTP_STATUS = 500


class EmbeddingStrategyNotRegisteredError(EmbeddingError):
    """No strategy is registered under the requested name.

    Raised by ``EmbeddingRegistry.get()`` / ``unregister()`` for an unknown
    or unregistered strategy name.
    """

    DEFAULT_MESSAGE = "Embedding strategy not registered."
    DEFAULT_ERROR_CODE = "EMBEDDING_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 400


class EmbeddingModelError(EmbeddingError):
    """The underlying embedding model could not be loaded or inspected.

    Raised when the ``sentence-transformers`` dependency is missing, the
    model fails to load (network, disk, or invalid model/revision), or the
    model reports an invalid dimension.
    """

    DEFAULT_MESSAGE = "Embedding model failure."
    DEFAULT_ERROR_CODE = "EMBEDDING_MODEL_ERROR"
    DEFAULT_HTTP_STATUS = 500


class EmbeddingEncodingError(EmbeddingError):
    """Encoding chunks into vectors failed or returned an invalid result.

    Raised when the model's ``encode()`` call fails, returns a mismatched
    number of vectors, or a vector cannot be converted to a tuple of floats
    or does not match the model's declared dimension.
    """

    DEFAULT_MESSAGE = "Embedding encoding failure."
    DEFAULT_ERROR_CODE = "EMBEDDING_ENCODING_ERROR"
    DEFAULT_HTTP_STATUS = 500

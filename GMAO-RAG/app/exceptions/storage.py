"""Exceptions for the storage layer."""
from __future__ import annotations

from typing import Any

from .base_exception import GMAOError


class StorageError(GMAOError):
    """Base class for every exception raised by the storage layer."""

    DEFAULT_MESSAGE = "A storage error occurred."
    DEFAULT_ERROR_CODE = "STORAGE_ERROR"
    DEFAULT_HTTP_STATUS = 500

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop("error_code", self.DEFAULT_ERROR_CODE),
            http_status=kwargs.pop("http_status", self.DEFAULT_HTTP_STATUS),
            **kwargs,
        )


class StorageValidationError(StorageError):
    """Raised when storage input or configuration is invalid."""

    DEFAULT_MESSAGE = "Invalid storage input or configuration."
    DEFAULT_ERROR_CODE = "STORAGE_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class StorageAlignmentError(StorageValidationError):
    """Raised when chunks and embeddings do not describe the same batch."""

    DEFAULT_MESSAGE = "Chunks and embeddings are not aligned."
    DEFAULT_ERROR_CODE = "STORAGE_ALIGNMENT_ERROR"
    DEFAULT_HTTP_STATUS = 400

    def __init__(
        self,
        message: str | None = None,
        *,
        chunk_count: int | None = None,
        embedding_count: int | None = None,
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        values = dict(details or {})
        values.update(
            {
                key: value
                for key, value in {
                    "chunk_count": chunk_count,
                    "embedding_count": embedding_count,
                }.items()
                if value is not None
            }
        )
        super().__init__(message, details=values, **kwargs)


class InvalidStorageStrategyError(StorageError):
    """Raised when a class registered as a storage strategy is invalid."""

    DEFAULT_MESSAGE = "Invalid storage strategy."
    DEFAULT_ERROR_CODE = "STORAGE_INVALID_STRATEGY"
    DEFAULT_HTTP_STATUS = 500


class StorageStrategyNotRegisteredError(StorageError):
    """Raised when a storage strategy name has no matching registered class."""

    DEFAULT_MESSAGE = "No storage strategy is registered for this name."
    DEFAULT_ERROR_CODE = "STORAGE_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 400


class StorageConnectionError(StorageError):
    """Raised when establishing a connection to a storage backend fails.

    Reserved for genuine connection failures (unreachable host, refused
    authentication, ...). A failure that occurs while writing or deleting
    data through an already-established connection is a
    :class:`StorageWriteError`, not this.
    """

    DEFAULT_MESSAGE = "Unable to connect to a storage backend."
    DEFAULT_ERROR_CODE = "STORAGE_CONNECTION_ERROR"
    DEFAULT_HTTP_STATUS = 500


class StorageWriteError(StorageError):
    """Raised when a write, update, upsert or delete operation fails."""

    DEFAULT_MESSAGE = "Unable to write to a storage backend."
    DEFAULT_ERROR_CODE = "STORAGE_WRITE_ERROR"
    DEFAULT_HTTP_STATUS = 500


class PartialStorageError(StorageError):
    """Raised by the orchestrator when a storage operation partially failed.

    Raised at the end of :meth:`StorageOrchestrator.save` /
    :meth:`StorageOrchestrator.delete` when the resulting
    :class:`~app.storage.base.StorageReport` has failures, the run was
    allowed to complete (``stop_on_failure=False``), and the orchestrator
    is configured to be noisy about partial failures
    (``raise_on_partial_failure=True``, the default). Its serializable
    ``details`` contain the failures and the names of strategies that
    succeeded; no mutable report object is attached after construction.

    HTTP status 207 (Multi-Status) is used by convention: some strategies
    succeeded, some did not.
    """

    DEFAULT_MESSAGE = "Storage completed only partially."
    DEFAULT_ERROR_CODE = "PARTIAL_STORAGE_ERROR"
    DEFAULT_HTTP_STATUS = 207

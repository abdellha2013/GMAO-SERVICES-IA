"""Base types and contracts for the storage layer.

This module defines the data structures used to report the outcome of a
storage operation (:class:`StorageOutcome`, :class:`StorageReport`) and the
abstract contract that every storage strategy (MySQL, Qdrant, ...) must
implement (:class:`StorageStrategy`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.models.chunk import Chunk
from app.models.embedding import Embedding


@dataclass(frozen=True, slots=True)
class StorageOutcome:
    """Result of a single storage strategy execution.

    Attributes
    ----------
    strategy_name:
        Registered name of the strategy that produced this outcome
        (for example ``"mysql"`` or ``"qdrant"``).
    saved_ids:
        Identifiers that were successfully persisted (or deleted) by
        the strategy.
    failures:
        Structured failure details. Each entry is a dictionary produced
        from a :class:`~app.exceptions.storage.StorageError` via its
        ``to_dict()`` method (or an equivalent mapping), so that callers
        keep the original ``message``, ``error_code`` and ``details``.
    """

    strategy_name: str
    saved_ids: tuple[Any, ...] = ()
    failures: tuple[dict[str, Any], ...] = ()

    @property
    def success(self) -> bool:
        """Return ``True`` when the strategy reported no failure."""
        return not self.failures


@dataclass(frozen=True, slots=True)
class StorageReport:
    """Aggregated result of an orchestrated storage operation.

    A report bundles the individual :class:`StorageOutcome` produced by
    each strategy that took part in a ``save()`` or ``delete()`` call.
    """

    outcomes: tuple[StorageOutcome, ...] = ()

    @property
    def failures(self) -> tuple[dict[str, Any], ...]:
        """Flatten all failures from every outcome into a single tuple."""
        return tuple(
            failure
            for outcome in self.outcomes
            for failure in outcome.failures
        )

    @property
    def has_failures(self) -> bool:
        """Return ``True`` when at least one outcome reported a failure."""
        return bool(self.failures)

    @property
    def is_full_success(self) -> bool:
        """Return ``True`` when every outcome succeeded."""
        return bool(self.outcomes) and all(
            outcome.success for outcome in self.outcomes
        )


class StorageStrategy(ABC):
    """Contract implemented by every concrete storage backend.

    ``name`` is declared as a plain class attribute (not a property) so
    that :class:`~app.storage.registry.StorageRegistry` can read it
    without instantiating the strategy. Instantiating a strategy may
    require a database connection or environment validation (see
    :class:`~app.storage.strategies.mysql_storage.MySQLStorage`), which
    must never happen as a side effect of registering the class.
    """

    name: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.name, str) or not cls.name.strip():
            raise TypeError(
                f"{cls.__name__} must define a non-empty class attribute "
                f"'name'."
            )

    @abstractmethod
    def supports(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Embedding],
    ) -> bool:
        """Return ``True`` when this strategy can persist the given batch."""
        raise NotImplementedError

    @abstractmethod
    def save(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Embedding],
    ) -> StorageOutcome:
        """Persist the given chunks and embeddings."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, chunk_ids: Sequence[Any]) -> StorageOutcome:
        """Delete the storage records identified by ``chunk_ids``."""
        raise NotImplementedError

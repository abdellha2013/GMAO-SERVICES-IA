"""Immutable data models used by :mod:`app.retrieval`."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


def _positive_id(name: str, value: int | None) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
        raise ValueError(f"{name} must be a positive integer or None.")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalFilter:
    """Optional constraints applied to retrieved chunks."""
    id_document: int | None = None
    id_panne: int | None = None
    id_equipement: int | None = None
    source_type: str | None = None
    min_score: float | None = None

    def __post_init__(self) -> None:
        for name in ("id_document", "id_panne", "id_equipement"):
            _positive_id(name, getattr(self, name))
        if self.source_type is not None:
            if not isinstance(self.source_type, str) or not self.source_type.strip():
                raise ValueError("source_type must be a non-empty string or None.")
            object.__setattr__(self, "source_type", self.source_type.strip().lower())
        if self.min_score is not None and (isinstance(self.min_score, bool) or not isinstance(self.min_score, (int, float)) or not math.isfinite(self.min_score)):
            raise ValueError("min_score must be a finite number or None.")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievedChunk:
    """One chunk returned by a retrieval strategy."""
    chunk_id: str
    content: str
    score: float
    rank: int
    source_name: str
    source_type: str
    id_document: int | None = None
    id_panne: int | None = None
    id_equipement: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_strategy: str = ""

    def __post_init__(self) -> None:
        for name in ("chunk_id", "content", "source_name", "source_type", "retrieval_strategy"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
            raise ValueError("score must be a finite number.")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer.")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary.")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalReport:
    """The ordered outcome of one user query."""
    query: str
    strategy_name: str
    results: tuple[RetrievedChunk, ...] = ()
    total_candidates: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string.")
        if not isinstance(self.strategy_name, str) or not self.strategy_name.strip():
            raise ValueError("strategy_name must be a non-empty string.")
        if isinstance(self.total_candidates, bool) or not isinstance(self.total_candidates, int) or self.total_candidates < 0:
            raise ValueError("total_candidates must be a non-negative integer.")

    @property
    def is_empty(self) -> bool:
        return not self.results

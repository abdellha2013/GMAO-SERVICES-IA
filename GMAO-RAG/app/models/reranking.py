"""Immutable data models used by :mod:`app.reranker`."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class RankedChunk:
    """One chunk returned by a reranking strategy.

    Preserves the original chunk identity and retrieval score while
    adding a cross-encoder reranking score and a final rank.
    """

    chunk_id: str
    content: str
    source_name: str
    source_type: str
    retrieval_score: float
    rerank_score: float
    rank: int
    id_document: int | None = None
    id_panne: int | None = None
    id_equipement: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    retrieval_strategy: str = ""
    reranker_strategy: str = ""

    def __post_init__(self) -> None:
        for name in ("chunk_id", "content", "source_name", "source_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")

        if isinstance(self.retrieval_score, bool) or not isinstance(self.retrieval_score, (int, float)) or not math.isfinite(self.retrieval_score):
            raise ValueError("retrieval_score must be a finite number.")
        if isinstance(self.rerank_score, bool) or not isinstance(self.rerank_score, (int, float)) or not math.isfinite(self.rerank_score):
            raise ValueError("rerank_score must be a finite number.")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer.")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary.")

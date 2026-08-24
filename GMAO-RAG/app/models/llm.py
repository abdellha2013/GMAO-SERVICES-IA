"""Immutable data models used by :mod:`app.llm`."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class Citation:
    """A reference to a source chunk used by the LLM to generate its answer."""

    chunk_id: str
    source_name: str
    source_type: str
    rerank_score: float

    def __post_init__(self) -> None:
        for name in ("chunk_id", "source_name", "source_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if isinstance(self.rerank_score, bool) or not isinstance(self.rerank_score, (int, float)) or not math.isfinite(self.rerank_score):
            raise ValueError("rerank_score must be a finite number.")


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMResponse:
    """Structured response produced by an LLM strategy."""

    answer: str
    query: str
    strategy_name: str
    model_name: str
    citations: tuple[Citation, ...] = ()
    tokens_input: int = 0
    tokens_output: int = 0
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("answer", "query", "strategy_name", "model_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if not isinstance(self.citations, tuple):
            raise ValueError("citations must be a tuple.")
        for i, c in enumerate(self.citations):
            if not isinstance(c, Citation):
                raise ValueError(f"citations[{i}] must be a Citation instance.")
        if isinstance(self.tokens_input, bool) or not isinstance(self.tokens_input, int) or self.tokens_input < 0:
            raise ValueError("tokens_input must be a non-negative integer.")
        if isinstance(self.tokens_output, bool) or not isinstance(self.tokens_output, int) or self.tokens_output < 0:
            raise ValueError("tokens_output must be a non-negative integer.")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, (int, float)) or not math.isfinite(self.duration_ms) or self.duration_ms < 0:
            raise ValueError("duration_ms must be a non-negative finite number.")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary.")

"""Cross-Encoder based reranking strategy."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from threading import RLock
from typing import Any, ClassVar

from app.exceptions import (
    RerankerModelError,
    RerankerValidationError,
    RerankingError,
)
from app.models.reranking import RankedChunk
from app.models.retrieval import RetrievedChunk
from app.reranker.base import RerankerStrategy

logger = logging.getLogger(__name__)


class CrossEncoderReranker(RerankerStrategy):
    """Rerank retrieved candidates using a Cross-Encoder model.

    The model evaluates query-document pairs jointly and produces
    relevance scores used to re-order the candidates.  The model is
    lazily loaded on the first call to :meth:`rerank` and cached at
    class level so subsequent calls reuse the same instance.
    """

    name = "cross-encoder"

    DEFAULT_MODEL_NAME: ClassVar[str] = "BAAI/bge-reranker-v2-m3"
    DEFAULT_BATCH_SIZE: ClassVar[int] = 16

    _model_cache: ClassVar[dict[str, Any]] = {}
    _cache_lock: ClassVar[RLock] = RLock()
    _key_locks: ClassVar[dict[str, RLock]] = {}

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str = "auto",
        **_: object,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise RerankerValidationError(message="model_name must be a non-empty string.")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise RerankerValidationError(
                message="batch_size must be a positive integer.",
                details={"batch_size": batch_size},
            )
        if not isinstance(device, str) or device.strip().lower() not in {"auto", "cpu", "cuda"}:
            raise RerankerValidationError(
                message="device must be one of: 'auto', 'cpu', 'cuda'.",
                details={"device": device},
            )

        self._model_name = model_name.strip()
        self._batch_size = batch_size
        self._device = device.strip().lower()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def device(self) -> str:
        return self._device

    def _cache_key(self) -> str:
        return f"{self._model_name}|{self._device}"

    def _get_model(self) -> Any:
        key = self._cache_key()

        cached = self._model_cache.get(key)
        if cached is not None:
            return cached

        with self._cache_lock:
            key_lock = self._key_locks.setdefault(key, RLock())

        with key_lock:
            cached = self._model_cache.get(key)
            if cached is not None:
                return cached

            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RerankerModelError(
                    message="sentence-transformers is required for CrossEncoderReranker.",
                    details={"dependency": "sentence-transformers"},
                    original=exc,
                ) from exc

            try:
                kwargs: dict[str, Any] = {}
                if self._device != "auto":
                    kwargs["device"] = self._device
                model = CrossEncoder(self._model_name, **kwargs)
            except Exception as exc:
                raise RerankerModelError(
                    message=f"Unable to load cross-encoder model '{self._model_name}'.",
                    details={
                        "model_name": self._model_name,
                        "device": self._device,
                    },
                    original=exc,
                ) from exc

            self._model_cache[key] = model
            logger.info(
                "CrossEncoder model '%s' loaded on device '%s'.",
                self._model_name,
                self._device,
            )
            return model

    @classmethod
    def clear_model_cache(cls) -> None:
        """Clear cached model instances; mainly intended for isolated tests."""
        with cls._cache_lock:
            cls._model_cache.clear()
            cls._key_locks.clear()

    def supports(self, query: str, candidates: Sequence[RetrievedChunk]) -> bool:
        return (
            isinstance(query, str)
            and bool(query.strip())
            and isinstance(candidates, Sequence)
            and not isinstance(candidates, (str, bytes))
            and all(isinstance(c, RetrievedChunk) for c in candidates)
        )

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        *,
        top_k: int,
        **kwargs: Any,
    ) -> list[RankedChunk]:
        if not isinstance(query, str) or not query.strip():
            raise RerankerValidationError(message="query must be a non-empty string.")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise RerankerValidationError(message="candidates must be a sequence of RetrievedChunk.")
        if not candidates:
            return []
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise RerankerValidationError(message="top_k must be a positive integer.")
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, RetrievedChunk):
                raise RerankerValidationError(
                    message="candidates must contain only RetrievedChunk objects.",
                    details={"index": index, "received_type": type(candidate).__name__},
                )

        model = self._get_model()

        pairs = [[query.strip(), candidate.content] for candidate in candidates]

        try:
            scores = model.predict(
                pairs,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RerankingError(
                message="Cross-Encoder prediction failed.",
                details={"model_name": self._model_name, "candidates_count": len(candidates)},
                original=exc,
            ) from exc

        scored: list[tuple[RetrievedChunk, float]] = []
        for candidate, score in zip(candidates, scores, strict=True):
            scored.append((candidate, float(score)))

        scored.sort(key=lambda item: item[1], reverse=True)

        results: list[RankedChunk] = []
        for rank, (candidate, rerank_score) in enumerate(scored[:top_k], 1):
            merged_metadata = dict(candidate.metadata)
            merged_metadata["retrieval_rank"] = candidate.rank
            results.append(
                RankedChunk(
                    chunk_id=candidate.chunk_id,
                    content=candidate.content,
                    source_name=candidate.source_name,
                    source_type=candidate.source_type,
                    retrieval_score=candidate.score,
                    rerank_score=rerank_score,
                    rank=rank,
                    id_document=candidate.id_document,
                    id_panne=candidate.id_panne,
                    id_equipement=candidate.id_equipement,
                    metadata=merged_metadata,
                    retrieval_strategy=candidate.retrieval_strategy,
                    reranker_strategy=self.name,
                )
            )

        logger.info(
            "Reranked %d candidates -> %d results (model=%s, top_k=%d).",
            len(candidates), len(results), self._model_name, top_k,
        )
        return results

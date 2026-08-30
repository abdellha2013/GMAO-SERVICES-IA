"""Sentence Transformers implementation of the embedding strategy."""

from __future__ import annotations

from collections.abc import Sequence
from threading import RLock
from typing import Any, ClassVar

from app.embedding.base import EmbeddingStrategy
from app.exceptions import (
    EmbeddingEncodingError,
    EmbeddingModelError,
    EmbeddingValidationError,
)
from app.models.chunk import Chunk
from app.models.embedding import Embedding


class SentenceTransformerEmbedding(EmbeddingStrategy):
    """Encode chunks locally with a lazily loaded Sentence Transformers model.

    The default E5 model expects the ``passage: `` prefix for indexed
    documents. Future query retrieval should use the companion ``query: ``
    prefix before comparing vectors.
    """

    DEFAULT_MODEL_NAME: ClassVar[str] = "intfloat/multilingual-e5-small"
    DEFAULT_MODEL_REVISION: ClassVar[str] = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    DEFAULT_DIMENSION: ClassVar[int] = 384
    DEFAULT_BATCH_SIZE: ClassVar[int] = 32
    _model_cache: ClassVar[dict[tuple[str, str, str], Any]] = {}
    # Guards mutation of ``_model_cache`` and ``_key_locks`` themselves.
    # Never held while a model is being loaded — only while looking up
    # or creating the per-key lock below.
    _cache_lock: ClassVar[RLock] = RLock()
    # One lock per (model_name, revision, device) cache key, so loading
    # one model never blocks lookups or loads for a different key.
    _key_locks: ClassVar[dict[tuple[str, str, str], RLock]] = {}

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        model_revision: str | None = DEFAULT_MODEL_REVISION,
        batch_size: int = DEFAULT_BATCH_SIZE,
        normalize_embeddings: bool = True,
        device: str = "auto",
        document_prefix: str = "passage: ",
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise EmbeddingValidationError(message="model_name must be a non-empty string.")
        if model_revision is not None and (not isinstance(model_revision, str) or not model_revision.strip()):
            raise EmbeddingValidationError(message="model_revision must be a non-empty string or None.")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise EmbeddingValidationError(
                message="batch_size must be a positive integer.",
                details={"batch_size": batch_size},
            )
        if not isinstance(normalize_embeddings, bool):
            raise EmbeddingValidationError(message="normalize_embeddings must be a boolean.")
        if not isinstance(device, str) or device.strip().lower() not in {"auto", "cpu", "cuda"}:
            raise EmbeddingValidationError(
                message="device must be one of: 'auto', 'cpu', 'cuda'.",
                details={"device": device},
            )
        if not isinstance(document_prefix, str):
            raise EmbeddingValidationError(message="document_prefix must be a string.")

        self._model_name = model_name.strip()
        self._model_revision = model_revision.strip() if model_revision is not None else "main"
        self._batch_size = batch_size
        self._normalize_embeddings = normalize_embeddings
        self._device = device.strip().lower()
        self._document_prefix = document_prefix
        self._dimension = (
            self.DEFAULT_DIMENSION
            if self._model_name == self.DEFAULT_MODEL_NAME
            else None
        )

    @property
    def name(self) -> str:
        return "sentence-transformer"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_revision(self) -> str:
        """Return the Hugging Face revision used to load the model."""
        return self._model_revision

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = self._resolve_dimension(self._get_model())
        return self._dimension

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def normalize_embeddings(self) -> bool:
        return self._normalize_embeddings

    @property
    def device(self) -> str:
        return self._device

    def supports(self, chunks: Sequence[Chunk]) -> bool:
        return (
            isinstance(chunks, Sequence)
            and not isinstance(chunks, (str, bytes))
            and bool(chunks)
            and all(isinstance(chunk, Chunk) and bool(chunk.content.strip()) for chunk in chunks)
        )

    @classmethod
    def clear_model_cache(cls) -> None:
        """Clear cached model instances; mainly intended for isolated tests."""
        with cls._cache_lock:
            cls._model_cache.clear()
            cls._key_locks.clear()

    def _cache_key(self) -> tuple[str, str, str]:
        return self._model_name, self._model_revision, self._device

    def _get_model(self) -> Any:
        key = self._cache_key()

        # Fast path: model already cached, no locking needed.
        cached = self._model_cache.get(key)
        if cached is not None:
            return cached

        # Obtain (or create) a lock scoped to this cache key only. The
        # class-level ``_cache_lock`` is held just long enough to look up
        # or register that per-key lock — never while a model loads — so
        # loading one model never blocks lookups or loads for a different
        # (model_name, revision, device) key.
        with self._cache_lock:
            key_lock = self._key_locks.setdefault(key, RLock())

        with key_lock:
            # Re-check: another thread may have loaded this exact key
            # while we were waiting for the lock (double-checked locking).
            cached = self._model_cache.get(key)
            if cached is not None:
                return cached

            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingModelError(
                    message="sentence-transformers is required for SentenceTransformerEmbedding.",
                    details={"dependency": "sentence-transformers"},
                    original=exc,
                ) from exc

            try:
                kwargs: dict[str, Any] = {}
                if self._device != "auto":
                    kwargs["device"] = self._device
                model = SentenceTransformer(
                    self._model_name,
                    revision=self._model_revision,
                    **kwargs,
                )
            except Exception as exc:
                raise EmbeddingModelError(
                    message=f"Unable to load embedding model '{self._model_name}'.",
                    details={
                        "model_name": self._model_name,
                        "model_revision": self._model_revision,
                        "device": self._device,
                    },
                    original=exc,
                ) from exc

            self._model_cache[key] = model
            return model

    def preload(self) -> Any:
        """Charge le modèle en mémoire si ce n'est pas déjà fait.

        Idempotent : le modèle est mis en cache au niveau de la classe,
        donc un appel ultérieur renvoie la même instance sans recharger.
        Appelé au démarrage du service pour que les questions soient
        traitées sans attendre le chargement du modèle.
        """
        return self._get_model()

    @staticmethod
    def _resolve_dimension(model: Any) -> int:
        try:
            # sentence-transformers renamed this API.  Prefer the current
            # spelling while keeping support for older model implementations.
            get_dimension = getattr(model, "get_embedding_dimension", None)
            if not callable(get_dimension):
                get_dimension = model.get_sentence_embedding_dimension
            dimension = get_dimension()
        except Exception as exc:
            raise EmbeddingModelError(
                message="Unable to determine the embedding model dimension.",
                original=exc,
            ) from exc

        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise EmbeddingModelError(
                message="Embedding model returned an invalid dimension.",
                details={"dimension": dimension},
            )
        return dimension

    @staticmethod
    def _as_float_tuple(vector: Any) -> tuple[float, ...]:
        values = vector.tolist() if hasattr(vector, "tolist") else vector
        try:
            return tuple(float(value) for value in values)
        except (TypeError, ValueError) as exc:
            raise EmbeddingEncodingError(
                message="Embedding model returned an invalid vector.",
                original=exc,
            ) from exc

    @staticmethod
    def _chunk_identifier(chunk: Chunk) -> str:
        return chunk.chunk_id or f"{chunk.source_name}:{chunk.chunk_index}"

    def embed(self, chunks: Sequence[Chunk]) -> list[Embedding]:
        if not self.supports(chunks):
            raise EmbeddingValidationError(
                message="chunks must be a non-empty sequence of non-empty Chunk objects.",
            )

        model = self._get_model()
        dimension = self._resolve_dimension(model)
        self._dimension = dimension
        texts = [f"{self._document_prefix}{chunk.content}" for chunk in chunks]

        try:
            vectors = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize_embeddings,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingEncodingError(
                message=f"Unable to encode chunks with '{self._model_name}'.",
                details={"model_name": self._model_name, "chunks_count": len(chunks)},
                original=exc,
            ) from exc

        if len(vectors) != len(chunks):
            raise EmbeddingEncodingError(
                message="Embedding model returned an unexpected number of vectors.",
                details={"chunks_count": len(chunks), "vectors_count": len(vectors)},
            )

        embeddings: list[Embedding] = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            numeric_vector = self._as_float_tuple(vector)
            if len(numeric_vector) != dimension:
                raise EmbeddingEncodingError(
                    message="Embedding vector dimension does not match the model dimension.",
                    details={
                        "index": index,
                        "expected_dimension": dimension,
                        "actual_dimension": len(numeric_vector),
                    },
                )

            metadata = dict(chunk.metadata)
            metadata.update(
                {
                    "embedding_strategy": self.name,
                    "embedding_model": self._model_name,
                    "embedding_model_revision": self._model_revision,
                    "embedding_dimension": dimension,
                    "normalize_embeddings": self._normalize_embeddings,
                }
            )
            embeddings.append(
                Embedding(
                    chunk_id=self._chunk_identifier(chunk),
                    vector=numeric_vector,
                    model_name=self._model_name,
                    dimension=dimension,
                    metadata=metadata,
                )
            )

        return embeddings

    def embed_query(self, query: str) -> tuple[float, ...]:
        """Encode one retrieval query with the E5 ``query: `` prefix.

        The model is obtained through :meth:`_get_model`, exactly as it is
        for passages.  Consequently a query and passages emitted by strategy
        instances configured with the same model, revision and device share
        both the model object and its cache key.
        """
        if not isinstance(query, str) or not query.strip():
            raise EmbeddingValidationError(
                message="query must be a non-empty string.",
                details={"received_type": type(query).__name__},
            )

        model = self._get_model()
        dimension = self._resolve_dimension(model)
        self._dimension = dimension

        try:
            vectors = model.encode(
                [f"query: {query.strip()}"],
                batch_size=self._batch_size,
                normalize_embeddings=self._normalize_embeddings,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingEncodingError(
                message=f"Unable to encode query with '{self._model_name}'.",
                details={"model_name": self._model_name},
                original=exc,
            ) from exc

        if len(vectors) != 1:
            raise EmbeddingEncodingError(
                message="Embedding model returned an unexpected number of query vectors.",
                details={"vectors_count": len(vectors)},
            )

        vector = self._as_float_tuple(vectors[0])
        if len(vector) != dimension:
            raise EmbeddingEncodingError(
                message="Query vector dimension does not match the model dimension.",
                details={
                    "expected_dimension": dimension,
                    "actual_dimension": len(vector),
                },
            )
        return vector

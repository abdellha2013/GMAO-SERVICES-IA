"""Qdrant storage strategy.

Persists embeddings as vector points in a Qdrant collection. This
strategy is intentionally independent from MySQL: it only knows about
``id_chunk`` (already present in ``chunk.metadata`` because MySQL is
expected to run first in the strategy sequence) and never writes to the
relational database itself. Propagating a successful Qdrant write back
into the MySQL status column is the orchestrator's responsibility (see
``StorageOrchestrator._mark_indexed_after_qdrant``), not this strategy's.
"""
from __future__ import annotations

import os
from collections.abc import Sequence

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import PointIdsList, PointStruct

from app.exceptions import StorageConnectionError, StorageValidationError, StorageWriteError
from app.models.chunk import Chunk
from app.models.embedding import Embedding
from app.storage.base import StorageOutcome, StorageStrategy


class QdrantStorage(StorageStrategy):
    """Storage strategy backed by a Qdrant collection."""

    name = "qdrant"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        **_: object,
    ) -> None:
        load_dotenv()
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks")
        try:
            self.client = QdrantClient(
                host=host or os.getenv("QDRANT_HOST", "localhost"),
                port=port or int(os.getenv("QDRANT_PORT", "6333")),
            )
        except ResponseHandlingException as exc:
            raise StorageConnectionError(
                message="Unable to connect to the Qdrant storage backend.",
                original=exc,
            ) from exc

    def supports(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> bool:
        """Return ``True`` when every chunk has a MySQL-generated ``id_chunk``.

        See STORAGE.md for the full metadata contract; ``id_chunk`` is
        expected to be injected by ``MySQLStorage.save()``, which is why
        Qdrant must run after MySQL in the default strategy sequence.
        """
        pairs = zip(chunks, embeddings, strict=True)
        return all(
            isinstance(chunk.metadata.get("id_chunk"), int) and bool(embedding.vector)
            for chunk, embedding in pairs
        )

    def save(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> StorageOutcome:
        """Upsert one vector point per chunk/embedding pair."""
        if not self.supports(chunks, embeddings):
            raise StorageValidationError(message="Qdrant storage requires MySQL-generated id_chunk values.")
        points = [
            PointStruct(
                id=chunk.metadata["id_chunk"],
                vector=list(embedding.vector),
                payload={
                    "id_chunk": chunk.metadata["id_chunk"],
                    "type_source": "Document" if chunk.metadata.get("id_document") else "Panne",
                    "id_equipement": chunk.metadata.get("id_equipement"),
                },
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        try:
            self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
        except ResponseHandlingException as exc:
            raise StorageWriteError(message="Unable to write to Qdrant.", original=exc) from exc
        return StorageOutcome(self.name, tuple(chunk.metadata["id_chunk"] for chunk in chunks))

    def delete(self, chunk_ids: Sequence[int]) -> StorageOutcome:
        """Delete the given points from the Qdrant collection."""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=list(chunk_ids)),
                wait=True,
            )
        except ResponseHandlingException as exc:
            raise StorageWriteError(message="Unable to delete Qdrant points.", original=exc) from exc
        return StorageOutcome(self.name, tuple(chunk_ids))

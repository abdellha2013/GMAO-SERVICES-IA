"""MySQL storage strategy.

Persists chunks (and their MySQL-generated identifiers) into the fused
``document_chunks`` table of the local ``gmao`` schema (chunk content
plus ``id_document`` parent in one row — there is no ``chunk_rag`` /
``document_chunk`` / ``panne_chunk`` split), and exposes the operations
the orchestrator needs to manage a chunk's lifecycle in MySQL: ``save``,
``delete`` and ``mark_indexed`` (kept as a no-op since the ``gmao``
schema has no ``statut_embedding`` column — indexed status is derived
from Qdrant presence instead).
"""
from __future__ import annotations

import os
from collections.abc import Sequence

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.exceptions import StorageConnectionError, StorageValidationError, StorageWriteError
from app.models.chunk import Chunk
from app.models.embedding import Embedding
from app.storage.base import StorageOutcome, StorageStrategy


class MySQLStorage(StorageStrategy):
    """Storage strategy backed by the project's MySQL database."""

    name = "mysql"

    def __init__(self, *, dsn: str | None = None, batch_size: int = 200, **_: object) -> None:
        load_dotenv()
        self._dsn = dsn or os.getenv("MYSQL_DSN") or self._dsn_from_env()
        if not self._dsn:
            raise StorageValidationError(message="MYSQL_DSN must be configured.")
        self._batch_size = batch_size
        self._engine = create_engine(self._dsn)

    @staticmethod
    def _dsn_from_env() -> str | None:
        host = os.getenv("GMAO_DB_HOST")
        user = os.getenv("GMAO_DB_USER")
        database = os.getenv("GMAO_DB_NAME")
        if not all((host, user, database)):
            return None
        password = os.getenv("GMAO_DB_PASSWORD", "")
        port = os.getenv("GMAO_DB_PORT", "3306")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

    def supports(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> bool:
        """Return ``True`` when every chunk carries a document parent id.

        In the fused ``gmao`` schema chunks are stored in
        ``document_chunks`` which requires ``id_document``.  See
        STORAGE.md for the full metadata contract.
        """
        return all(
            bool(chunk.metadata.get("id_document"))
            for chunk in chunks
        )

    def save(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> StorageOutcome:
        """Insert ``chunks`` into ``document_chunks``.

        On success, each ``chunk.metadata["id_chunk"]`` is populated with
        the MySQL-generated primary key, which downstream strategies
        (Qdrant) rely on to key their own records.
        """
        if not self.supports(chunks, embeddings):
            raise StorageValidationError(
                message="Each chunk requires id_document in metadata."
            )
        saved_ids: list[int] = []
        try:
            with self._engine.begin() as connection:
                for chunk in chunks:
                    tokens = chunk.metadata.get("nombre_tokens")
                    if tokens is None:
                        tokens = len(chunk.content.split())
                    result = connection.execute(
                        text(
                            "INSERT INTO document_chunks "
                            "(contenu, ordre_chunk, nombre_tokens, id_document) "
                            "VALUES (:content, :order, :tokens, :parent_id)"
                        ),
                        {
                            "content": chunk.content,
                            "order": chunk.chunk_index,
                            "tokens": tokens,
                            "parent_id": chunk.metadata["id_document"],
                        },
                    )
                    chunk_id = int(result.lastrowid)
                    saved_ids.append(chunk_id)
                    chunk.metadata["id_chunk"] = chunk_id
        except OperationalError as exc:
            raise StorageConnectionError(
                message="Unable to connect to the MySQL storage backend.",
                original=exc,
            ) from exc
        except SQLAlchemyError as exc:
            raise StorageWriteError(message="MySQL storage transaction failed.", original=exc) from exc
        return StorageOutcome(self.name, tuple(saved_ids))

    def delete(self, chunk_ids: Sequence[int]) -> StorageOutcome:
        """Delete the given chunks from ``document_chunks``.

        The ``gmao`` schema declares ``ON DELETE CASCADE`` from the
        ``documents`` parent, but these rows are deleted explicitly so the
        outcome count is accurate regardless of whether the parent is
        removed afterwards.
        """
        deleted_ids: list[int] = []
        try:
            with self._engine.begin() as connection:
                for chunk_id in chunk_ids:
                    connection.execute(
                        text("DELETE FROM document_chunks WHERE id_chunk = :id"),
                        {"id": chunk_id},
                    )
                    deleted_ids.append(chunk_id)
        except OperationalError as exc:
            raise StorageConnectionError(
                message="Unable to connect to the MySQL storage backend.",
                original=exc,
            ) from exc
        except SQLAlchemyError as exc:
            raise StorageWriteError(message="Unable to delete MySQL chunks.", original=exc) from exc
        return StorageOutcome(self.name, tuple(deleted_ids))

    def mark_indexed(self, chunk_ids: Sequence[int]) -> None:
        """No-op: the ``gmao`` schema has no ``statut_embedding`` column.

        ``indexed`` status is derived from Qdrant presence instead, so
        this hook (kept for the orchestrator interface) does nothing.
        """

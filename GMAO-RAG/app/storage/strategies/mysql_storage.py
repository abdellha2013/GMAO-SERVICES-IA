"""MySQL storage strategy.

Persists chunks (and their MySQL-generated identifiers) into
``chunk_rag`` plus the relevant child table (``document_chunk`` or
``panne_chunk``), and exposes the operations the orchestrator needs to
manage a chunk's lifecycle in MySQL: ``save``, ``delete`` and
``mark_indexed`` (called by the orchestrator once a chunk has been
successfully written to Qdrant).
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

# Child tables that reference chunk_rag(id_chunk). If the foreign keys in
# the schema are declared with ON DELETE CASCADE, deleting from chunk_rag
# is enough and these explicit deletes are redundant but harmless. If they
# are not, these deletes are required to avoid leaving orphaned rows or
# hitting a foreign-key violation on the chunk_rag delete itself.
_CHILD_TABLES: tuple[str, ...] = ("document_chunk", "panne_chunk")


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
        """Return ``True`` when every chunk carries a document or panne parent id.

        See STORAGE.md for the full metadata contract expected at this
        stage of the pipeline (``id_document`` / ``id_panne``).
        """
        return all(
            bool(chunk.metadata.get("id_document") or chunk.metadata.get("id_panne"))
            for chunk in chunks
        )

    def save(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> StorageOutcome:
        """Insert ``chunks`` into ``chunk_rag`` and their matching child table.

        On success, each ``chunk.metadata["id_chunk"]`` is populated with
        the MySQL-generated primary key, which downstream strategies
        (Qdrant) rely on to key their own records.
        """
        if not self.supports(chunks, embeddings):
            raise StorageValidationError(
                message="Each chunk requires source_type document/panne and its parent ID in metadata."
            )
        saved_ids: list[int] = []
        try:
            with self._engine.begin() as connection:
                for chunk in chunks:
                    is_document = bool(chunk.metadata.get("id_document"))
                    source = "Document" if is_document else "Panne"
                    result = connection.execute(
                        text(
                            "INSERT INTO chunk_rag "
                            "(contenu, ordre_chunk, nombre_tokens, type_source, statut_embedding) "
                            "VALUES (:content, :order, :tokens, :source, 'En_attente')"
                        ),
                        {
                            "content": chunk.content,
                            "order": chunk.chunk_index,
                            "tokens": chunk.metadata.get("nombre_tokens"),
                            "source": source,
                        },
                    )
                    chunk_id = int(result.lastrowid)
                    saved_ids.append(chunk_id)
                    chunk.metadata["id_chunk"] = chunk_id
                    if is_document:
                        child_table, parent_key = "document_chunk", "id_document"
                    else:
                        child_table, parent_key = "panne_chunk", "id_panne"
                    connection.execute(
                        text(
                            f"INSERT INTO {child_table} (id_chunk, {parent_key}) "
                            f"VALUES (:id_chunk, :parent_id)"
                        ),
                        {"id_chunk": chunk_id, "parent_id": chunk.metadata[parent_key]},
                    )
        except OperationalError as exc:
            raise StorageConnectionError(
                message="Unable to connect to the MySQL storage backend.",
                original=exc,
            ) from exc
        except SQLAlchemyError as exc:
            raise StorageWriteError(message="MySQL storage transaction failed.", original=exc) from exc
        return StorageOutcome(self.name, tuple(saved_ids))

    def delete(self, chunk_ids: Sequence[int]) -> StorageOutcome:
        """Delete the given chunks from ``chunk_rag`` and its child tables.

        Child rows are deleted first, in the same transaction, so this is
        safe whether or not ``ON DELETE CASCADE`` is configured on the
        foreign keys: if it is, these deletes are a no-op by the time
        ``chunk_rag`` is deleted; if it is not, they prevent orphaned rows
        or a foreign-key violation.
        """
        deleted_ids: list[int] = []
        try:
            with self._engine.begin() as connection:
                for chunk_id in chunk_ids:
                    for child_table in _CHILD_TABLES:
                        connection.execute(
                            text(f"DELETE FROM {child_table} WHERE id_chunk = :id"),
                            {"id": chunk_id},
                        )
                    connection.execute(
                        text("DELETE FROM chunk_rag WHERE id_chunk = :id"),
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
        """Flag ``chunk_ids`` as indexed once they have been written to Qdrant.

        Called by :class:`~app.storage.orchestrator.StorageOrchestrator`
        after a successful ``QdrantStorage.save()``. ``QdrantStorage``
        itself must never call this or otherwise touch MySQL directly.
        """
        if not chunk_ids:
            return
        try:
            with self._engine.begin() as connection:
                for chunk_id in chunk_ids:
                    connection.execute(
                        text(
                            "UPDATE chunk_rag "
                            "SET statut_embedding = 'Indexe', date_indexation = NOW() "
                            "WHERE id_chunk = :id"
                        ),
                        {"id": chunk_id},
                    )
        except OperationalError as exc:
            raise StorageConnectionError(
                message="Unable to connect to the MySQL storage backend.",
                original=exc,
            ) from exc
        except SQLAlchemyError as exc:
            raise StorageWriteError(
                message="Qdrant points were written but the MySQL status update failed.",
                original=exc,
            ) from exc

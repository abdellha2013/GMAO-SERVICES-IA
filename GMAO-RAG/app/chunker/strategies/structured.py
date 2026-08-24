"""
Structured-data chunking strategy.

This module provides a chunker specialized for structured documents
such as JSON, CSV, XLSX and database results.

The strategy attempts to preserve logical records whenever possible.
Large records are split only when they exceed the configured chunk size.

Version corrigée : voir les commentaires "# FIX" pour le détail des
correctifs apportés au fichier original.
"""

from __future__ import annotations

import json
from typing import Any

from app.exceptions import (
    ChunkerValidationError,
    ChunkingError,
)

from app.models.chunk import Chunk
from app.models.parsing import ParsedDocument

from app.chunker.strategies.base import BaseChunkerStrategy


class StructuredChunker(BaseChunkerStrategy):
    """
    Chunker strategy for structured documents.

    Supported source types
    ----------------------
    - json
    - csv
    - xlsx
    - mysql

    chunk_size / chunk_overlap validation (including construction,
    since ``__init__`` was entirely missing in the original file) is
    inherited from ``BaseChunkerStrategy``, which keeps this
    strategy consistent with ``MarkdownChunker`` and
    ``RecursiveChunker`` and also guards against ``bool`` being
    silently accepted as an ``int``.
    """

    # ==========================================================
    # Strategy identity
    # ==========================================================

    @property
    def name(self) -> str:
        return "structured"

    @property
    def source_types(self) -> tuple[str, ...]:
        return ("json", "csv", "xlsx", "mysql")

    # ==========================================================
    # Support
    # ==========================================================

    def supports(self, document: ParsedDocument) -> bool:
        """
        Check whether this strategy supports the document.

        Consistent with ``RecursiveChunker`` and ``MarkdownChunker``,
        ``supports()`` is a side-effect-free compatibility test: an
        unexpected input type returns False rather than raising, as
        required by the ``ChunkerStrategy`` contract (see
        ``CHUNKER.md`` §11, checklist item 5).
        """

        if not isinstance(document, ParsedDocument):
            return False

        source_type = (document.source_type or "").strip().lower()

        return source_type in self.source_types

    # ==========================================================
    # Structured record extraction
    # ==========================================================

    def _extract_records(
        self,
        content: str,
        source_type: str,
    ) -> list[str]:

        content = content.strip()

        if not content:
            return []

        if source_type == "json":
            return self._extract_json_records(content)

        return self._extract_line_records(content)

    def _extract_json_records(self, content: str) -> list[str]:

        try:
            data: Any = json.loads(content)
        except json.JSONDecodeError:
            return self._extract_line_records(content)

        if isinstance(data, list):

            records: list[str] = []
            for item in data:
                records.append(
                    json.dumps(item, ensure_ascii=False, indent=2)
                )
            return records

        if isinstance(data, dict):
            return [json.dumps(data, ensure_ascii=False, indent=2)]

        return [json.dumps(data, ensure_ascii=False)]

    @staticmethod
    def _extract_line_records(content: str) -> list[str]:

        records: list[str] = []
        for line in content.splitlines():
            line = line.strip()
            if line:
                records.append(line)
        return records

    # ==========================================================
    # Record grouping
    # ==========================================================

    def _group_records(self, records: list[str]) -> list[str]:

        chunks: list[str] = []
        current_records: list[str] = []
        current_length = 0

        for record in records:

            record_length = len(record)

            if record_length > self.chunk_size:

                if current_records:
                    chunks.append("\n".join(current_records))
                    current_records = []
                    current_length = 0

                chunks.extend(self._split_large_record(record))
                continue

            separator_length = 1 if current_records else 0
            candidate_length = (
                current_length + separator_length + record_length
            )

            if candidate_length <= self.chunk_size:
                current_records.append(record)
                current_length = candidate_length
            else:
                if current_records:
                    chunks.append("\n".join(current_records))
                current_records = [record]
                current_length = record_length

        if current_records:
            chunks.append("\n".join(current_records))

        return chunks

    # ==========================================================
    # Large record splitting
    # ==========================================================

    def _split_large_record(self, record: str) -> list[str]:

        lines = [
            line.strip() for line in record.splitlines() if line.strip()
        ]

        if len(lines) > 1:
            chunks = self._split_lines(lines)
        else:
            chunks = self._split_words(record)

        return chunks

    def _split_lines(self, lines: list[str]) -> list[str]:

        chunks: list[str] = []
        current: list[str] = []
        current_length = 0

        for line in lines:

            line_length = len(line)
            separator_length = 1 if current else 0
            candidate_length = (
                current_length + separator_length + line_length
            )

            if candidate_length <= self.chunk_size:
                current.append(line)
                current_length = candidate_length
            else:
                if current:
                    chunks.append("\n".join(current))

                if line_length <= self.chunk_size:
                    current = [line]
                    current_length = line_length
                else:
                    chunks.extend(self._split_words(line))
                    current = []
                    current_length = 0

        if current:
            chunks.append("\n".join(current))

        return chunks

    def _split_words(self, text: str) -> list[str]:

        words = text.split()
        chunks: list[str] = []
        current_words: list[str] = []
        current_length = 0

        for word in words:

            additional_length = (
                len(word) if not current_words else len(word) + 1
            )

            if current_length + additional_length <= self.chunk_size:
                current_words.append(word)
                current_length += additional_length
            else:
                if current_words:
                    chunks.append(" ".join(current_words))
                current_words = [word]
                current_length = len(word)

        if current_words:
            chunks.append(" ".join(current_words))

        return chunks

    # ==========================================================
    # Overlap
    # ==========================================================

    def _get_overlap(self, text: str) -> str:
        return text[-self.chunk_overlap:] if text else ""

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """
        Apply bounded overlap between consecutive record chunks.

        FIX (size bound) : the original code built
        ``overlap + '\\n' + current`` without ever checking the
        result stayed within ``chunk_size``. A full chunk could
        therefore silently exceed the configured size. The same
        rule as ``MarkdownChunker`` now applies: the overlap is only
        kept if it does not push the chunk past ``chunk_size``.

        FIX (drift) : the overlap source is now always the
        *original* previous chunk (``chunks[index - 1]``, delegated
        to ``BaseChunkerStrategy._apply_bounded_overlap``), not the
        already-combined result of the previous iteration. Computing
        it from the combined result let the overlap grow unbounded
        across a run of short records — by the last chunk it could
        contain the entire document (see ``FIX_CHUNKER_MODULE.md``
        §3 for the reproduced case).
        """

        return self._apply_bounded_overlap(
            chunks,
            get_overlap=self._get_overlap,
            combine=lambda overlap, current: (
                overlap.rstrip() + "\n" + current.lstrip()
            ),
        )

    # ==========================================================
    # Main chunk operation
    # ==========================================================

    def chunk(self, document: ParsedDocument) -> list[Chunk]:

        if not isinstance(document, ParsedDocument):
            raise ChunkerValidationError(
                message="document must be a ParsedDocument.",
                details={"received_type": type(document).__name__},
            )

        if not document.content or not document.content.strip():
            raise ChunkerValidationError(
                message="Document content must not be empty.",
                details={"source_name": document.source_name},
            )

        if not self.supports(document):
            raise ChunkerValidationError(
                message="StructuredChunker does not support this document.",
                details={
                    "source_type": document.source_type,
                    "source_name": document.source_name,
                    "strategy": self.name,
                },
            )

        try:

            source_type = document.source_type.strip().lower()

            records = self._extract_records(document.content, source_type)

            if not records:
                raise ChunkerValidationError(
                    message="No structured records were found in the document.",
                    details={
                        "source_name": document.source_name,
                        "source_type": source_type,
                    },
                )

            raw_chunks = self._group_records(records)

            non_empty_raw_chunks = [c for c in raw_chunks if c.strip()]

            if len(non_empty_raw_chunks) != len(raw_chunks):
                self._log_discarded_empty_piece(
                    document.source_name,
                    self.name,
                )

            chunks = self._apply_overlap(non_empty_raw_chunks)

            result: list[Chunk] = []

            for index, chunk_content in enumerate(chunks):

                metadata = dict(document.metadata or {})
                metadata.update(
                    {
                        "chunker": self.name,
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap,
                        "chunk_index": index,
                        "structured_source_type": source_type,
                    }
                )

                # FIX : chunk_id et chunk_index absents dans le code
                # original -> TypeError garanti (chunk_index est un
                # argument positionnel requis par le modèle Chunk,
                # confirmé par le traceback précédent sur
                # MarkdownChunker).
                result.append(
                    Chunk(
                        chunk_id=f"{document.source_name}:{index}",
                        chunk_index=index,
                        source_name=document.source_name,
                        source_type=document.source_type,
                        content=chunk_content,
                        metadata=metadata,
                    )
                )

            return result

        except ChunkerValidationError:
            raise

        except Exception as exc:

            raise ChunkingError(
                message=(
                    f"Unable to chunk structured document "
                    f"'{document.source_name}'."
                ),
                original=exc,
                details={
                    "strategy": self.name,
                    "source_type": document.source_type,
                },
            ) from exc
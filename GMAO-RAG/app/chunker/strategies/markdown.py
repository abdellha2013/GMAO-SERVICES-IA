"""
Markdown-aware chunking strategy.

Version corrigée : voir les commentaires "# FIX" pour le détail
des correctifs apportés au fichier original.
"""

from __future__ import annotations

import re

from app.chunker.strategies.base import BaseChunkerStrategy
from app.exceptions import (
    ChunkerValidationError,
    ChunkingError,
)
from app.models.chunk import Chunk
from app.models.parsing import ParsedDocument


class MarkdownChunker(BaseChunkerStrategy):
    """
    Chunker strategy specialized for Markdown documents.

    chunk_size / chunk_overlap validation is inherited from
    ``BaseChunkerStrategy`` (see ``app.chunker.strategies.base``),
    which also guards against the ``bool``-is-a-subclass-of-``int``
    pitfall (``MarkdownChunker(chunk_size=True, ...)`` now correctly
    raises ``ChunkSizeError`` instead of being silently accepted as
    ``chunk_size=1``).
    """

    @property
    def name(self) -> str:
        return "markdown"

    @property
    def source_types(self) -> tuple[str, ...]:
        return ("markdown", "md")

    def supports(self, document: ParsedDocument) -> bool:

        if not isinstance(document, ParsedDocument):
            return False

        source_type = (document.source_type or "").strip().lower()
        metadata = document.metadata or {}
        mime_type = (metadata.get("mime_type", "") or "").strip().lower()

        return (
            source_type in self.source_types
            or mime_type in {"text/markdown", "text/x-markdown"}
        )

    @staticmethod
    def _is_heading(line: str) -> bool:
        return bool(re.match(r"^\s{0,3}#{1,6}\s+", line))

    @staticmethod
    def _is_fence(line: str) -> bool:
        return bool(re.match(r"^\s*(```+|~~~+)", line))

    def _split_sections(self, content: str) -> list[str]:

        lines = content.splitlines()
        sections: list[str] = []
        current: list[str] = []
        inside_code_block = False
        fence_marker: str | None = None

        for line in lines:

            if self._is_fence(line):
                marker_match = re.match(r"^\s*(```+|~~~+)", line)
                if marker_match:
                    marker = marker_match.group(1)[0]
                    if not inside_code_block:
                        inside_code_block = True
                        fence_marker = marker
                    elif marker == fence_marker:
                        inside_code_block = False
                        fence_marker = None
                current.append(line)
                continue

            if self._is_heading(line) and not inside_code_block and current:
                section = "\n".join(current).strip()
                if section:
                    sections.append(section)
                current = []

            current.append(line)

        if current:
            section = "\n".join(current).strip()
            if section:
                sections.append(section)

        return sections

    @staticmethod
    def _split_paragraphs(section: str) -> list[str]:
        return [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", section)
            if paragraph.strip()
        ]

    def _split_large_section(self, section: str) -> list[str]:

        if len(section) <= self.chunk_size:
            return [section]

        paragraphs = self._split_paragraphs(section)
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:

            candidate = (
                paragraph if not current else f"{current}\n\n{paragraph}"
            )

            if len(candidate) <= self.chunk_size:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(paragraph) <= self.chunk_size:
                current = paragraph
            else:
                chunks.extend(self._split_by_lines(paragraph))

        if current:
            chunks.append(current)

        return chunks

    def _split_by_lines(self, text: str) -> list[str]:

        lines = text.splitlines()
        chunks: list[str] = []
        current_lines: list[str] = []
        inside_code_block = False
        fence_marker: str | None = None

        def current_text() -> str:
            return "\n".join(current_lines).strip()

        for line in lines:

            if self._is_fence(line):
                marker_match = re.match(r"^\s*(```+|~~~+)", line)
                if marker_match:
                    marker = marker_match.group(1)[0]
                    if not inside_code_block:
                        inside_code_block = True
                        fence_marker = marker
                    elif marker == fence_marker:
                        inside_code_block = False
                        fence_marker = None

            candidate_lines = [*current_lines, line]
            candidate = "\n".join(candidate_lines).strip()

            if len(candidate) <= self.chunk_size:
                current_lines.append(line)
                continue

            if current_lines:
                chunks.append(current_text())
                current_lines = []

            if len(line) <= self.chunk_size:
                current_lines.append(line)
            else:
                chunks.extend(self._split_by_words(line))

        if current_lines:
            chunks.append(current_text())

        return [chunk for chunk in chunks if chunk.strip()]

    def _split_by_words(self, text: str) -> list[str]:

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

    def _get_overlap(self, text: str) -> str:

        if self.chunk_overlap <= 0:
            return ""

        if not text:
            return ""

        overlap = text[-self.chunk_overlap:]

        if len(overlap) < len(text):
            first_space = overlap.find(" ")
            if first_space > 0:
                overlap = overlap[first_space + 1:]

        return overlap.strip()

    def _starts_with_heading(self, chunk: str) -> bool:
        lines = chunk.splitlines()
        return self._is_heading(lines[0]) if lines else False

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """
        Apply bounded overlap between consecutive Markdown chunks.

        Delegates to ``BaseChunkerStrategy._apply_bounded_overlap``,
        which always computes the overlap from the *original*
        previous chunk (``chunks[index - 1]``) rather than from the
        already-combined result of the previous iteration. This is
        what prevents the overlap from drifting/compounding across a
        run of short paragraphs (see ``FIX_CHUNKER_MODULE.md`` §3).
        """

        return self._apply_bounded_overlap(
            chunks,
            get_overlap=self._get_overlap,
            combine=lambda overlap, current: f"{overlap}\n\n{current}",
            skip_overlap=self._starts_with_heading,
        )

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
                message="MarkdownChunker does not support this document.",
                details={
                    "source_type": document.source_type,
                    "source_name": document.source_name,
                    "strategy": self.name,
                },
            )

        try:

            content = (
                document.content
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .strip()
            )

            sections = self._split_sections(content)

            raw_chunks: list[str] = []
            for section in sections:
                raw_chunks.extend(self._split_large_section(section))

            non_empty_raw_chunks = [c for c in raw_chunks if c.strip()]

            if len(non_empty_raw_chunks) != len(raw_chunks):
                self._log_discarded_empty_piece(
                    document.source_name,
                    self.name,
                )

            raw_chunks = [c.strip() for c in non_empty_raw_chunks]

            chunks = self._apply_overlap(raw_chunks)

            result: list[Chunk] = []

            for index, chunk_content in enumerate(chunks):

                metadata = dict(document.metadata or {})
                metadata.update(
                    {
                        "chunker": self.name,
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap,
                        "chunk_index": index,
                    }
                )

                # FIX : "content=content" (le document entier) remplacé par
                # "content=chunk_content" (le morceau réellement produit
                # par cette itération). C'était le bug principal : tous
                # les chunks contenaient le document complet.
                #
                # FIX : le modèle Chunk exige "chunk_index" (positional
                # argument manquant, confirmé par TypeError). Ajouté ici.
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
                    f"Unable to chunk Markdown document "
                    f"'{document.source_name}'."
                ),
                original=exc,
                details={
                    "strategy": self.name,
                    "source_type": document.source_type,
                },
            ) from exc
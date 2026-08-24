"""
Parser output models.

This module defines the data models produced by the Parser layer.

The Parser receives a SourceDocument and produces a ParsedDocument.
ParsedDocument represents normalized and structured content that is
ready for the next stage of the RAG pipeline, such as chunking.

Design principles:
    - Keep the model independent from concrete parser strategies.
    - Preserve source information from SourceDocument.
    - Keep metadata extensible.
    - Do not introduce chunking or embedding concerns here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from pathlib import Path

@dataclass(slots=True)
class ParsedDocument:
    """
    Represents the normalized result produced by the Parser.

    A ParsedDocument is the bridge between the data-source layer
    (SourceDocument) and the downstream RAG pipeline (for example,
    the future Chunker).

    Attributes:
        source_name:
            Name identifying the original source.

        source_type:
            Type of the original source, for example:
            "txt", "markdown", "html", "json", "mysql".

        content:
            Normalized textual content produced by the parser.

        metadata:
            Parser and source metadata. Existing source metadata should
            be preserved whenever possible.

        mime_type:
            MIME type associated with the original source, if available.

        source_path:
            Physical source path when one exists. It is None for sources
            such as MySQL where there is no physical file.

        size:
            Size of the parsed content in UTF-8 bytes.

        created_at:
            Original source creation timestamp, when available.

        updated_at:
            Original source modification timestamp, when available.

        parsed_at:
            Timestamp indicating when the parsing operation completed.
    """

    source_name: str
    source_type: str
    content: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)

    mime_type: str | None = None
    source_path: Path | None = None

    size: int = 0

    created_at: datetime | None = None
    updated_at: datetime | None = None
    parsed_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        """
        Return True when the parsed content contains no meaningful text.
        """
        return not self.content.strip()

    @property
    def content_length(self) -> int:
        """
        Return the number of Unicode characters in the content.
        """
        return len(self.content)

    @property
    def content_size_bytes(self) -> int:
        """
        Return the UTF-8 encoded size of the content in bytes.
        """
        return len(self.content.encode("utf-8"))

    @property
    def extension(self) -> str | None:
        """
        Return the source file extension when a physical path exists.

        Returns:
            Lowercase extension without the leading dot,
            or None when source_path is unavailable.
        """
        if self.source_path is None:
            return None

        suffix = getattr(self.source_path, "suffix", "")
        if not suffix:
            return None

        return suffix.lstrip(".").lower()

    @property
    def filename(self) -> str | None:
        """
        Return the source filename when a physical path exists.
        """
        if self.source_path is None:
            return None

        name = getattr(self.source_path, "name", "")
        return name or None

    def with_metadata(self, **values: Any) -> "ParsedDocument":
        """
        Return a new ParsedDocument with additional metadata.

        Existing metadata is preserved and updated with the supplied values.
        """
        metadata = dict(self.metadata)
        metadata.update(values)

        return ParsedDocument(
            source_name=self.source_name,
            source_type=self.source_type,
            content=self.content,
            metadata=metadata,
            mime_type=self.mime_type,
            source_path=self.source_path,
            size=self.size,
            created_at=self.created_at,
            updated_at=self.updated_at,
            parsed_at=self.parsed_at,
        )
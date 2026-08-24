"""
Chunk model.

This module defines the normalized representation of a text chunk
produced by the Chunker layer.

A Chunk contains the extracted content together with the information
required to preserve its origin and position in the source document.

Pipeline
--------
SourceDocument
    ↓
Parser
    ↓
ParsedDocument
    ↓
Chunker
    ↓
list[Chunk]
    ↓
Embedding
    ↓
Vector Store
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Chunk:
    """
    Represent a normalized chunk produced by the Chunker layer.

    A chunk is a coherent portion of a ParsedDocument prepared for
    downstream operations such as embedding, indexing, and retrieval.

    Parameters
    ----------
    content : str
        Textual content of the chunk.

    chunk_index : int
        Zero-based position of the chunk inside the source document.

    source_name : str
        Name identifying the original source.

    source_type : str
        Type of the original source, for example ``txt``, ``pdf``,
        ``markdown``, ``json``, or ``mysql``.

    metadata : dict[str, Any], optional
        Additional information inherited from the source or generated
        during chunking.

    start_char : int | None, optional
        Character offset where the chunk starts in the parsed content.

    end_char : int | None, optional
        Character offset where the chunk ends in the parsed content.

    total_chunks : int | None, optional
        Total number of chunks generated from the source document.

    chunk_id : str | None, optional
        Optional stable identifier for the chunk.

    Notes
    -----
    ``content`` is the only field containing the actual chunk text.
    The other fields preserve context and provenance for downstream
    RAG operations.
    """

    content: str
    chunk_index: int
    source_name: str
    source_type: str

    metadata: dict[str, Any] = field(default_factory=dict)

    start_char: int | None = None
    end_char: int | None = None

    total_chunks: int | None = None

    chunk_id: str | None = None

    def __post_init__(self) -> None:
        """
        Validate and normalize the chunk after initialization.

        Raises
        ------
        ValueError
            If a required field is invalid.
        """

        if not isinstance(self.content, str):
            raise ValueError(
                "Chunk content must be a string."
            )

        self.content = self.content.strip()

        if not self.content:
            raise ValueError(
                "Chunk content must not be empty."
            )

        if not isinstance(self.chunk_index, int):
            raise ValueError(
                "chunk_index must be an integer."
            )

        if self.chunk_index < 0:
            raise ValueError(
                "chunk_index must be greater than or equal to 0."
            )

        if not isinstance(self.source_name, str):
            raise ValueError(
                "source_name must be a string."
            )

        self.source_name = self.source_name.strip()

        if not self.source_name:
            raise ValueError(
                "source_name must not be empty."
            )

        if not isinstance(self.source_type, str):
            raise ValueError(
                "source_type must be a string."
            )

        self.source_type = self.source_type.strip().lower()

        if not self.source_type:
            raise ValueError(
                "source_type must not be empty."
            )

        if not isinstance(self.metadata, dict):
            raise ValueError(
                "metadata must be a dictionary."
            )

        if self.start_char is not None:
            if not isinstance(self.start_char, int):
                raise ValueError(
                    "start_char must be an integer or None."
                )

            if self.start_char < 0:
                raise ValueError(
                    "start_char must be greater than or equal to 0."
                )

        if self.end_char is not None:
            if not isinstance(self.end_char, int):
                raise ValueError(
                    "end_char must be an integer or None."
                )

            if self.end_char < 0:
                raise ValueError(
                    "end_char must be greater than or equal to 0."
                )

        if (
            self.start_char is not None
            and self.end_char is not None
            and self.end_char < self.start_char
        ):
            raise ValueError(
                "end_char must be greater than or equal to start_char."
            )

        if self.total_chunks is not None:
            if not isinstance(self.total_chunks, int):
                raise ValueError(
                    "total_chunks must be an integer or None."
                )

            if self.total_chunks <= 0:
                raise ValueError(
                    "total_chunks must be greater than 0."
                )

            if self.chunk_index >= self.total_chunks:
                raise ValueError(
                    "chunk_index must be smaller than total_chunks."
                )

        if self.chunk_id is not None:
            if not isinstance(self.chunk_id, str):
                raise ValueError(
                    "chunk_id must be a string or None."
                )

            self.chunk_id = self.chunk_id.strip()

            if not self.chunk_id:
                self.chunk_id = None

    @property
    def content_length(self) -> int:
        """
        Return the number of characters contained in the chunk.

        Returns
        -------
        int
            Length of the chunk content.
        """
        return len(self.content)

    @property
    def is_first(self) -> bool:
        """
        Return whether this is the first chunk of the document.

        Returns
        -------
        bool
            True when ``chunk_index`` is zero.
        """
        return self.chunk_index == 0

    @property
    def is_last(self) -> bool:
        """
        Return whether this is the last chunk of the document.

        Returns
        -------
        bool
            True when ``total_chunks`` is known and this is the
            final chunk.
        """
        if self.total_chunks is None:
            return False

        return self.chunk_index == self.total_chunks - 1

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the chunk into a serializable dictionary.

        Returns
        -------
        dict[str, Any]
            Dictionary representation of the chunk.
        """
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "total_chunks": self.total_chunks,
            "metadata": dict(self.metadata),
        }





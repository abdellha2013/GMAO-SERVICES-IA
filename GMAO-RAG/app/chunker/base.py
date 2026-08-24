"""
Base contract for chunker strategies.

This module defines the common interface implemented by every
chunking strategy.

Each strategy receives a ParsedDocument and transforms it into
a collection of Chunk objects.

Concrete chunking logic belongs to the individual strategy
implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.chunk import Chunk
from app.models.parsing import ParsedDocument


class ChunkerStrategy(ABC):
    """
    Abstract contract for a chunker strategy.

    A chunker strategy transforms one ParsedDocument into a
    sequence of normalized Chunk objects.

    Concrete implementations may target different document
    families, such as:

    - plain text;
    - PDF and DOCX extracted text;
    - Markdown;
    - HTML;
    - structured data;
    - database results.

    Strategy selection is handled by ChunkerRegistry and
    ChunkerOrchestrator.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique name of the chunker strategy.

        Returns
        -------
        str
            Unique strategy identifier.

        Raises
        ------
        NotImplementedError
            If the concrete strategy does not implement the property.
        """
        raise NotImplementedError


    @property
    @abstractmethod
    def source_types(self) -> tuple[str, ...]:
        """
        Return the source types supported by this strategy.

        A strategy may support multiple source types.

        Examples
        --------
        RecursiveChunker:
            ("txt", "text", "pdf", "docx", "html")

        MarkdownChunker:
            ("md", "markdown")

        StructuredChunker:
            ("json", "csv", "xlsx", "mysql")

        Returns
        -------
        tuple[str, ...]
            Supported source types.
        """
        raise NotImplementedError

    @abstractmethod
    def supports(
        self,
        document: ParsedDocument,
    ) -> bool:
        """
        Determine whether this strategy supports a document.

        This method only checks compatibility. It must not perform
        the actual chunking operation.

        Parameters
        ----------
        document : ParsedDocument
            Parsed document to evaluate.

        Returns
        -------
        bool
            True when the strategy can process the document,
            otherwise False.
        """
        raise NotImplementedError

    @abstractmethod
    def chunk(
        self,
        document: ParsedDocument,
    ) -> list[Chunk]:
        """
        Split a ParsedDocument into normalized chunks.

        Parameters
        ----------
        document : ParsedDocument
            Parsed document to split.

        Returns
        -------
        list[Chunk]
            Generated chunks in their original order.

        Raises
        ------
        ChunkerError
            If the document cannot be chunked successfully.

        Notes
        -----
        Concrete strategies should raise appropriate subclasses
        of ChunkerError rather than generic exceptions whenever
        possible.
        """
        raise NotImplementedError
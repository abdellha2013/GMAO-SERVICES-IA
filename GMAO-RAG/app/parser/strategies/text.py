"""
Plain-text parser strategy.

This module provides the parser strategy responsible for processing
SourceDocument instances representing plain-text sources.

The strategy does not read files, access databases, create chunks, or
generate embeddings. Those responsibilities belong to the corresponding
data-source loaders and downstream RAG components.

The TextParser only validates the source document, verifies that it
supports the document, performs minimal text normalization, and produces
a ParsedDocument.
"""

from __future__ import annotations

from app.exceptions import ParserValidationError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.strategies.base import BaseParserStrategy


class TextParser(BaseParserStrategy):
    """
    Parser strategy for plain-text documents.

    This strategy handles documents whose ``source_type`` is ``"txt"``,
    as well as ``"pdf"`` and ``"docx"``. The latter two are routed here
    because ``PDFLoader`` and ``DOCXLoader`` have already extracted the
    raw text upstream (see ``DATA_SOURCES.md`` §3.3); by the time a
    ``pdf``/``docx`` document reaches this strategy it is plain text
    like any other, so this is not a mapping error. It preserves the
    textual structure of the document while performing only minimal
    normalization.

    The strategy does not:

    - read files directly;
    - detect or change file encodings;
    - remove meaningful whitespace inside the document;
    - split content into chunks;
    - generate embeddings;
    - access external data sources.

    Parameters
    ----------
    None

    Examples
    --------
    >>> parser = TextParser()
    >>> parser.name
    'text'
    """
    SUPPORTED_SOURCE_TYPES = frozenset({"txt", "pdf", "docx"})

    @property
    def name(self) -> str:
        """
        Return the unique strategy name.

        Returns
        -------
        str
            Identifier of this parser strategy.
        """
        return "text"

    def supports(self, document: SourceDocument) -> bool:
        """
        Check whether this strategy supports the given document.

        The selection is intentionally based on ``source_type``.
        The loader is responsible for correctly identifying the source
        before creating the SourceDocument.

        Parameters
        ----------
        document : SourceDocument
            Document to evaluate.



        Returns
        -------
        bool
            ``True`` when the document is a plain-text source.

        Raises
        ------
        ParserValidationError
            If the provided document is invalid.
        """
        self._validate_document(document)

        source_type = document.source_type.strip().lower()

        return source_type in self.SUPPORTED_SOURCE_TYPES

    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse a plain-text SourceDocument.

        The method validates the document, verifies that this strategy
        supports it, performs minimal normalization using ``strip()``,
        and creates the normalized ParsedDocument.

        Parameters
        ----------
        document : SourceDocument
            Source document produced by a data-source loader.

        Returns
        -------
        ParsedDocument
            Normalized representation of the text document.

        Raises
        ------
        ParserValidationError
            If the document is invalid, empty, or unsupported.
        """
        self._validate_document(document)
        self._validate_content(document)

        if not self.supports(document):
            raise ParserValidationError(
                message="TextParser does not support this document.",
                details={
                    "source_type": document.source_type,
                    "mime_type": document.mime_type,
                    "strategy": self.name,
                },
            )

        content = document.content.strip()

        if not content:
            raise ParserValidationError(
                message="TextParser produced empty content.",
                details={
                    "source_name": document.source_name,
                    "strategy": self.name,
                },
            )

        return self._build_parsed_document(
            document,
            content,
        )

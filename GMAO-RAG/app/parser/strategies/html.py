"""
HTML parser strategy implementation.

This module provides the parser strategy responsible for HTML-based
SourceDocument instances.

The strategy converts HTML content into normalized plain text while
preserving the meaningful textual structure of the document.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from app.exceptions import ParserValidationError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.strategies.base import BaseParserStrategy


class HTMLParser(BaseParserStrategy):
    """
    Parser strategy for HTML source documents.

    The strategy:
    - validates the input SourceDocument;
    - detects HTML documents using source_type or MIME type;
    - removes non-content HTML elements such as scripts and styles;
    - extracts readable text from the HTML document;
    - normalizes excessive whitespace;
    - returns a ParsedDocument.

    The strategy does not perform:
    - chunking;
    - embedding;
    - vectorization;
    - document classification.
    """
    SUPPORTED_SOURCE_TYPES = frozenset({"html", "htm"})

    @property
    def name(self) -> str:
        """
        Return the unique strategy name.

        Returns
        -------
        str
            Strategy identifier.
        """
        return "html"

    def supports(self, document: SourceDocument) -> bool:
        """
        Check whether the document is an HTML document.

        Detection is based on either the source type or MIME type.

        Parameters
        ----------
        document:
            SourceDocument to evaluate.

        Returns
        -------
        bool
            True when the document is recognized as HTML.

        Raises
        ------
        ParserValidationError
            If the document itself is invalid.
        """
        self._validate_document(document)

        source_type = document.source_type.strip().lower()
        mime_type = (document.mime_type or "").strip().lower()

        return source_type in self.SUPPORTED_SOURCE_TYPES or mime_type in {
            "text/html",
            "application/xhtml+xml",
        }

    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse an HTML SourceDocument into a ParsedDocument.

        HTML markup is removed and only meaningful textual content is
        preserved. Script and style elements are explicitly ignored.

        Parameters
        ----------
        document:
            HTML SourceDocument produced by a data source loader.

        Returns
        -------
        ParsedDocument
            Normalized parsing result.

        Raises
        ------
        ParserValidationError
            If the document is invalid, unsupported, or contains no
            meaningful textual content.
        """
        self._validate_content(document)

        if not self.supports(document):
            raise ParserValidationError(
                message="HTMLParser does not support this document.",
                details={
                    "source_type": document.source_type,
                    "mime_type": document.mime_type,
                    "strategy": self.name,
                },
            )

        soup = BeautifulSoup(document.content, "html.parser")

        for element in soup(["script", "style", "noscript", "template"]):
            element.decompose()

        text = soup.get_text(separator="\n")

        content = self._normalize_text(text)

        if not content:
            raise ParserValidationError(
                message="HTML document contains no meaningful text.",
                details={
                    "source_name": document.source_name,
                    "strategy": self.name,
                },
            )

        return self._build_parsed_document(document, content)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize extracted HTML text.

        Consecutive spaces and empty lines are reduced while preserving
        meaningful line boundaries.

        Parameters
        ----------
        text:
            Raw text extracted from HTML.

        Returns
        -------
        str
            Clean normalized text.
        """
        lines = []

        for line in text.splitlines():
            normalized = " ".join(line.split())

            if normalized:
                lines.append(normalized)

        return "\n".join(lines).strip()
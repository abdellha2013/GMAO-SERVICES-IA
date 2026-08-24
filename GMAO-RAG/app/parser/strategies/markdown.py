"""
Markdown parsing strategy.

This module provides the parser strategy responsible for Markdown
SourceDocument instances.

The strategy normalizes Markdown content while preserving the semantic
structure of the original document. It does not perform chunking or
embedding.
"""

from __future__ import annotations

import re

from app.exceptions import ParserValidationError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.strategies.base import BaseParserStrategy


class MarkdownParser(BaseParserStrategy):
    """
    Parser strategy for Markdown documents.

    The parser performs lightweight normalization while preserving
    Markdown structure such as headings, lists, links, and emphasis.

    Responsibilities
    ----------------
    - Validate the input SourceDocument.
    - Verify that the document is a Markdown source.
    - Normalize line endings.
    - Remove unnecessary trailing whitespace.
    - Collapse excessive blank lines.
    - Preserve meaningful Markdown syntax.
    - Return a normalized ParsedDocument.

    The parser does not:
    - split the document into chunks;
    - generate embeddings;
    - convert Markdown to HTML;
    - remove semantic Markdown structures.
    """
    SUPPORTED_SOURCE_TYPES = frozenset({"markdown", "md"})

    @property
    def name(self) -> str:
        """
        Return the unique strategy name.

        Returns
        -------
        str
            Parser strategy identifier.
        """
        return "markdown"

    def supports(self, document: SourceDocument) -> bool:
        """
        Check whether this strategy supports the document.

        Markdown support is determined primarily from ``source_type``.
        The MIME type is used as a secondary indicator.

        Parameters
        ----------
        document:
            SourceDocument to evaluate.

        Returns
        -------
        bool
            True when the document is recognized as Markdown.

        Raises
        ------
        ParserValidationError
            If the document itself is invalid.
        """
        self._validate_document(document)

        source_type = document.source_type.strip().lower()
        mime_type = (document.mime_type or "").strip().lower()

        return source_type in self.SUPPORTED_SOURCE_TYPES or mime_type in {
            "text/markdown",
            "text/x-markdown",
        }

    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse and normalize a Markdown SourceDocument.

        Parameters
        ----------
        document:
            Markdown SourceDocument produced by a data source loader.

        Returns
        -------
        ParsedDocument
            Normalized Markdown parsing result.

        Raises
        ------
        ParserValidationError
            If the document is invalid, unsupported, or empty.
        """
        self._validate_content(document)

        if not self.supports(document):
            raise ParserValidationError(
                message="MarkdownParser does not support this document.",
                details={
                    "source_type": document.source_type,
                    "mime_type": document.mime_type,
                    "strategy": self.name,
                },
            )

        content = self._normalize_content(document.content)

        if not content:
            raise ParserValidationError(
                message="Markdown document contains no meaningful content.",
                details={
                    "source_name": document.source_name,
                    "strategy": self.name,
                },
            )

        metadata = dict(document.metadata)
        metadata.update(
            {
                "parser": self.name,
                "source_type": document.source_type,
                "original_size": document.size,
                "parsed_size": len(content.encode("utf-8")),
            }
        )

        return self._build_parsed_document(
            document,
            content,
            metadata=metadata,
        )

    @staticmethod
    def _normalize_content(content: str) -> str:
        """
        Normalize Markdown content without destroying its structure.

        The normalization performs only safe transformations:

        - normalize CRLF/CR to LF;
        - remove trailing spaces and tabs;
        - remove excessive blank lines;
        - remove leading/trailing empty lines.

        Markdown syntax itself is intentionally preserved.

        Parameters
        ----------
        content:
            Raw Markdown content.

        Returns
        -------
        str
            Normalized Markdown content.
        """
        content = content.replace("\r\n", "\n").replace("\r", "\n")

        lines = [line.rstrip(" \t") for line in content.split("\n")]

        normalized_lines: list[str] = []
        blank_count = 0

        for line in lines:
            if line.strip():
                blank_count = 0
                normalized_lines.append(line)
                continue

            blank_count += 1

            if blank_count <= 2:
                normalized_lines.append("")

        normalized = "\n".join(normalized_lines)

        return normalized.strip()

    @staticmethod
    def extract_headings(content: str) -> list[str]:
        """
        Extract Markdown headings from normalized content.

        This helper is intentionally independent from the main parsing
        process and can later be reused by a chunking strategy.

        Parameters
        ----------
        content:
            Markdown content.

        Returns
        -------
        list[str]
            Heading texts in document order.
        """
        headings: list[str] = []

        for line in content.splitlines():
            match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)

            if match:
                heading = match.group(1).strip()

                if heading:
                    headings.append(heading)

        return headings
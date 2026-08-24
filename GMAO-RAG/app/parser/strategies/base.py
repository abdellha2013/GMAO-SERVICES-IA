"""
Base contract for concrete parser strategies.

This module defines the common base class used by all concrete
parser strategies.

A strategy is responsible for determining whether it supports a
SourceDocument and for transforming that document into a
ParsedDocument.

The parser orchestrator remains responsible for selecting the
appropriate strategy.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.exceptions import ParserError, ParserValidationError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.base import ParserStrategy

__all__ = ["BaseParserStrategy"]


class BaseParserStrategy(ParserStrategy):
    """
    Base implementation shared by concrete parser strategies.

    This class provides common validation for parser strategies while
    leaving source-specific parsing logic to subclasses.

    Concrete strategies should implement:

    - ``name``
    - ``supports()``
    - ``parse()``

    Examples of concrete strategies include:

    - TextParser
    - MarkdownParser
    - HTMLParser
    - StructuredParser
    - DatabaseParser
    """

    def _validate_document(self, document: SourceDocument) -> None:
        """
        Validate a SourceDocument before parsing.

        Parameters
        ----------
        document : SourceDocument
            Document to validate.

        Raises
        ------
        ParserValidationError
            If the document is invalid or cannot be parsed.
        """
        if not isinstance(document, SourceDocument):
            raise ParserValidationError(
                "Parser expects a SourceDocument instance.",
                details={
                    "expected_type": "SourceDocument",
                    "received_type": type(document).__name__,
                },
            )

        if not isinstance(document.source_name, str):
            raise ParserValidationError(
                "SourceDocument source_name must be a string.",
                details={
                    "field": "source_name",
                    "received_type": type(
                        document.source_name
                    ).__name__,
                },
            )

        if not document.source_name.strip():
            raise ParserValidationError(
                "SourceDocument source_name must not be empty.",
                details={"field": "source_name"},
            )

        if not isinstance(document.source_type, str):
            raise ParserValidationError(
                "SourceDocument source_type must be a string.",
                details={
                    "field": "source_type",
                    "received_type": type(
                        document.source_type
                    ).__name__,
                },
            )

        if not document.source_type.strip():
            raise ParserValidationError(
                "SourceDocument source_type must not be empty.",
                details={"field": "source_type"},
            )

        if not isinstance(document.content, str):
            raise ParserValidationError(
                "SourceDocument content must be a string.",
                details={
                    "field": "content",
                    "received_type": type(
                        document.content
                    ).__name__,
                },
            )

    def _validate_content(self, document: SourceDocument) -> None:
        """
        Validate that the document contains usable content.

        Parameters
        ----------
        document : SourceDocument
            Document whose content should be validated.

        Raises
        ------
        ParserValidationError
            If the document content is empty or contains only
            whitespace.
        """
        self._validate_document(document)

        if not document.content.strip():
            raise ParserValidationError(
                "SourceDocument content must not be empty.",
                details={
                    "source_name": document.source_name,
                    "source_type": document.source_type,
                },
            )

    def _normalize_source_type(self, document: SourceDocument) -> str:
        """
        Return the normalized source type of a document.

        Parameters
        ----------
        document : SourceDocument
            Source document.

        Returns
        -------
        str
            Lowercase normalized source type.

        Raises
        ------
        ParserValidationError
            If the source type is invalid.
        """
        self._validate_document(document)

        return document.source_type.strip().lower()

    def _get_text_content(self, document: SourceDocument) -> str:
        """
        Return normalized textual content from a document.

        The method validates the document and removes leading and
        trailing whitespace without modifying the internal structure
        of the content.

        Parameters
        ----------
        document : SourceDocument
            Source document to read.

        Returns
        -------
        str
            Normalized document content.

        Raises
        ------
        ParserValidationError
            If the document or its content is invalid.
        """
        self._validate_content(document)

        return document.content.strip()

    def _build_parsed_document(
        self,
        document: SourceDocument,
        content: str,
        **overrides: Any,
    ) -> ParsedDocument:
        """
        Build a ParsedDocument from a SourceDocument.

        The method preserves provenance fields from the original
        document and populates ``parsed_at`` with the current UTC
        timestamp.

        Parameters
        ----------
        document:
            SourceDocument origin.

        content:
            Content already normalized by the strategy.

        **overrides:
            Optional fields to override in the resulting ParsedDocument.

        Returns
        -------
        ParsedDocument
        """
        fields = {
            "content": content,
            "source_name": document.source_name,
            "source_type": document.source_type,
            "source_path": document.source_path,
            "mime_type": document.mime_type,
            "size": document.size,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "parsed_at": datetime.now(timezone.utc),
            "metadata": dict(document.metadata),
        }
        fields.update(overrides)

        try:
            return ParsedDocument(**fields)
        except Exception as exc:
            raise ParserError(
                message="Failed to create ParsedDocument.",
                details={
                    "strategy": self.name,
                    "source_name": document.source_name,
                    "source_type": document.source_type,
                },
                original=exc,
            ) from exc

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique strategy name.

        Returns
        -------
        str
            Strategy identifier.

        Raises
        ------
        ParserValidationError
            If the concrete strategy exposes an invalid name.
        """
        raise NotImplementedError

    @abstractmethod
    def supports(self, document: SourceDocument) -> bool:
        """
        Determine whether the strategy supports a document.

        Parameters
        ----------
        document : SourceDocument
            Document to evaluate.

        Returns
        -------
        bool
            True when the strategy supports the document.

        Raises
        ------
        ParserValidationError
            If the document is invalid.
        """
        raise NotImplementedError

    @abstractmethod
    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse a SourceDocument into a ParsedDocument.

        Parameters
        ----------
        document : SourceDocument
            Document to parse.

        Returns
        -------
        ParsedDocument
            Normalized parsing result.

        Raises
        ------
        ParserValidationError
            If the document is invalid.

        ParserError
            If the concrete parsing operation fails.
        """
        raise NotImplementedError


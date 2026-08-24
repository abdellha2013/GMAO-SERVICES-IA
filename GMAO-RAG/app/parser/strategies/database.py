"""
MySQL database parser strategy.

This module parses SourceDocument instances produced by MySQLLoader.

The database loader is responsible for connecting to MySQL, executing the
validated read-only query, retrieving rows, and converting the result set
into textual content.

This strategy does not connect to MySQL and never executes SQL. Its role is
limited to validating and normalizing the already extracted database result
for the downstream RAG pipeline.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from app.exceptions import ParserValidationError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.strategies.base import BaseParserStrategy


class DatabaseParser(BaseParserStrategy):
    """
    Parser strategy for database result documents.

    The strategy currently targets SourceDocument instances produced by
    MySQLLoader.

    Supported source type
    ---------------------
    ``mysql``

    Supported MySQL result values include:

    - NULL
    - strings
    - integers
    - floats
    - Decimal
    - booleans
    - date
    - datetime
    - time
    - dictionaries
    - lists
    - JSON-compatible values
    - arbitrary Python objects with a string representation

    The parser does not:

    - open database connections;
    - execute SQL queries;
    - modify database data;
    - access credentials;
    - access the original database;
    - perform chunking;
    - generate embeddings.
    """

    SUPPORTED_SOURCE_TYPES = frozenset({"mysql"})

    SUPPORTED_MIME_TYPES = frozenset(
        {
            "application/x-mysql-resultset",
        }
    )

    _LEGACY_ROW_MARKER = re.compile(r"^---\s*Row\s+\d+\s*---$", re.IGNORECASE)

    @property
    def name(self) -> str:
        """
        Return the unique strategy name.

        Returns
        -------
        str
            Strategy identifier used by the parser registry.
        """
        return "database"

    def supports(self, document: SourceDocument) -> bool:
        """
        Check whether this strategy supports the document.

        The primary routing mechanism is ``source_type``. The MySQL
        result-set MIME type is accepted as a secondary indicator.

        Parameters
        ----------
        document : SourceDocument
            Source document to evaluate.

        Returns
        -------
        bool
            True when the document represents a supported MySQL result.

        Raises
        ------
        ParserValidationError
            If the document itself is invalid.
        """
        self._validate_document(document)

        source_type = document.source_type.strip().lower()
        mime_type = (document.mime_type or "").strip().lower()

        return (
            source_type in self.SUPPORTED_SOURCE_TYPES
            or mime_type in self.SUPPORTED_MIME_TYPES
        )

    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse a MySQL SourceDocument.

        The method validates the document, verifies that it belongs to the
        supported database source, normalizes the textual result-set
        representation, and returns a ParsedDocument.

        Parameters
        ----------
        document : SourceDocument
            Document produced by MySQLLoader.

        Returns
        -------
        ParsedDocument
            Normalized database result.

        Raises
        ------
        ParserValidationError
            If the document is invalid, unsupported, or contains no
            meaningful database result.
        """
        self._validate_content(document)

        if not self.supports(document):
            raise ParserValidationError(
                message="DatabaseParser does not support this document.",
                details={
                    "source_type": document.source_type,
                    "mime_type": document.mime_type,
                    "strategy": self.name,
                },
            )

        content = self._normalize_content(document.content)

        if not content:
            raise ParserValidationError(
                message="Database result contains no meaningful content.",
                details={
                    "source_name": document.source_name,
                    "source_type": document.source_type,
                    "strategy": self.name,
                },
            )

        return self._build_parsed_document(
            document,
            content,
        )

    @staticmethod
    def _normalize_content(content: str) -> str:
        """
        Normalize textual database result content.

        The method preserves row and column boundaries while removing
        unnecessary whitespace around the complete result. It also removes
        legacy ``--- Row N ---`` markers emitted by older MySQL loaders, so
        those technical labels can never reach RAG storage.

        It intentionally does not reinterpret SQL syntax because the SQL
        query has already been validated and executed by MySQLLoader.

        Parameters
        ----------
        content : str
            Textual result produced by MySQLLoader.

        Returns
        -------
        str
            Normalized database result.
        """
        lines: list[str] = []

        for line in content.splitlines():
            normalized = line.strip()

            if normalized and not DatabaseParser._LEGACY_ROW_MARKER.fullmatch(normalized):
                lines.append(normalized)

        return "\n".join(lines).strip()

    @staticmethod
    def format_value(value: Any) -> str:
        """
        Convert a database value into a stable textual representation.

        This helper is public at class level because it can also be useful
        when validating or testing database result formatting.

        Parameters
        ----------
        value : Any
            Database value.

        Returns
        -------
        str
            Human-readable textual representation.

        Notes
        -----
        NULL is represented as ``NULL``.

        JSON-compatible dictionaries and lists are serialized using UTF-8
        characters without ASCII escaping.
        """
        if value is None:
            return "NULL"

        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"

        if isinstance(value, datetime):
            return value.isoformat(sep=" ")

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, time):
            return value.isoformat()

        if isinstance(value, Decimal):
            return format(value, "f")

        if isinstance(value, (dict, list, tuple)):
            try:
                return json.dumps(
                    value,
                    ensure_ascii=False,
                    default=str,
                )
            except (TypeError, ValueError):
                return str(value)

        return str(value)

    @classmethod
    def format_row(
        cls,
        row: dict[str, Any],
    ) -> str:
        """
        Format one database row as readable text.

        Parameters
        ----------
        row : dict[str, Any]
            Mapping of column names to database values.

        Returns
        -------
        str
            One normalized textual representation of the row.

        Examples
        --------
        A row such as::

            {
                "id": 1,
                "name": "Pump A",
                "active": True,
                "temperature": Decimal("24.50"),
                "description": None,
            }

        becomes conceptually::

            id: 1 | name: Pump A | active: TRUE |
            temperature: 24.50 | description: NULL
        """
        if not isinstance(row, dict):
            raise ParserValidationError(
                message="Database row must be a dictionary.",
                details={
                    "received_type": type(row).__name__,
                },
            )

        parts: list[str] = []

        for column, value in row.items():
            column_name = str(column).strip()

            if not column_name:
                column_name = "<unnamed>"

            parts.append(
                f"{column_name}: {cls.format_value(value)}"
            )

        return " | ".join(parts)

    @classmethod
    def format_rows(
        cls,
        rows: list[dict[str, Any]],
    ) -> str:
        """
        Format multiple database rows as readable text.

        This method is mainly useful for tests and future integrations
        where structured rows are available before being converted into
        SourceDocument.content.

        Parameters
        ----------
        rows : list[dict[str, Any]]
            Database result rows.

        Returns
        -------
        str
            One row per line.

        Raises
        ------
        ParserValidationError
            If rows is not a list or contains invalid rows.
        """
        if not isinstance(rows, list):
            raise ParserValidationError(
                message="Database rows must be provided as a list.",
                details={
                    "received_type": type(rows).__name__,
                },
            )

        if not rows:
            return ""

        formatted_rows: list[str] = []

        for row in rows:
            formatted_rows.append(
                cls.format_row(row)
            )

        return "\n".join(formatted_rows).strip()

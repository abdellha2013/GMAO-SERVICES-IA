"""
Structured data parser strategy.

This module provides the parser strategy for structured source
documents such as JSON, CSV, and XLSX.

The loader is responsible for extracting the source content.
This strategy only validates, normalizes, and structures the
already extracted textual content.

Pipeline
--------

    JSON / CSV / XLSX
            ↓
          Loader
            ↓
      SourceDocument
            ↓
    StructuredParser
            ↓
      ParsedDocument
            ↓
          Chunker
"""

from __future__ import annotations

import json

from app.exceptions import ParserValidationError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.strategies.base import BaseParserStrategy


class StructuredParser(BaseParserStrategy):
    """
    Parser strategy for structured documents.

    Supported source types are:

    - JSON
    - CSV
    - XLSX

    The strategy does not access the filesystem, database, or
    original source. It operates exclusively on SourceDocument.content.
    """

    SUPPORTED_SOURCE_TYPES = frozenset(
        {
            "json",
            "csv",
            "xlsx",
        }
    )

    SUPPORTED_MIME_TYPES = frozenset(
        {
            "application/json",
            "text/json",
            "text/csv",
            "application/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }
    )

    @property
    def name(self) -> str:
        """
        Return the unique strategy name.

        Returns
        -------
        str
            Strategy identifier.
        """
        return "structured"

    def supports(
        self,
        document: SourceDocument,
    ) -> bool:
        """
        Check whether the document is supported.

        Detection uses source_type first and MIME type as a
        secondary indicator.

        Parameters
        ----------
        document:
            SourceDocument to evaluate.

        Returns
        -------
        bool
            True when the document is a supported structured format.

        Raises
        ------
        ParserValidationError
            If the document is invalid.
        """
        self._validate_document(document)

        source_type = (
            document.source_type.strip().lower()
        )

        mime_type = (
            (document.mime_type or "")
            .strip()
            .lower()
        )

        return (
            source_type in self.SUPPORTED_SOURCE_TYPES
            or mime_type in self.SUPPORTED_MIME_TYPES
        )

    def parse(
        self,
        document: SourceDocument,
    ) -> ParsedDocument:
        """
        Parse a structured SourceDocument.

        JSON content is validated and normalized into a stable
        pretty-printed representation.

        CSV and XLSX content are already extracted by their
        respective loaders, so the parser performs textual
        normalization without reopening or reparsing the source.

        Parameters
        ----------
        document:
            Structured SourceDocument produced by a loader.

        Returns
        -------
        ParsedDocument
            Normalized structured document.

        Raises
        ------
        ParserValidationError
            If the document is invalid, unsupported, empty,
            or contains invalid JSON.
        """
        self._validate_content(document)

        if not self.supports(document):
            raise ParserValidationError(
                message=(
                    "StructuredParser does not support "
                    "this document."
                ),
                details={
                    "source_type": document.source_type,
                    "mime_type": document.mime_type,
                    "strategy": self.name,
                },
            )

        source_type = (
            document.source_type.strip().lower()
        )

        if source_type == "json":
            content = self._parse_json(
                document.content,
            )
        elif source_type in {"csv", "xlsx"}:
            content = self._normalize_tabular_content(
                document.content,
            )
        else:
            content = self._parse_by_mime_type(
                document,
            )

        if not content:
            raise ParserValidationError(
                message=(
                    "Structured document contains "
                    "no meaningful content."
                ),
                details={
                    "source_name": document.source_name,
                    "source_type": document.source_type,
                    "mime_type": document.mime_type,
                    "strategy": self.name,
                },
            )

        return self._build_parsed_document(
            document,
            content,
        )

    # ==========================================================
    # JSON
    # ==========================================================

    @staticmethod
    def _parse_json(
        content: str,
    ) -> str:
        """
        Validate and normalize JSON content.

        The resulting representation is deterministic and
        UTF-8 friendly.  When the content is already flattened
        (e.g. produced by ``JSONLoader``), it is returned as-is
        since ``json.loads`` cannot parse ``path: value`` lines.

        Parameters
        ----------
        content:
            Raw JSON text or pre-flattened ``path: value`` lines.

        Returns
        -------
        str
            Pretty-printed JSON or the original content if already
            flattened.

        Raises
        ------
        ParserValidationError
            If the JSON content is invalid and not flattened.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Content is already flattened (e.g. from JSONLoader) —
            # return as-is since it's in a readable format.
            return content.strip()

        try:
            normalized = json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
        except (TypeError, ValueError) as exc:
            raise ParserValidationError(
                message=(
                    "JSON content could not be normalized."
                ),
                details={
                    "error_type": type(exc).__name__,
                },
                original=exc,
            ) from exc

        return normalized.strip()

    # ==========================================================
    # Tabular Data
    # ==========================================================

    @staticmethod
    def _normalize_tabular_content(
        content: str,
    ) -> str:
        """
        Normalize already-extracted CSV/XLSX text.

        The method deliberately does not parse the original
        file format. CSV/XLSX extraction is the responsibility
        of the corresponding loader.

        Empty lines are removed and surrounding whitespace is
        normalized while preserving row boundaries.

        Parameters
        ----------
        content:
            Text produced by a CSV or XLSX loader.

        Returns
        -------
        str
            Normalized tabular text.
        """
        lines: list[str] = []

        for line in content.splitlines():
            normalized = line.strip()

            if normalized:
                lines.append(normalized)

        return "\n".join(lines).strip()

    # ==========================================================
    # MIME Fallback
    # ==========================================================

    def _parse_by_mime_type(
        self,
        document: SourceDocument,
    ) -> str:
        """
        Parse a structured document using its MIME type.

        This fallback is useful when source_type is not one of
        the canonical values but the MIME type clearly identifies
        a supported structured format.

        Parameters
        ----------
        document:
            SourceDocument to normalize.

        Returns
        -------
        str
            Normalized content.

        Raises
        ------
        ParserValidationError
            If the MIME type cannot determine a supported format.
        """
        mime_type = (
            (document.mime_type or "")
            .strip()
            .lower()
        )

        if mime_type in {
            "application/json",
            "text/json",
        }:
            return self._parse_json(
                document.content,
            )

        if mime_type in {
            "text/csv",
            "application/csv",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }:
            return self._normalize_tabular_content(
                document.content,
            )

        raise ParserValidationError(
            message=(
                "Unable to determine the structured "
                "document format."
            ),
            details={
                "source_type": document.source_type,
                "mime_type": document.mime_type,
                "strategy": self.name,
            },
        )
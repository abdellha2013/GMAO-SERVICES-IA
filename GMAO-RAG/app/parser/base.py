"""
Base contract for parser strategies.

This module defines the common interface implemented by every parser
strategy in the parsing layer.

Each strategy receives a SourceDocument and transforms it into a
ParsedDocument. Concrete parsing logic belongs to the individual
strategy implementations.

The strategy contract is intentionally small:
    SourceDocument -> ParsedDocument
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument


class ParserStrategy(ABC):
    """
    Abstract contract for a parser strategy.

    A parser strategy is responsible for transforming a single
    SourceDocument into a normalized ParsedDocument.

    Concrete implementations may target different source families,
    such as:

    - plain text
    - Markdown
    - HTML
    - structured data
    - database results

    The strategy must not be responsible for selecting another
    strategy. Strategy selection belongs to the parser orchestrator
    and registry.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique name of the parser strategy.

        The name is used for identification, logging, diagnostics,
        and registry-related operations.

        Returns
        -------
        str
            Unique strategy identifier.

        Raises
        ------
        ParserError
            If a concrete implementation cannot provide a valid
            strategy name.
        """
        raise NotImplementedError

    @abstractmethod
    def supports(self, document: SourceDocument) -> bool:
        """
        Determine whether this strategy supports the given document.

        This method must only determine compatibility. It must not
        perform the actual parsing operation.

        Parameters
        ----------
        document : SourceDocument
            Source document produced by a data source loader.

        Returns
        -------
        bool
            True when this strategy can parse the document,
            otherwise False.

        Raises
        ------
        ParserError
            If the document cannot be evaluated because of an
            invalid parser-specific condition.
        """
        raise NotImplementedError

    @abstractmethod
    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse a SourceDocument into a ParsedDocument.

        The implementation is responsible for transforming the
        document content into the normalized parser representation.

        Strategy implementations should preserve relevant source
        information and parsing metadata required by downstream
        components such as the future chunking layer.

        Parameters
        ----------
        document : SourceDocument
            Source document produced by a data source loader.

        Returns
        -------
        ParsedDocument
            Normalized parsing result.

        Raises
        ------
        ParserError
            If the document cannot be parsed successfully.
        """
        raise NotImplementedError


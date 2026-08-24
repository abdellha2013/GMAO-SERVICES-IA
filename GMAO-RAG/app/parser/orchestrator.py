"""
Parser orchestrator.

This module selects the appropriate parser strategy for a given
SourceDocument and executes the parsing operation.

Strategy storage and lookup are handled by ParserRegistry. This
module is only responsible for orchestration: resolving the source
type, retrieving the matching strategy, instantiating it, and
delegating to its parse() method.
"""

from __future__ import annotations

from app.exceptions import ParserError
from app.models.document import SourceDocument
from app.models.parsing import ParsedDocument
from app.parser.registry import ParserRegistry


class ParserOrchestrator:
    """
    Resolves and executes the parser strategy for a SourceDocument.

    Parameters
    ----------
    registry : ParserRegistry
        Registry containing the strategies available for selection.
    """

    def __init__(self, registry: ParserRegistry) -> None:
        self._registry = registry

    def parse(self, document: SourceDocument) -> ParsedDocument:
        """
        Parse a SourceDocument using the strategy registered for its
        source_type.

        Parameters
        ----------
        document : SourceDocument
            Document to parse.

        Returns
        -------
        ParsedDocument

        Raises
        ------
        ParserStrategyNotRegisteredError
            If no strategy is registered for document.source_type.

        ParserError
            If the resolved strategy fails to parse the document.
        """
        strategy_cls = self._registry.get(document.source_type)
        strategy = strategy_cls()

        if not strategy.supports(document):
            raise ParserError(
                message="Resolved strategy does not support this document.",
                details={
                    "strategy": strategy.name,
                    "source_type": document.source_type,
                    "source_name": document.source_name,
                },
            )

        return strategy.parse(document)
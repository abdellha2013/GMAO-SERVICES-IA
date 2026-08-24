"""
Parser package.

This package contains the parsing layer of the GMAO-RAG pipeline.

It exposes the strategy contract (``ParserStrategy``), the strategy
registry (``ParserRegistry``), and the concrete parser strategies
responsible for transforming a ``SourceDocument`` into a
``ParsedDocument``.

Strategy selection and orchestration are the responsibility of the
parser registry and the upstream RAG pipeline, not of this package
itself.
"""

from __future__ import annotations

from app.parser.base import ParserStrategy
from app.parser.registry import ParserRegistry
from app.parser.strategies import (
    ALL_STRATEGIES,
    BaseParserStrategy,
    DatabaseParser,
    HTMLParser,
    MarkdownParser,
    StructuredParser,
    TextParser,
)
from app.parser.orchestrator import ParserOrchestrator

__all__ = [
    "ParserStrategy",
    "ParserRegistry",
    "BaseParserStrategy",
    "DatabaseParser",
    "HTMLParser",
    "MarkdownParser",
    "StructuredParser",
    "TextParser",
    "ParserOrchestrator",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> ParserRegistry:
    """Build a registry containing every parser strategy shipped by default."""
    registry = ParserRegistry()
    for strategy in ALL_STRATEGIES:
        registry.register(strategy)
    return registry


def build_default_orchestrator() -> ParserOrchestrator:
    """Build a parser orchestrator ready for every supported source type."""
    return ParserOrchestrator(build_default_registry())

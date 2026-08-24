"""
Parser strategies package.

This package contains the concrete parser strategies used by the
GMAO-RAG parser layer.

Each strategy is responsible for handling a specific family of
SourceDocument instances.
"""

from __future__ import annotations

from app.parser.strategies.base import BaseParserStrategy
from app.parser.strategies.database import DatabaseParser
from app.parser.strategies.html import HTMLParser
from app.parser.strategies.markdown import MarkdownParser
from app.parser.strategies.structured import StructuredParser
from app.parser.strategies.text import TextParser

ALL_STRATEGIES = (
    DatabaseParser,
    HTMLParser,
    MarkdownParser,
    StructuredParser,
    TextParser,
)

__all__ = [
    "BaseParserStrategy",
    "DatabaseParser",
    "HTMLParser",
    "MarkdownParser",
    "StructuredParser",
    "TextParser",
    "ALL_STRATEGIES",
]

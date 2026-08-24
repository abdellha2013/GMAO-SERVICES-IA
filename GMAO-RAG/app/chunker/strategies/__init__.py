"""
app/chunker/strategies/__init__.py
===================================

Point d'entrée public des stratégies de chunking concrètes.

Ce module centralise l'import des stratégies afin de simplifier
leur usage ailleurs dans le projet.

Exemple
-------
Au lieu de :

    from app.chunker.strategies.markdown import MarkdownChunker
    from app.chunker.strategies.structured import StructuredChunker
    from app.chunker.strategies.recursive import RecursiveChunker

on peut simplement écrire :

    from app.chunker.strategies import (
        MarkdownChunker,
        StructuredChunker,
        RecursiveChunker,
    )
"""

from __future__ import annotations

from app.chunker.strategies.base import BaseChunkerStrategy
from app.chunker.strategies.markdown import MarkdownChunker
from app.chunker.strategies.structured import StructuredChunker
from app.chunker.strategies.recursive import RecursiveChunker

__all__ = [
    "BaseChunkerStrategy",
    "MarkdownChunker",
    "StructuredChunker",
    "RecursiveChunker",
    "ALL_STRATEGIES",
]

# ==============================================================
# Registre de toutes les stratégies connues, dans l'ordre où
# elles doivent être enregistrées. Sert de source unique de
# vérité pour construire un ChunkerRegistry pré-rempli (voir
# app.chunker.build_default_registry).
# ==============================================================

ALL_STRATEGIES: tuple[type, ...] = (
    MarkdownChunker,
    StructuredChunker,
    RecursiveChunker,
)
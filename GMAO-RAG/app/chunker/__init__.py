"""
app/chunker/__init__.py
========================

Point d'entrée public de la couche Chunker.

Ce module centralise les imports des composants principaux du
pipeline de chunking (registre, orchestrateur, contrat de base)
et fournit un utilitaire pour construire un registre pré-rempli
avec toutes les stratégies disponibles.

Exemple
-------
Au lieu de :

    from app.chunker.base import ChunkerStrategy
    from app.chunker.registry import ChunkerRegistry
    from app.chunker.orchestrator import ChunkerOrchestrator
    from app.chunker.strategies.markdown import MarkdownChunker
    from app.chunker.strategies.structured import StructuredChunker
    from app.chunker.strategies.recursive import RecursiveChunker

    registry = ChunkerRegistry()
    registry.register(MarkdownChunker)
    registry.register(StructuredChunker)
    registry.register(RecursiveChunker)
    orchestrator = ChunkerOrchestrator(registry=registry)

on peut simplement écrire :

    from app.chunker import build_default_orchestrator

    orchestrator = build_default_orchestrator()

Notes
-----
Il n'existe qu'un seul contrat de stratégie : ``ChunkerStrategy``,
défini dans ``app.chunker.base``. Le fichier ``chunker.py`` qui
dupliquait ce contrat a été supprimé : il n'était utilisé nulle
part et créait un risque silencieux d'incompatibilité (deux
classes ``ChunkerStrategy`` distinctes, ``issubclass()`` renvoyant
``False`` entre elles selon le module importé).
"""

from __future__ import annotations

from app.chunker.base import ChunkerStrategy
from app.chunker.registry import ChunkerRegistry
from app.chunker.orchestrator import ChunkerOrchestrator
from app.chunker.strategies import ALL_STRATEGIES

__all__ = [
    "ChunkerStrategy",
    "ChunkerRegistry",
    "ChunkerOrchestrator",
    "build_default_registry",
    "build_default_orchestrator",
]


def build_default_registry() -> ChunkerRegistry:
    """
    Construire un ChunkerRegistry pré-rempli avec toutes les
    stratégies de chunking connues du projet.

    Returns
    -------
    ChunkerRegistry
        Registre avec MarkdownChunker, StructuredChunker et
        RecursiveChunker déjà enregistrés.
    """

    registry = ChunkerRegistry()

    for strategy in ALL_STRATEGIES:
        registry.register(strategy)

    return registry


def build_default_orchestrator(
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> ChunkerOrchestrator:
    """
    Construire un ChunkerOrchestrator prêt à l'emploi, avec
    toutes les stratégies par défaut déjà enregistrées.

    Parameters
    ----------
    chunk_size : int
        Taille maximale d'un chunk.

    chunk_overlap : int
        Chevauchement entre chunks consécutifs.

    Returns
    -------
    ChunkerOrchestrator
        Orchestrateur configuré et prêt à chunker des
        ParsedDocument.
    """

    return ChunkerOrchestrator(
        registry=build_default_registry(),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
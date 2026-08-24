"""
app/data_sources/interfaces/__init__.py
=======================================

Point d'entrée du sous-package interfaces.

Expose le contrat commun de toutes les sources de données du
projet : la classe abstraite ``BaseSource`` (Template Method
Pattern) ainsi que l'énumération ``SourceState`` décrivant son
cycle de vie.
"""

from __future__ import annotations

from app.data_sources.interfaces.base_source import BaseSource, SourceState

__all__ = [
    "BaseSource",
    "SourceState",
]

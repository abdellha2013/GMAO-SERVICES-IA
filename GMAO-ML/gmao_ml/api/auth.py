"""API key authentication middleware — DÉSACTIVÉ.

Tous les services communiquent librement sans clé API.
L'auth est complètement désactivée pour simplifier le développement.
"""
from __future__ import annotations


async def verify_api_key(authorize: str | None = None) -> str:
    """Toujours accepter — pas d'authentification."""
    return "dev-mode"


__all__ = ["verify_api_key"]

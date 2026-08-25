"""Authentification GMAO-API — DÉSACTIVÉE.

Tous les services communiquent librement sans clé API.
"""

from __future__ import annotations


async def verify_api_key() -> str:
    """Toujours accepter — pas d'authentification."""
    return "dev-mode"


__all__ = ["verify_api_key"]

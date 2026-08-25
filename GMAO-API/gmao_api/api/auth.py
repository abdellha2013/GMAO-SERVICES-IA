"""Authentification GMAO-API — Bearer ``GMAO_API_KEY``.

Si ``GMAO_API_KEY`` n'est pas configurée, l'auth est **désactivée**
(mode dev / dashboard local) : tout le monde est accepté.

Si ``GMAO_API_KEY`` est configurée, l'en-tête ``Authorization: Bearer <clé>``
est requis (absent → 422, invalide → 401).
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, Request, status


def _get_api_key() -> str | None:
    return os.getenv("GMAO_API_KEY") or None


async def verify_api_key(
    request: Request,
    authorize: str | None = Header(None, alias="Authorization"),
) -> str | None:
    """Dépendance FastAPI validant ``Authorization: Bearer <clé>``.

    Si aucune clé n'est configurée (``GMAO_API_KEY`` absent + settings vide),
    mode dev : tout le monde passe, retourne ``"dev-mode"``.
    """

    configured_key = getattr(
        getattr(request.app.state, "settings", None), "api_key", None
    )
    configured_key = configured_key or _get_api_key()

    # Mode dev : aucune clé configurée → pas d'auth
    if not configured_key:
        return "dev-mode"

    # Clé configurée mais header absent
    if authorize is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Expected 'Bearer <key>'.",
        )

    if not authorize.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Expected 'Bearer <key>'.",
        )

    token = authorize[7:]

    if not hmac.compare_digest(token.encode(), configured_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return token


__all__ = ["verify_api_key"]

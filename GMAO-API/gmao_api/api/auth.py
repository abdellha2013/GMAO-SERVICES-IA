"""Authentification GMAO-API — Bearer ``GMAO_API_KEY``.

Comportement identique à GMAO-ML : en-tête ``Authorization`` requis
(absent → 422 via validation FastAPI, invalide → 401).
"""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, Request, status


def _get_api_key() -> str | None:
    return os.getenv("GMAO_API_KEY")


async def verify_api_key(
    request: Request,
    authorize: str = Header(..., alias="Authorization"),
) -> str:
    """Dépendance FastAPI validant ``Authorization: Bearer <clé>``."""

    if not authorize.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Expected 'Bearer <key>'.",
        )

    token = authorize[7:]
    # Clé injectée via Settings (app.state) sinon environnement.
    configured_key = getattr(getattr(request.app.state, "settings", None), "api_key", None)
    configured_key = configured_key or _get_api_key()

    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured (missing GMAO_API_KEY).",
        )

    if not hmac.compare_digest(token.encode(), configured_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return token


__all__ = ["verify_api_key"]

"""API key authentication middleware.

The Laravel backend authenticates with FastAPI using a shared secret
sent in the ``Authorization`` header::

    Authorization: Bearer <RAG_API_KEY>

The key is read from the ``RAG_API_KEY`` environment variable.  If the
variable is not set, authentication is **disabled** (development mode).
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException


def _get_api_key() -> str | None:
    """Return the configured API key, or ``None`` if unset."""
    return os.getenv("RAG_API_KEY")


async def verify_api_key(authorize: str = Header(..., alias="Authorization")) -> str:
    """Validate the Bearer token from the ``Authorization`` header.

    Parameters
    ----------
    authorize:
        Raw ``Authorization`` header value (e.g. ``"Bearer abc123"``).

    Returns
    -------
    str
        The validated token string.

    Raises
    ------
    HTTPException
        401 if the token is missing, malformed, or invalid.
    """
    configured_key = _get_api_key()

    # --- Dev mode: no key configured → skip validation ---
    if configured_key is None:
        return "dev-mode"

    # --- Validate header format ---
    if not isinstance(authorize, str) or not authorize.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header. Expected 'Bearer <token>'.",
        )

    token = authorize[7:]  # strip "Bearer " prefix

    if token != configured_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )

    return token

"""Hiérarchie d'erreurs GMAO-API (format de réponse : message / error_code / details)."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Erreur métier/technique exposée proprement par l'API."""

    http_status: int = 500
    error_code: str = "API_INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        if http_status is not None:
            self.http_status = http_status
        self.details: dict[str, Any] = details or {}

    def to_body(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class MlUpstreamError(ApiError):
    """GMAO-ML injoignable, lent, ou réponse invalide."""

    http_status = 503
    error_code = "ML_UNREACHABLE"


__all__ = ["ApiError", "MlUpstreamError"]

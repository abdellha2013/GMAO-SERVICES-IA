"""
gmao_ml/exceptions/base_exception.py
====================================

Description
-----------
Définition de l'exception de base du sous-projet GMAO-ML.

Toutes les exceptions personnalisées du sous-projet héritent de
``MLError``, calquée sur ``GMAOError`` (GMAO-RAG) pour garantir un
comportement homogène dans tout le monorepo.

Cette classe fournit une structure commune pour :

- un message lisible ;
- un code d'erreur optionnel ;
- des informations complémentaires (details) ;
- une exception d'origine (original) ;
- un code HTTP optionnel.

Diagramme UML
-------------

       +-----------------------+
       |       Exception       |  <-- Classe native de Python
       +-----------------------+
                   ▲
                   │ (Héritage)
+-------------------------------------------------------------------------+
|                                MLError                                  |
|                        {slots, kw_only}                                 |
+-------------------------------------------------------------------------+
| + message : str                                                         |
| + error_code : str | None = None                                        |
| + details : dict[str, Any]                                              |
| + original : Exception | None = None                                    |
| + http_status : int | None = None                                       |
| / has_details : bool {readOnly}                                         |
| / cause : Exception | None {readOnly}                                   |
+-------------------------------------------------------------------------+
| + to_dict() : dict[str, Any]                                            |
| + with_original(exc: Exception) : MLError                               |
| + __str__() : str                                                       |
| + __repr__() : str                                                      |
+-------------------------------------------------------------------------+
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = ["MLError"]


def _serialize_value(value: Any) -> Any:
    """Convertit récursivement une valeur en un type compatible JSON.

    Les objets inconnus sont automatiquement convertis en chaîne de
    caractères afin d'éviter toute erreur de sérialisation.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, dict):
        return {
            str(key): _serialize_value(val)
            for key, val in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(val) for val in value]

    try:
        return str(value)
    except Exception:
        return repr(value)


@dataclass(
    slots=True,
    kw_only=True,
)
class MLError(Exception):
    """Exception de base du sous-projet GMAO-ML.

    Parameters
    ----------
    message:
        Description de l'erreur.

    error_code:
        Code d'erreur métier.

    details:
        Informations techniques complémentaires.

    original:
        Exception d'origine.

    http_status:
        Code HTTP associé à cette erreur.
    """

    message: str

    error_code: str | None = None

    details: dict[str, Any] = field(default_factory=dict)

    original: Exception | None = None

    http_status: int | None = None

    def __post_init__(self) -> None:
        """Valide les paramètres et normalise les champs."""

        if not self.message or not self.message.strip():
            raise ValueError(
                "The exception message cannot be empty."
            )

        if self.details is None:
            object.__setattr__(self, "details", {})

        Exception.__init__(self, self.message)

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def has_details(self) -> bool:
        """Indique si des informations complémentaires sont disponibles."""

        return bool(self.details)

    @property
    def cause(self) -> Exception | None:
        """Retourne l'exception d'origine chaînée si présente."""

        if self.original is not None:
            return self.original
        return self.__cause__ or self.__context__

    # ==========================================================
    # Serialization
    # ==========================================================

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'exception en dictionnaire compatible JSON."""

        data = {
            "type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "http_status": self.http_status,
            "details": _serialize_value(self.details),
        }

        origin = self.cause
        if origin is not None:
            data["original"] = {
                "type": origin.__class__.__name__,
                "message": str(origin),
            }

        return data

    # ==========================================================
    # Utilities
    # ==========================================================

    def with_original(self, exc: Exception) -> "MLError":
        """Retourne une nouvelle exception contenant l'origine chaînée."""

        return replace(self, original=exc)

    # ==========================================================
    # Display
    # ==========================================================

    def __str__(self) -> str:
        """Représentation lisible de l'erreur."""

        if self.error_code:
            return f"[{self.error_code}] {self.message}"

        return self.message

    def __repr__(self) -> str:
        """Représentation destinée au débogage (details volontairement omis)."""

        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"http_status={self.http_status!r}, "
            f"details_keys={list(self.details.keys())!r})"
        )

"""
app/exceptions/base_exception.py
================================

Description
-----------
Définition de l'exception de base du projet GMAO AI Service.

Toutes les exceptions personnalisées du projet doivent hériter de
`GMAOError`.

Cette classe fournit une structure commune pour :

- un message lisible ;
- un code d'erreur optionnel ;
- des informations complémentaires (details) ;
- une exception d'origine (original) ;
- un code HTTP optionnel.

Elle facilite :

- la journalisation (logging) ;
- le débogage ;
- la sérialisation JSON ;
- les réponses des APIs ;
- les tests unitaires.

Diagramme UML
-------------
       +-----------------------+
       |       Exception       |  <-- Classe native de Python
       +-----------------------+
                   ▲
                   │ (Héritage)
+-------------------------------------------------------------------------+
|                                GMAOError                                |
|                        {frozen, slots, kw_only}                         |
+-------------------------------------------------------------------------+
| + message : str                                                         |
| + error_code : str | None = None                                        |
| + details : dict[str, Any]                                              |
| + original : Exception | None = None                                    |
| + http_status : int | None = None                                       |
| / has_details : bool {readOnly}                                         |
| / cause : Exception | None {readOnly}                                   |
+-------------------------------------------------------------------------+
| + __post_init__() : None                                                |
| + to_dict() : dict[str, Any]                                            |
| + with_original(exc: Exception) : GMAOError                             |
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

__all__ = ["GMAOError"]


def _serialize_value(value: Any) -> Any:
    """
    Convertit récursivement une valeur en un type compatible JSON.

    Types supportés
    ----------------
    - None
    - bool
    - int
    - float
    - str
    - datetime
    - date
    - Path
    - Enum
    - dict
    - list
    - tuple
    - set

    Les objets inconnus sont automatiquement convertis
    en chaîne de caractères afin d'éviter toute erreur
    de sérialisation JSON.
    """

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
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
        return [_serialize_value(item) for item in value]

    # Fallback : garantit toujours une valeur sérialisable.
    try:
        return str(value)
    except Exception:
        return repr(value)


@dataclass(
    frozen=False,
    slots=True,
    kw_only=True,
)
class GMAOError(Exception):
    """
    Exception de base du projet.

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
        """
        Vérifie la validité des paramètres et normalise les champs.

        Note
        ----
        Les sous-classes (ParserError, ChunkerError, ...) acceptent
        souvent ``details: dict | None = None`` dans leur propre
        signature et transmettent cette valeur telle quelle. Si on ne
        la normalisait pas ici, ``self.details`` resterait à ``None``
        au lieu du ``dict()`` vide attendu par ``has_details``,
        ``to_dict()`` et ``__repr__()``, provoquant un crash
        (``AttributeError: 'NoneType' object has no attribute 'keys'``)
        dès qu'on logue ou sérialise l'exception. On corrige donc ici,
        une bonne fois pour toutes, pour que TOUTES les couches du
        pipeline (data source, file, database, parser, chunker)
        bénéficient de la même garantie.
        """
        if not self.message or not self.message.strip():
            raise ValueError(
                "The exception message cannot be empty."
            )

        if self.details is None:
            # dataclass est frozen -> passage par object.__setattr__.
            object.__setattr__(self, "details", {})

        Exception.__init__(self, self.message)

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def has_details(self) -> bool:
        """
        Indique si des informations complémentaires sont disponibles.
        """
        return bool(self.details)

    @property
    def cause(self) -> Exception | None:
        """
        Retourne l'exception d'origine.

        Retombe sur ``__cause__`` / ``__context__`` (posés par
        ``raise ... from ...``) si ``original`` n'a pas été fourni
        explicitement, afin d'éviter d'avoir deux mécanismes de
        chaînage d'erreurs qui se contredisent.
        """
        if self.original is not None:
            return self.original
        return self.__cause__ or self.__context__

    # ==========================================================
    # Serialization
    # ==========================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Convertit l'exception en dictionnaire compatible JSON.

        Returns
        -------
        dict[str, Any]
            Représentation sérialisable de l'exception.
        """

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

    def with_original(self, exc: Exception) -> "GMAOError":
        """
        Retourne une nouvelle exception contenant
        l'exception d'origine.

        Parameters
        ----------
        exc:
            Exception à chaîner.

        Returns
        -------
        GMAOError
        """
        return replace(self, original=exc)

    # ==========================================================
    # Display
    # ==========================================================

    def __str__(self) -> str:
        """
        Représentation lisible de l'exception.
        """
        if self.error_code:
            return f"[{self.error_code}] {self.message}"

        return self.message

    def __repr__(self) -> str:
        """
        Représentation destinée au débogage.

        Le contenu complet de 'details' n'est volontairement
        pas affiché afin d'éviter des logs trop volumineux.
        """
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code!r}, "
            f"http_status={self.http_status!r}, "
            f"details_keys={list(self.details.keys())!r})"
        )






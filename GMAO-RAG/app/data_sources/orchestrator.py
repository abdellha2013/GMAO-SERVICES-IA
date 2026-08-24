"""
app/data_sources/orchestrator.py
=================================

Description
-----------
Orchestrateur du Data Source Layer.

Ce module fournit un point d'entrée UNIQUE pour charger un
``SourceDocument`` quelle que soit l'origine réelle des données
(fichier local, base de données, API...).

Il ne contient aucune logique de lecture propre à un format ou à un
protocole : cette responsabilité reste dans les loaders spécialisés
(``app.data_sources.file``, ``app.data_sources.database``, ...).
L'orchestrateur se limite à :

    1. déterminer le type de source (``DataSourceKind``) ;
    2. déléguer au point d'entrée public correspondant
       (``load_file``, ``load_database``, ...) ;
    3. retourner un ``SourceDocument`` normalisé, ou lever une
       exception métier claire si la source est inconnue,
       ambiguë ou non supportée.

Architecture
------------

    DataSourceOrchestrator.load(source)
                ↓
        _resolve_kind(source)
                ↓
    ┌───────────┼──────────────┐
    ↓           ↓              ↓
  FILE      DATABASE          API
    ↓           ↓              ↓
 load_file  load_database   (non implémenté)
    ↓           ↓
        SourceDocument

Ce module est le pendant, côté chargement, de

``app.parser.orchestrator.ParserOrchestrator`` côté parsing :

    DataSourceOrchestrator.load()   -> SourceDocument
    ParserOrchestrator.parse()      -> ParsedDocument

État du support par type de source
-----------------------------------
- ``file``     : entièrement supporté (txt, md, html, csv, json,
                 xlsx, docx, pdf).
- ``database`` : entièrement supporté (driver ``mysql``).
- ``api``      : non implémenté. Le sous-package
                 ``app.data_sources.api`` existe mais est vide.
                 Toute tentative de chargement lève explicitement
                 ``UnsupportedSourceError`` plutôt que d'échouer
                 silencieusement ou avec une erreur bas niveau.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from app.data_sources.database import load_database
from app.data_sources.file import load_file
from app.exceptions import UnsupportedSourceError
from app.models.document import SourceDocument

__all__ = [
    "DataSourceKind",
    "DataSourceOrchestrator",
]


# ==========================================================
# Source Kind
# ==========================================================


class DataSourceKind(str, Enum):
    """
    Type de source de données géré par l'orchestrateur.

    Hériter de ``str`` permet de comparer directement une valeur
    brute (``"file"``) à un membre de l'enum, et de l'utiliser
    telle quelle dans les logs, exceptions ou sérialisations JSON.
    """

    FILE = "file"
    DATABASE = "database"
    API = "api"


# Types de sources reconnus mais volontairement non supportés pour
# le moment. Séparés de DataSourceKind pour ne pas laisser croire
# qu'ils font partie de l'API stable de l'enum.
_KNOWN_UNSUPPORTED_KINDS: frozenset[str] = frozenset({"api"})


# ==========================================================
# Orchestrator
# ==========================================================


class DataSourceOrchestrator:
    """
    Point d'entrée unique pour le chargement de données.

    Cette classe ne connaît aucun détail d'implémentation des
    loaders concrets. Elle se contente de résoudre le type de
    source puis de déléguer au point d'entrée public correspondant
    (``load_file``, ``load_database``...).

    Examples
    --------
    Chargement d'un fichier (résolution automatique) :

    >>> orchestrator = DataSourceOrchestrator()
    >>> document = orchestrator.load("reports/maintenance.pdf")

    Chargement d'une base de données (dictionnaire de configuration) :

    >>> document = orchestrator.load({
    ...     "driver": "mysql",
    ...     "host": "localhost",
    ...     "database": "gmao",
    ...     "user": "root",
    ...     "password": "secret",
    ...     "table": "interventions",
    ... })

    Chargement d'une base de données (kind explicite + kwargs) :

    >>> document = orchestrator.load(
    ...     "mysql",
    ...     kind="database",
    ...     host="localhost",
    ...     database="gmao",
    ...     user="root",
    ...     password="secret",
    ...     table="interventions",
    ... )
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    # ======================================================
    # Public API
    # ======================================================

    def load(
        self,
        source: str | Path | Mapping[str, Any],
        *,
        kind: DataSourceKind | str | None = None,
        **kwargs: Any,
    ) -> SourceDocument:
        """
        Charge une source de données et retourne un ``SourceDocument``.

        Parameters
        ----------
        source:
            - Un chemin de fichier (``str`` ou ``Path``) pour une
              source de type fichier.
            - Un dictionnaire de configuration (doit contenir la
              clé ``"driver"``) pour une source de type base de
              données.
            - Un nom de driver (``str``, ex: ``"mysql"``) si
              ``kind="database"`` est fourni explicitement, auquel
              cas les paramètres de connexion sont passés via
              ``**kwargs``.

        kind:
            Force le type de source plutôt que de le déduire de
            ``source``. Utile pour lever toute ambiguïté (ex: un
            nom de driver seul, sans dictionnaire).

        **kwargs:
            Paramètres supplémentaires transmis au loader résolu.
            Pour une source ``database``, ce sont les paramètres de
            connexion attendus par ``load_database`` (``host``,
            ``database``, ``user``, ``password``, ``table``,
            ``query``, ...).

        Returns
        -------
        SourceDocument
            Document standardisé, indépendant de son origine.

        Raises
        ------
        UnsupportedSourceError
            Si le type de source ne peut pas être déterminé, ou
            s'il est reconnu mais non supporté (ex: ``"api"``).

        GMAOError
            Toute erreur métier levée par le loader délégué
            (ex: ``MissingFileError``, ``DatabaseConnectionError``).
        """

        resolved_kind = self._resolve_kind(source, kind)

        self._logger.debug(
            "Resolved source kind '%s' for %r.",
            resolved_kind.value,
            source,
        )

        if resolved_kind is DataSourceKind.FILE:
            return self._load_file(source)

        if resolved_kind is DataSourceKind.DATABASE:
            return self._load_database(source, kwargs)

        raise self._unsupported_kind_error(resolved_kind.value)

    def supports(self, kind: DataSourceKind | str) -> bool:
        """
        Indique si un type de source est actuellement supporté.

        Returns
        -------
        bool
        """
        normalized = self._normalize_kind(kind)
        return normalized in (DataSourceKind.FILE, DataSourceKind.DATABASE)

    # ======================================================
    # Kind Resolution
    # ======================================================

    def _resolve_kind(
        self,
        source: str | Path | Mapping[str, Any],
        kind: DataSourceKind | str | None,
    ) -> DataSourceKind:
        """
        Détermine le ``DataSourceKind`` de la source fournie.

        L'ordre de résolution est :

        1. ``kind`` explicite, si fourni (aucune ambiguïté possible).
        2. ``source`` est un ``Mapping`` contenant ``"driver"``
           -> ``DATABASE``.
        3. ``source`` est un ``str`` ou un ``Path``
           -> ``FILE``.

        Raises
        ------
        UnsupportedSourceError
            Si aucune règle ne permet de résoudre le type de source.
        """

        if kind is not None:
            return self._normalize_kind(kind)

        if isinstance(source, Mapping):
            if "driver" in source:
                return DataSourceKind.DATABASE

            raise UnsupportedSourceError(
                message=(
                    "Cannot resolve source kind: a mapping was "
                    "provided without a 'driver' key."
                ),
                details={"provided_keys": sorted(source.keys())},
            )

        if isinstance(source, (str, Path)):
            return DataSourceKind.FILE

        raise UnsupportedSourceError(
            message=(
                "Cannot resolve source kind for value of type "
                f"'{type(source).__name__}'. Expected str, Path, "
                "or Mapping, or an explicit 'kind' argument."
            ),
            details={"source_type": type(source).__name__},
        )

    def _normalize_kind(
        self,
        kind: DataSourceKind | str,
    ) -> DataSourceKind:
        """
        Normalise un ``kind`` fourni par l'appelant (``str`` ou enum).

        Raises
        ------
        UnsupportedSourceError
            Si la valeur ne correspond à aucun ``DataSourceKind``
            connu (supporté ou non).
        """

        if isinstance(kind, DataSourceKind):
            return kind

        normalized = str(kind).strip().lower()

        try:
            return DataSourceKind(normalized)
        except ValueError:
            raise UnsupportedSourceError(
                message=f"Unknown source kind '{kind}'.",
                details={
                    "supported": [member.value for member in DataSourceKind],
                },
            ) from None

    def _unsupported_kind_error(self, kind: str) -> UnsupportedSourceError:
        """
        Construit l'erreur retournée pour un type de source connu
        mais non encore implémenté (ex: ``"api"``).
        """

        if kind in _KNOWN_UNSUPPORTED_KINDS:
            return UnsupportedSourceError(
                message=(
                    f"Source kind '{kind}' is recognized but not yet "
                    "implemented. app.data_sources.api currently "
                    "exposes no loader."
                ),
                details={"kind": kind, "status": "not_implemented"},
            )

        return UnsupportedSourceError(
            message=f"Source kind '{kind}' is not supported.",
            details={"kind": kind},
        )

    # ======================================================
    # Delegation
    # ======================================================

    def _load_file(self, source: str | Path | Mapping[str, Any]) -> SourceDocument:
        """
        Délègue le chargement à ``app.data_sources.file.load_file``.
        """

        if isinstance(source, Mapping):
            # Ne devrait pas arriver : un Mapping est toujours résolu
            # en DATABASE. Garde-fou en cas d'extension future.
            raise UnsupportedSourceError(
                message="A file source cannot be provided as a mapping.",
                details={"provided_keys": sorted(source.keys())},
            )

        return load_file(source)

    def _load_database(
        self,
        source: str | Path | Mapping[str, Any],
        kwargs: dict[str, Any],
    ) -> SourceDocument:
        """
        Délègue le chargement à
        ``app.data_sources.database.load_database``.

        ``source`` peut être :

        - un ``Mapping`` complet de configuration
          (``{"driver": "mysql", "host": ..., ...}``) ;
        - un simple nom de driver (``str``), auquel cas les
          paramètres de connexion doivent être fournis via
          ``**kwargs`` de ``load()``.
        """

        if isinstance(source, Mapping):
            config: dict[str, Any] = dict(source)
            config.update(kwargs)
        else:
            config = {"driver": source, **kwargs}

        if "driver" not in config:
            raise UnsupportedSourceError(
                message="Database source is missing the 'driver' key.",
                details={"provided_keys": sorted(config.keys())},
            )

        return load_database(**config)
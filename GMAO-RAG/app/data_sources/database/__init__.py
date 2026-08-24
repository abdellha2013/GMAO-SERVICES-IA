"""
app/data_sources/database/__init__.py
=====================================

Point d'entrée du sous-package database.

Le package expose actuellement MySQL comme seule source
de données relationnelle implémentée.

Architecture
------------

    application
         ↓
    load_database()
         ↓
    get_loader_class()
         ↓
    MySQLLoader
         ↓
    MySQLSource
         ↓
    SourceDocument

Les imports des loaders sont différés afin de ne pas charger
SQLAlchemy / PyMySQL lorsque le sous-package database est
simplement importé.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.document import SourceDocument


__all__ = [
    "DRIVER_LOADER_MAP",
    "get_loader_class",
    "load_database",
    "MySQLLoader",
    "MySQLSource",
]


# ==========================================================
# Registry
# ==========================================================

DRIVER_LOADER_MAP: dict[str, tuple[str, str]] = {
    "mysql": (
        "mysql_loader",
        "MySQLLoader",
    ),
}


# ==========================================================
# Loader Resolution
# ==========================================================

def get_loader_class(
    driver: str,
) -> type:
    """
    Résout la classe de loader correspondant à un driver.

    Parameters
    ----------
    driver:
        Nom du moteur de base de données.

    Returns
    -------
    type
        Classe du loader.

    Raises
    ------
    UnsupportedSourceError
        Driver inconnu ou loader indisponible.
    """

    from app.exceptions import UnsupportedSourceError

    if not isinstance(driver, str):
        raise UnsupportedSourceError(
            message=(
                "Database driver must be a string."
            ),
            details={
                "driver_type": type(driver).__name__,
            },
        )

    normalized = driver.strip().lower()

    if not normalized:
        raise UnsupportedSourceError(
            message=(
                "Database driver cannot be empty."
            )
        )

    entry = DRIVER_LOADER_MAP.get(
        normalized,
    )

    if entry is None:
        raise UnsupportedSourceError(
            message=(
                f"No database loader is registered "
                f"for driver '{normalized}'."
            ),
            details={
                "driver": normalized,
                "supported": sorted(
                    DRIVER_LOADER_MAP,
                ),
            },
        )

    module_name, class_name = entry

    try:
        module = __import__(
            f"{__name__}.{module_name}",
            fromlist=[class_name],
        )

        loader_class = getattr(
            module,
            class_name,
        )

        return loader_class

    except (
        ImportError,
        AttributeError,
    ) as exc:
        raise UnsupportedSourceError(
            message=(
                f"Database loader for driver "
                f"'{normalized}' is registered but "
                f"cannot be loaded "
                f"('{module_name}.{class_name}')."
            ),
            details={
                "driver": normalized,
                "module": module_name,
                "class": class_name,
            },
            original=exc,
        ) from exc


# ==========================================================
# Public Loader API
# ==========================================================

def load_database(
    driver: str,
    *,
    host: str,
    database: str,
    user: str,
    password: str = "",
    table: str | None = None,
    query: str | None = None,
    params: dict[str, Any] | None = None,
    **kwargs: Any,
) -> "SourceDocument":
    """
    Charge des données depuis une base de données.

    Parameters
    ----------
    driver:
        Moteur de base de données.
        Exemple : "mysql".

    host:
        Hôte du serveur.

    database:
        Nom de la base.

    user:
        Utilisateur.

    password:
        Mot de passe.

    table:
        Table à charger.

    query:
        Requête SELECT personnalisée.

    params:
        Paramètres liés à la requête.

    **kwargs:
        Options spécifiques au loader.

    Returns
    -------
    SourceDocument
        Document standardisé.

    Raises
    ------
    UnsupportedSourceError
        Driver non supporté.

    GMAOError
        Toute erreur métier levée par le loader.
    """

    loader_class = get_loader_class(
        driver,
    )

    loader = loader_class(
        host=host,
        database=database,
        user=user,
        password=password,
        table=table,
        query=query,
        params=params,
        **kwargs,
    )

    return loader.read()


# ==========================================================
# Lazy Public Exports
# ==========================================================

def __getattr__(
    name: str,
) -> Any:
    """
    Expose MySQLLoader et MySQLSource avec import paresseux.
    """

    if name == "MySQLLoader":
        from app.data_sources.database.mysql_loader import (
            MySQLLoader,
        )

        return MySQLLoader

    if name == "MySQLSource":
        from app.data_sources.database.mysql_source import (
            MySQLSource,
        )

        return MySQLSource

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


def __dir__() -> list[str]:
    """
    Retourne les symboles publics et disponibles.
    """

    return sorted(
        set(
            list(globals().keys())
            + __all__
        )
    )
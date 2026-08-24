"""
app/exceptions/data_source.py
=============================

Description
-----------
Définition des exceptions du Data Source Layer.

Toutes les erreurs liées au chargement de données (fichiers,
bases de données, APIs, services cloud, etc.) doivent hériter
de DataSourceError.

Cette hiérarchie permet :

- une gestion centralisée des erreurs ;
- un traitement uniforme dans les services ;
- une meilleure lisibilité du code ;
- une intégration simple avec les APIs.

Hiérarchie
----------
Exception
    └── GMAOError
            └── DataSourceError
                    ├── ValidationError
                    ├── ConfigurationError
                    ├── DataConnectionError
                    ├── AuthenticationError
                    ├── PermissionDeniedError
                    ├── LoadingError
                    ├── CloseError
                    └── UnsupportedSourceError

Note
----
``DataConnectionError`` (et non ``ConnectionError``) : le nom natif
Python ``ConnectionError`` est une exception builtin utilisée par la
stack réseau/OS (``socket``, ``requests``, ``asyncpg``, etc.). La
définir ici sous le même nom masquerait le builtin dans tout module qui
ferait ``from app.exceptions import ConnectionError`` : un
``except ConnectionError`` n'attraperait plus les vraies erreurs
réseau, seulement celle du projet. D'où le renommage.
"""

from __future__ import annotations

from .base_exception import GMAOError

__all__ = [
    "DataSourceError",
    "ValidationError",
    "ConfigurationError",
    "DataConnectionError",
    "AuthenticationError",
    "PermissionDeniedError",
    "LoadingError",
    "CloseError",
    "UnsupportedSourceError",
]


class DataSourceError(GMAOError):
    """
    Exception de base du Data Source Layer.

    Toutes les exceptions liées aux sources de données
    doivent hériter de cette classe.
    """

    DEFAULT_MESSAGE = "An unexpected data source error occurred."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_ERROR"
    DEFAULT_HTTP_STATUS = 500
    DEFAULT_RETRYABLE = False

    def __init__(
        self,
        message: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop(
                "error_code",
                self.DEFAULT_ERROR_CODE,
            ),
            http_status=kwargs.pop(
                "http_status",
                self.DEFAULT_HTTP_STATUS,
            ),
            **kwargs,
        )


class ValidationError(DataSourceError):
    """
    La source de données est invalide.
    """

    DEFAULT_MESSAGE = "The data source validation failed."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class ConfigurationError(DataSourceError):
    """
    Configuration invalide de la source.
    """

    DEFAULT_MESSAGE = "The data source configuration is invalid."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_CONFIGURATION_ERROR"
    DEFAULT_HTTP_STATUS = 500


class DataConnectionError(DataSourceError):
    """
    Impossible d'établir une connexion avec la source.
    """

    DEFAULT_MESSAGE = "Unable to connect to the data source."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_CONNECTION_ERROR"
    DEFAULT_HTTP_STATUS = 503


class AuthenticationError(DataConnectionError):
    """
    Échec de l'authentification.
    """

    DEFAULT_MESSAGE = "Authentication failed."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_AUTHENTICATION_ERROR"
    DEFAULT_HTTP_STATUS = 401


class PermissionDeniedError(DataConnectionError):
    """
    Permissions insuffisantes.
    """

    DEFAULT_MESSAGE = "Permission denied."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_PERMISSION_DENIED"
    DEFAULT_HTTP_STATUS = 403


class LoadingError(DataSourceError):
    """
    Erreur lors du chargement des données.
    """

    DEFAULT_MESSAGE = "Unable to load data from the source."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_LOADING_ERROR"
    DEFAULT_HTTP_STATUS = 500


class CloseError(DataSourceError):
    """
    Erreur lors de la fermeture de la source.
    """

    DEFAULT_MESSAGE = "Unable to close the data source."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_CLOSE_ERROR"
    DEFAULT_HTTP_STATUS = 500


class UnsupportedSourceError(DataSourceError):
    """
    Type de source non pris en charge.
    """

    DEFAULT_MESSAGE = "The data source is not supported."
    DEFAULT_ERROR_CODE = "DATA_SOURCE_UNSUPPORTED"
    DEFAULT_HTTP_STATUS = 400

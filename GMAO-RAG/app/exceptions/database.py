"""
app/exceptions/database.py
==========================

Description
-----------
Définition des exceptions spécifiques aux bases de données.

Toutes les erreurs liées aux bases de données doivent hériter
de DatabaseError.

Cette hiérarchie couvre :

- MySQL
- PostgreSQL
- SQL Server
- Oracle
- SQLite
- Futures bases de données

Hiérarchie
----------
Exception
    │
    ▼
GMAOError
    │
    ▼
DataSourceError
    │
    ├── ValidationError
    ├── ConfigurationError
    ├── DataConnectionError
    ├── LoadingError
    ├── CloseError
    ├── UnsupportedSourceError
    │
    └── DatabaseError
            ├── DatabaseValidationError
            ├── DatabaseConnectionError
            ├── DatabaseLoadingError
            ├── TransactionError
            ├── DuplicateKeyError
            └── ForeignKeyError
"""

from __future__ import annotations

from .data_source import (
    DataConnectionError,
    DataSourceError,
    LoadingError,
)

__all__ = [
    "DatabaseError",
    "DuplicateKeyError",
    "ForeignKeyError",
    "DatabaseValidationError",
    "DatabaseConnectionError",
    "DatabaseLoadingError",
    "DatabaseAuthenticationError",
    "DatabasePermissionError",
    "DatabaseTimeoutError",
    "DatabaseNotFoundError",
    "TableNotFoundError",
    "QueryExecutionError",
    "EmptyResultError",
    "TransactionError",
]


class DatabaseError(DataSourceError):
    """
    Exception de base pour toutes les erreurs liées
    aux bases de données.
    """

    DEFAULT_MESSAGE = "A database error has occurred."
    DEFAULT_ERROR_CODE = "DATABASE_ERROR"
    DEFAULT_HTTP_STATUS = 500
    DEFAULT_RETRYABLE = False


class DatabaseValidationError(DatabaseError):
    """
    Configuration ou paramètres invalides.
    """

    DEFAULT_MESSAGE = "The database configuration is invalid."
    DEFAULT_ERROR_CODE = "DATABASE_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class DatabaseConnectionError(DataConnectionError):
    """
    Impossible d'établir une connexion.
    """

    DEFAULT_MESSAGE = "Unable to connect to the database."
    DEFAULT_ERROR_CODE = "DATABASE_CONNECTION_ERROR"
    DEFAULT_HTTP_STATUS = 503
    DEFAULT_RETRYABLE = True


class DatabaseAuthenticationError(DatabaseConnectionError):
    """
    Authentification refusée.
    """

    DEFAULT_MESSAGE = "Database authentication failed."
    DEFAULT_ERROR_CODE = "DATABASE_AUTHENTICATION_ERROR"
    DEFAULT_HTTP_STATUS = 401
    DEFAULT_RETRYABLE = False


class DatabasePermissionError(DatabaseConnectionError):
    """
    Permissions insuffisantes.
    """

    DEFAULT_MESSAGE = "Database permission denied."
    DEFAULT_ERROR_CODE = "DATABASE_PERMISSION_DENIED"
    DEFAULT_HTTP_STATUS = 403
    DEFAULT_RETRYABLE = False


class DatabaseTimeoutError(DatabaseConnectionError):
    """
    Délai de connexion dépassé.
    """

    DEFAULT_MESSAGE = "Database connection timeout."
    DEFAULT_ERROR_CODE = "DATABASE_TIMEOUT"
    DEFAULT_HTTP_STATUS = 504
    DEFAULT_RETRYABLE = True


class DatabaseLoadingError(LoadingError):
    """
    Impossible de récupérer les données.
    """

    DEFAULT_MESSAGE = "Unable to load data from the database."
    DEFAULT_ERROR_CODE = "DATABASE_LOADING_ERROR"
    DEFAULT_HTTP_STATUS = 500
    DEFAULT_RETRYABLE = True


class QueryExecutionError(DatabaseLoadingError):
    """
    Erreur pendant l'exécution d'une requête SQL.
    """

    DEFAULT_MESSAGE = "SQL query execution failed."
    DEFAULT_ERROR_CODE = "DATABASE_QUERY_ERROR"
    DEFAULT_HTTP_STATUS = 500
    DEFAULT_RETRYABLE = False


class TableNotFoundError(DatabaseLoadingError):
    """
    La table demandée n'existe pas.
    """

    DEFAULT_MESSAGE = "The requested table was not found."
    DEFAULT_ERROR_CODE = "DATABASE_TABLE_NOT_FOUND"
    DEFAULT_HTTP_STATUS = 404
    DEFAULT_RETRYABLE = False


class DatabaseNotFoundError(DatabaseConnectionError):
    """
    La base de données demandée n'existe pas.
    """

    DEFAULT_MESSAGE = "The requested database was not found."
    DEFAULT_ERROR_CODE = "DATABASE_NOT_FOUND"
    DEFAULT_HTTP_STATUS = 404
    DEFAULT_RETRYABLE = False


class EmptyResultError(DatabaseLoadingError):
    """
    La requête ne retourne aucun résultat.
    """

    DEFAULT_MESSAGE = "The query returned no results."
    DEFAULT_ERROR_CODE = "DATABASE_EMPTY_RESULT"
    DEFAULT_HTTP_STATUS = 404
    DEFAULT_RETRYABLE = False


class TransactionError(DatabaseError):
    """
    Erreur pendant une transaction.
    """

    DEFAULT_MESSAGE = "The database transaction failed."
    DEFAULT_ERROR_CODE = "DATABASE_TRANSACTION_ERROR"
    DEFAULT_HTTP_STATUS = 500
    DEFAULT_RETRYABLE = True


class DuplicateKeyError(DatabaseLoadingError):
    """
    Exception levée lorsqu'une opération viole une contrainte
    PRIMARY KEY ou UNIQUE.

    Exemple
    --------
    - Insertion d'un document avec un identifiant déjà existant.
    - Violation d'une contrainte UNIQUE.
    """

    DEFAULT_MESSAGE = "A duplicate key constraint has been violated."
    DEFAULT_ERROR_CODE = "DATABASE_DUPLICATE_KEY"
    DEFAULT_HTTP_STATUS = 409
    DEFAULT_RETRYABLE = False


class ForeignKeyError(DatabaseLoadingError):
    """
    Exception levée lorsqu'une contrainte de clé étrangère
    est violée.

    Exemple
    --------
    - document_id inexistant
    - suppression d'un enregistrement encore référencé
    """

    DEFAULT_MESSAGE = "A foreign key constraint has been violated."
    DEFAULT_ERROR_CODE = "DATABASE_FOREIGN_KEY"
    DEFAULT_HTTP_STATUS = 409
    DEFAULT_RETRYABLE = False

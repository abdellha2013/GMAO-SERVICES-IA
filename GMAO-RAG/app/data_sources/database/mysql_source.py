"""
app/data_sources/database/mysql_source.py
=========================================

Description
-----------
Source de données MySQL responsable de la connexion et de
l'exécution des requêtes SQL.

Cette classe fournit les fonctionnalités communes nécessaires
à toutes les opérations MySQL :

- validation de la configuration ;
- validation des identifiants SQL ;
- ouverture de connexion ;
- fermeture de connexion ;
- gestion du cycle de vie SQLAlchemy ;
- exécution de requêtes paramétrées ;
- vérification de l'existence d'une table ;
- traduction des erreurs SQLAlchemy / PyMySQL en exceptions
  métier du projet.

Cette classe ne construit pas de SourceDocument.

La transformation des résultats SQL en SourceDocument est
la responsabilité de MySQLLoader.

Architecture
------------

    MySQL
      ↓
    MySQLSource
      ↓
    connexion / SQL / erreurs
      ↓
    MySQLLoader
      ↓
    SourceDocument
      ↓
    Parser
      ↓
    Chunker
      ↓
    Embedding

Dépendances
-----------
SQLAlchemy + PyMySQL.

Installation :

    uv add sqlalchemy pymysql
"""

from __future__ import annotations

import re
from logging import getLogger
from typing import TYPE_CHECKING, Any, Final

from app.data_sources.interfaces.base_source import BaseSource
from app.exceptions import DatabaseValidationError

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine


logger = getLogger(__name__)

__all__ = ["MySQLSource"]


# ==========================================================
# Configuration
# ==========================================================

_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]{0,63}$"
)


# MySQL error codes commonly encountered during connection
# and read-only query operations.

_ERRNO_ACCESS_DENIED: Final[tuple[int, ...]] = (
    1044,
    1045,
    1142,
)

_ERRNO_UNKNOWN_DATABASE: Final[tuple[int, ...]] = (
    1049,
)

_ERRNO_CANNOT_CONNECT: Final[tuple[int, ...]] = (
    2002,
    2003,
    2005,
)

_ERRNO_TABLE_NOT_FOUND: Final[tuple[int, ...]] = (
    1146,
)

_ERRNO_DUPLICATE_KEY: Final[tuple[int, ...]] = (
    1062,
)

_ERRNO_FOREIGN_KEY: Final[tuple[int, ...]] = (
    1216,
    1217,
    1451,
    1452,
)


class MySQLSource(BaseSource[str]):
    """
    Source de données représentant une connexion MySQL.

    La classe est volontairement indépendante de la logique
    de transformation en SourceDocument.

    Parameters
    ----------
    host:
        Adresse du serveur MySQL.

    database:
        Nom de la base de données.

    user:
        Utilisateur MySQL.

    password:
        Mot de passe MySQL.

    port:
        Port du serveur MySQL.

    charset:
        Jeu de caractères utilisé par la connexion.

    connect_timeout:
        Délai maximal d'établissement de connexion,
        en secondes.
    """

    DEFAULT_PORT: Final[int] = 3306
    DEFAULT_CHARSET: Final[str] = "utf8mb4"
    DEFAULT_CONNECT_TIMEOUT: Final[int] = 10

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(
        self,
        host: str,
        database: str,
        user: str,
        password: str = "",
        *,
        port: int = DEFAULT_PORT,
        charset: str = DEFAULT_CHARSET,
        connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        """
        Initialise une source MySQL.

        La connexion n'est pas ouverte pendant l'initialisation.

        Elle est établie uniquement lorsqu'une opération nécessitant
        une connexion est exécutée.
        """

        target = (
            f"{user}@{host}:{port}/{database}"
        )

        super().__init__(target)

        self._host = host
        self._database = database
        self._user = user
        self._password = password
        self._port = port
        self._charset = charset
        self._connect_timeout = connect_timeout

        self._engine: "Engine | None" = None
        self._connection: "Connection | None" = None

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def host(self) -> str:
        """Retourne l'hôte MySQL."""
        return self._host

    @property
    def database(self) -> str:
        """Retourne le nom de la base MySQL."""
        return self._database

    @property
    def user(self) -> str:
        """Retourne l'utilisateur MySQL."""
        return self._user

    @property
    def port(self) -> int:
        """Retourne le port MySQL."""
        return self._port

    @property
    def charset(self) -> str:
        """Retourne le charset de connexion."""
        return self._charset

    @property
    def connect_timeout(self) -> int:
        """Retourne le délai de connexion."""
        return self._connect_timeout

    @property
    def source_path(self) -> None:
        """Retourne ``None`` : une source MySQL n'a pas de chemin de fichier."""
        return None

    @property
    def source_name(self) -> str:
        """
        Nom lisible de la source.

        Le mot de passe n'est jamais exposé.
        """

        return (
            f"mysql://"
            f"{self._user}@"
            f"{self._host}:"
            f"{self._port}/"
            f"{self._database}"
        )

    
        
    # ==========================================================
    # Validation
    # ==========================================================

    def validate(self) -> None:
        """
        Valide la configuration de connexion.

        Cette méthode ne tente pas de se connecter au serveur.

        Raises
        ------
        DatabaseValidationError
            Si la configuration est invalide.
        """

        self.logger.debug(
            "Validating MySQL configuration for '%s'.",
            self.source_name,
        )

        missing: list[str] = []

        for name, value in (
            ("host", self._host),
            ("database", self._database),
            ("user", self._user),
        ):
            if not isinstance(value, str) or not value.strip():
                missing.append(name)

        if missing:
            raise DatabaseValidationError(
                message=(
                    "Missing required MySQL parameter(s): "
                    f"{', '.join(missing)}."
                ),
                details={
                    "missing": missing,
                },
            )

        if not isinstance(self._port, int):
            raise DatabaseValidationError(
                message="MySQL port must be an integer.",
                details={
                    "port": self._port,
                },
            )

        if not 1 <= self._port <= 65535:
            raise DatabaseValidationError(
                message=(
                    f"Invalid MySQL port: {self._port}."
                ),
                details={
                    "port": self._port,
                },
            )

        if not isinstance(self._connect_timeout, int):
            raise DatabaseValidationError(
                message=(
                    "MySQL connect_timeout must be an integer."
                ),
                details={
                    "connect_timeout": self._connect_timeout,
                },
            )

        if self._connect_timeout <= 0:
            raise DatabaseValidationError(
                message=(
                    "MySQL connect_timeout must be greater "
                    "than zero."
                ),
                details={
                    "connect_timeout": self._connect_timeout,
                },
            )

        if not isinstance(self._charset, str):
            raise DatabaseValidationError(
                message="MySQL charset must be a string.",
                details={
                    "charset": self._charset,
                },
            )

        if not self._charset.strip():
            raise DatabaseValidationError(
                message="MySQL charset cannot be empty.",
                details={
                    "charset": self._charset,
                },
            )

        if not self._password:
            self.logger.warning(
                "MySQL source '%s' is configured without a password.",
                self.source_name,
            )

    # ==========================================================
    # SQL Identifier Validation
    # ==========================================================

    @staticmethod
    def validate_identifier(
        name: str,
    ) -> str:
        """
        Valide un identifiant SQL MySQL.

        Les identifiants SQL ne peuvent pas être transmis comme
        paramètres liés. Ils doivent donc être validés avant
        interpolation dans une requête.

        Parameters
        ----------
        name:
            Nom de table ou autre identifiant SQL.

        Returns
        -------
        str
            Identifiant validé.

        Raises
        ------
        DatabaseValidationError
            Si l'identifiant est invalide.
        """

        if not isinstance(name, str):
            raise DatabaseValidationError(
                message="SQL identifier must be a string.",
                details={
                    "identifier": repr(name),
                },
            )

        if not _IDENTIFIER_PATTERN.fullmatch(name):
            raise DatabaseValidationError(
                message=(
                    f"Invalid SQL identifier: '{name}'."
                ),
                details={
                    "identifier": name,
                    "rule": (
                        "letters, digits and underscore; "
                        "must not start with a digit; "
                        "maximum length is 64 characters"
                    ),
                },
            )

        return name

    # ==========================================================
    # Connection Lifecycle
    # ==========================================================

    def _connect(self) -> None:
        """
        Établit une connexion MySQL.

        Raises
        ------
        DatabaseConnectionError
            Driver absent ou erreur générale de connexion.

        DatabaseAuthenticationError
            Identifiants refusés.

        DatabaseNotFoundError
            Base inexistante.

        DatabaseTimeoutError
            Connexion expirée.
        """

        from app.exceptions import (
            DatabaseAuthenticationError,
            DatabaseConnectionError,
            DatabaseNotFoundError,
            DatabaseTimeoutError,
        )

        self.validate()

        try:
            import sqlalchemy  # noqa: F401
            import pymysql  # noqa: F401
        except ImportError as exc:
            raise DatabaseConnectionError(
                message=(
                    "MySQL driver dependencies are missing. "
                    "SQLAlchemy and PyMySQL are required."
                ),
                details={
                    "driver": "pymysql",
                    "module": "pymysql",
                },
                original=exc,
            ) from exc

        self.logger.info(
            "Connecting to MySQL source '%s'.",
            self.source_name,
        )

        try:
            from sqlalchemy import create_engine
            from sqlalchemy.exc import OperationalError

        except ImportError as exc:
            raise DatabaseConnectionError(
                message=(
                    "MySQL driver dependencies are missing. "
                    "SQLAlchemy and PyMySQL are required."
                ),
                details={
                    "driver": "pymysql",
                    "module": "pymysql",
                },
                original=exc,
            ) from exc

        url = (
            f"mysql+pymysql://"
            f"{self._user}:{self._password}"
            f"@{self._host}:{self._port}"
            f"/{self._database}"
            f"?charset={self._charset}"
        )

        try:
            self._engine = create_engine(
                url,
                pool_pre_ping=True,
                connect_args={
                    "connect_timeout": self._connect_timeout,
                },
            )

            self._connection = self._engine.connect()

        except OperationalError as exc:
            errno = self._extract_errno(exc)
            message = str(exc).lower()

            if errno in _ERRNO_ACCESS_DENIED:
                raise DatabaseAuthenticationError(
                    message=(
                        f"MySQL authentication failed "
                        f"for '{self.source_name}'."
                    ),
                    original=exc,
                ) from exc

            if errno in _ERRNO_UNKNOWN_DATABASE:
                raise DatabaseNotFoundError(
                    message=(
                        f"MySQL database "
                        f"'{self._database}' does not exist."
                    ),
                    original=exc,
                ) from exc

            if (
                errno in _ERRNO_CANNOT_CONNECT
                or "timed out" in message
                or "timeout" in message
            ):
                if (
                    "timed out" in message
                    or "timeout" in message
                ):
                    from app.exceptions import (
                        DatabaseTimeoutError,
                    )

                    raise DatabaseTimeoutError(
                        message=(
                            f"Connection to MySQL source "
                            f"'{self.source_name}' timed out."
                        ),
                        original=exc,
                    ) from exc

                raise DatabaseConnectionError(
                    message=(
                        f"Unable to reach MySQL server "
                        f"for '{self.source_name}'."
                    ),
                    original=exc,
                ) from exc

            raise DatabaseConnectionError(
                message=(
                    f"Unable to connect to MySQL source "
                    f"'{self.source_name}'."
                ),
                original=exc,
            ) from exc

        except Exception as exc:
            self._dispose_resources()

            raise DatabaseConnectionError(
                message=(
                    f"Unexpected error while connecting "
                    f"to MySQL source '{self.source_name}'."
                ),
                original=exc,
            ) from exc

    def _close(self) -> None:
        """
        Ferme proprement la connexion et le moteur SQLAlchemy.

        Cette opération est idempotente.
        """

        self.logger.debug(
            "Closing MySQL source '%s'.",
            self.source_name,
        )

        self._dispose_resources()

    # ==========================================================
    # Query Execution
    # ==========================================================

    def execute_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Exécute une requête SQL paramétrée.

        Parameters
        ----------
        sql:
            Requête SQL utilisant des paramètres liés.

        params:
            Paramètres associés à la requête.

        Returns
        -------
        list[dict[str, Any]]
            Résultats sous forme de dictionnaires.

        Raises
        ------
        QueryExecutionError
            Erreur d'exécution SQL.

        TableNotFoundError
            Table inexistante.
        """

        from app.exceptions import (
            QueryExecutionError,
            TableNotFoundError,
        )

        if not isinstance(sql, str) or not sql.strip():
            raise DatabaseValidationError(
                message="SQL query cannot be empty.",
                details={
                    "sql": sql,
                },
            )

        if params is not None and not isinstance(params, dict):
            raise DatabaseValidationError(
                message="SQL query parameters must be a dictionary.",
                details={
                    "params_type": type(params).__name__,
                },
            )

        self.ensure_connected()

        self.logger.debug(
            "Executing SQL query against '%s'.",
            self.source_name,
        )

        try:
            from sqlalchemy import text
            from sqlalchemy.exc import (
                IntegrityError,
                ProgrammingError,
                SQLAlchemyError,
            )

            result = self._connection.execute(
                text(sql),
                params or {},
            )

            columns = list(result.keys())

            rows = [
                dict(zip(columns, row))
                for row in result.fetchall()
            ]

            self.logger.debug(
                "SQL query returned %d row(s).",
                len(rows),
            )

            return rows

        except IntegrityError as exc:
            errno = self._extract_errno(exc)

            if errno in _ERRNO_DUPLICATE_KEY:
                from app.exceptions import DuplicateKeyError

                raise DuplicateKeyError(
                    original=exc,
                ) from exc

            if errno in _ERRNO_FOREIGN_KEY:
                from app.exceptions import ForeignKeyError

                raise ForeignKeyError(
                    original=exc,
                ) from exc

            raise QueryExecutionError(
                message=(
                    "Integrity constraint violation "
                    "during SQL execution."
                ),
                original=exc,
            ) from exc

        except ProgrammingError as exc:
            errno = self._extract_errno(exc)

            if errno in _ERRNO_TABLE_NOT_FOUND:
                raise TableNotFoundError(
                    original=exc,
                ) from exc

            raise QueryExecutionError(
                message="The SQL query is invalid.",
                details={
                    "sql": sql,
                },
                original=exc,
            ) from exc

        except SQLAlchemyError as exc:
            raise QueryExecutionError(
                message=(
                    f"Query execution failed against "
                    f"'{self.source_name}'."
                ),
                details={
                    "sql": sql,
                },
                original=exc,
            ) from exc

        except Exception as exc:
            raise QueryExecutionError(
                message=(
                    f"Unexpected error while executing "
                    f"query against '{self.source_name}'."
                ),
                details={
                    "sql": sql,
                },
                original=exc,
            ) from exc

    # ==========================================================
    # Table Helpers
    # ==========================================================

    def table_exists(
        self,
        table_name: str,
    ) -> bool:
        """
        Vérifie l'existence d'une table MySQL.

        Le nom de table est transmis comme paramètre lié
        à information_schema.

        Parameters
        ----------
        table_name:
            Nom de la table.

        Returns
        -------
        bool
            True si la table existe.
        """

        table_name = self.validate_identifier(
            table_name,
        )

        rows = self.execute_query(
            (
                "SELECT COUNT(*) AS table_count "
                "FROM information_schema.tables "
                "WHERE table_schema = :database "
                "AND table_name = :table_name"
            ),
            {
                "database": self._database,
                "table_name": table_name,
            },
        )

        return bool(
            rows
            and rows[0].get("table_count", 0)
        )

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    @staticmethod
    def _extract_errno(
        exc: Exception,
    ) -> int | None:
        """
        Extrait le code errno MySQL depuis une exception SQLAlchemy.
        """

        current: Any = exc

        for _ in range(3):
            origin = getattr(
                current,
                "orig",
                None,
            )

            if origin is None:
                break

            current = origin

        args = getattr(
            current,
            "args",
            None,
        )

        if args and isinstance(args[0], int):
            return args[0]

        return None

    def _dispose_resources(self) -> None:
        """
        Libère les ressources SQLAlchemy.

        Les erreurs de fermeture sont journalisées mais ne sont
        pas propagées afin de ne pas masquer une erreur précédente.
        """

        if self._connection is not None:
            try:
                self._connection.close()

            except Exception:
                self.logger.debug(
                    "Error while closing MySQL connection.",
                    exc_info=True,
                )

            finally:
                self._connection = None

        if self._engine is not None:
            try:
                self._engine.dispose()

            except Exception:
                self.logger.debug(
                    "Error while disposing MySQL engine.",
                    exc_info=True,
                )

            finally:
                self._engine = None

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        """
        Représentation de debug sans exposer le mot de passe.
        """

        return (
            f"{self.__class__.__name__}("
            f"source={self.source_name!r}, "
            f"state={self.state.value!r})"
        )

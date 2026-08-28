"""
app/data_sources/database/mysql_loader.py
=========================================

Description
-----------
Loader MySQL responsable de la conversion des résultats SQL en
``SourceDocument``.

Cette classe hérite de :class:`MySQLSource` (connexion, exécution de
requêtes, gestion des erreurs) et ajoute la logique propre au
pipeline RAG :

- sélection entre chargement d'une table complète (``table``) ou
  d'une requête personnalisée (``query``) ;
- validation du mode de chargement (les deux paramètres sont
  mutuellement exclusifs, l'un des deux est obligatoire) ;
- construction de la requête SQL (avec ``LIMIT`` pour le mode
  ``table``) ;
- limitation du nombre de lignes chargées (``max_rows``) ;
- transformation des résultats SQL en texte exploitable par le
  pipeline RAG ;
- génération des métadonnées ;
- retour d'un ``SourceDocument`` standardisé.

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
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Final

from app.data_sources.database.mysql_source import MySQLSource
from app.models.document import SourceDocument

UTC = timezone.utc


class MySQLLoader(MySQLSource):
    """
    Loader MySQL transformant le résultat d'une requête SQL en
    ``SourceDocument``.

    Parameters
    ----------
    host, database, user, password, port, charset, connect_timeout:
        Paramètres de connexion, transmis tels quels à
        :class:`MySQLSource`.

    table:
        Nom de la table à charger intégralement (``SELECT * FROM
        {table} LIMIT {max_rows}``). Mutuellement exclusif avec
        ``query``.

    query:
        Requête ``SELECT`` personnalisée à exécuter telle quelle.
        Mutuellement exclusif avec ``table``.

    max_rows:
        Nombre maximal de lignes chargées lorsque ``table`` est
        utilisé. Doit être strictement positif et ne peut pas
        dépasser :data:`MAX_ROWS_LIMIT`.

    params:
        Paramètres liés à la requête SQL (utilisés uniquement avec
        ``query``).
    """

    # ==========================================================
    # Configuration
    # ==========================================================

    DEFAULT_MAX_ROWS: Final[int] = 1_000
    MAX_ROWS_LIMIT: Final[int] = 100_000

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
        table: str | None = None,
        query: str | None = None,
        max_rows: int = DEFAULT_MAX_ROWS,
        params: dict[str, Any] | None = None,
        id_document: int | None = None,
        id_panne: int | None = None,
        max_content_bytes: int | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialise un loader MySQL.

        Raises
        ------
        DatabaseValidationError
            Si ni ``table`` ni ``query`` n'est fourni, si les deux
            sont fournis simultanément, ou si ``max_rows`` est
            invalide.
        """

        from app.exceptions import DatabaseValidationError

        # Filter out GMAO-specific kwargs before passing to MySQLSource
        # which only accepts host/database/user/password/port/charset/connect_timeout
        super().__init__(
            host,
            database,
            user,
            password,
        )

        if (table is None) == (query is None):
            raise DatabaseValidationError(
                message=(
                    "Exactly one of 'table' or 'query' must be "
                    "provided."
                ),
                details={
                    "table": table,
                    "query": query,
                },
            )

        if not isinstance(max_rows, int) or isinstance(max_rows, bool):
            raise DatabaseValidationError(
                message="'max_rows' must be an integer.",
                details={"max_rows": max_rows},
            )

        if max_rows <= 0:
            raise DatabaseValidationError(
                message="'max_rows' must be greater than zero.",
                details={"max_rows": max_rows},
            )

        if max_rows > self.MAX_ROWS_LIMIT:
            raise DatabaseValidationError(
                message=(
                    f"'max_rows' ({max_rows}) exceeds the maximum "
                    f"allowed value ({self.MAX_ROWS_LIMIT})."
                ),
                details={
                    "max_rows": max_rows,
                    "max_rows_limit": self.MAX_ROWS_LIMIT,
                },
            )

        if params is not None and not isinstance(params, dict):
            raise DatabaseValidationError(
                message="'params' must be a dictionary.",
                details={"params_type": type(params).__name__},
            )

        self._table = table
        self._query = query
        self._max_rows = max_rows
        self._params = params or {}
        self._id_document = id_document
        self._id_panne = id_panne
        self._max_content_bytes = max_content_bytes

    # ==========================================================
    # Mode Resolution
    # ==========================================================

    def _load_mode(self) -> str:
        """
        Détermine le mode de chargement utilisé par ce loader.

        Returns
        -------
        str
            ``"select"`` si une requête personnalisée est fournie,
            ``"table"`` si un nom de table est fourni, ``"unknown"``
            sinon (état normalement inatteignable une fois la
            validation du constructeur passée).
        """

        if self._query is not None:
            return "select"

        if self._table is not None:
            return "table"

        return "unknown"

    # ==========================================================
    # Query Construction
    # ==========================================================

    def _build_query(self) -> str:
        """
        Construit la requête SQL à exécuter selon le mode courant.

        Returns
        -------
        str
            Requête SQL prête à être exécutée par
            :meth:`MySQLSource.execute_query`.
        """

        if self._query is not None:
            # Only inject LIMIT if the query doesn't already contain one
            query_upper = self._query.strip().upper()
            if "LIMIT" not in query_upper:
                return f"{self._query} LIMIT {self._max_rows}"
            return self._query

        table_name = self.validate_identifier(self._table)

        return f"SELECT * FROM {table_name} LIMIT {self._max_rows}"

    # ==========================================================
    # Public API
    # ==========================================================

    def load(self) -> SourceDocument:
        """
        Exécute la requête résolue et retourne un ``SourceDocument``.

        Returns
        -------
        SourceDocument
            Document standardisé contenant le résultat de la
            requête, sous forme de texte, ainsi que les métadonnées
            associées.

        Raises
        ------
        DatabaseValidationError
            Si un ``id_document`` ou ``id_panne`` fourni ne
            correspond à aucun enregistrement parent.

        QueryExecutionError
            Erreur d'exécution SQL.

        TableNotFoundError
            Table inexistante (mode ``table``).
        """

        from app.exceptions import DatabaseValidationError

        # --- Step 1: Validate GMAO parent existence ---
        parent_info = self._validate_gmao_parents()

        # --- Step 2: Build and execute query ---
        sql = self._build_query()

        self.logger.info(
            "Loading MySQL data from '%s' (mode=%s).",
            self.source_name,
            self._load_mode(),
        )

        rows = self.execute_query(sql, self._params)

        # --- Step 3: Determine if result was limited ---
        limited = self._load_mode() == "select" and len(rows) >= self._max_rows

        # --- Step 4: Build content ---
        # In query mode without row headers, use flat key:value format
        if self._query is not None:
            content = self._rows_to_flat_text(rows)
        else:
            content = self._rows_to_text(rows)

        # --- Step 5: Truncate content if max_content_bytes is set ---
        if self._max_content_bytes is not None:
            encoded = content.encode("utf-8")
            if len(encoded) > self._max_content_bytes:
                content = encoded[: self._max_content_bytes].decode(
                    "utf-8", errors="ignore",
                )

        now = datetime.now(tz=UTC)

        columns = list(rows[0].keys()) if rows else []

        # --- Step 6: Build metadata ---
        metadata: dict[str, Any] = {
            "driver": "mysql",
            "host": self.host,
            "database": self.database,
            "query": self._query,
            "query_mode": "query" if self._query is not None else "table",
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": columns,
            "sql_operation": self._detect_sql_operation(),
            "limited": limited,
            "max_rows": self._max_rows,
            "table": self._table,
            "mode": self._load_mode(),
        }

        # Attach GMAO parent info
        if self._id_document is not None:
            metadata["id_document"] = self._id_document
        if self._id_panne is not None:
            metadata["id_panne"] = self._id_panne
        metadata.update(parent_info)

        self.logger.info(
            "MySQL source '%s' loaded successfully (%d row(s)).",
            self.source_name,
            len(rows),
        )

        return SourceDocument(
            source_name=self.source_name,
            source_type="mysql",
            source_path=self.source_path,
            content=content,
            mime_type="application/x-mysql-resultset",
            size=len(content.encode("utf-8")),
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )

    # ==========================================================
    # GMAO Parent Validation
    # ==========================================================

    def _validate_gmao_parents(self) -> dict[str, Any]:
        """
        Valide l'existence des parents GMAO (id_document, id_panne).

        Returns
        -------
        dict
            Métadonnées parentales (id_document, id_equipement, etc.).

        Raises
        ------
        DatabaseValidationError
            Si un ID parent fourni n'existe pas dans la base.
        """
        from app.exceptions import DatabaseValidationError

        parent_info: dict[str, Any] = {}

        if self._id_panne is not None:
            rows = self.execute_query(
                "SELECT id_panne, id_equipement FROM pannes "
                "WHERE id_panne = :parent_id",
                {"parent_id": self._id_panne},
            )
            if not rows:
                raise DatabaseValidationError(
                    message=(
                        f"GMAO parent 'id_panne={self._id_panne}' "
                        "not found."
                    ),
                    details={"id_panne": self._id_panne},
                )
            parent_info["id_panne"] = rows[0].get("id_panne", self._id_panne)
            parent_info["id_equipement"] = rows[0].get("id_equipement")

        if self._id_document is not None:
            rows = self.execute_query(
                "SELECT id_document, id_equipement FROM documents "
                "WHERE id_document = :parent_id",
                {"parent_id": self._id_document},
            )
            if not rows:
                raise DatabaseValidationError(
                    message=(
                        f"GMAO parent 'id_document={self._id_document}' "
                        "not found."
                    ),
                    details={"id_document": self._id_document},
                )
            parent_info["id_document"] = rows[0].get("id_document", self._id_document)
            parent_info["id_equipement"] = rows[0].get("id_equipement")

        return parent_info

    # ==========================================================
    # SQL Operation Detection
    # ==========================================================

    def _detect_sql_operation(self) -> str:
        """Detect the SQL operation type from the query."""
        source = self._query or f"SELECT * FROM {self._table}"
        first_word = source.strip().split()[0].lower()
        return first_word

    # ==========================================================
    # Row Conversion
    # ==========================================================

    def _rows_to_text(
        self,
        rows: list[dict[str, Any]],
    ) -> str:
        """
        Convertit les résultats SQL en texte adapté au RAG.

        Chaque ligne SQL conserve son unité sémantique :

            --- Row 1 ---
            colonne_a: valeur
            colonne_b: valeur

        Les valeurs complexes sont sérialisées de manière
        déterministe.
        """

        blocks: list[str] = []

        for index, row in enumerate(
            rows,
            start=1,
        ):
            lines = [
                f"--- Row {index} ---"
            ]

            for column, value in row.items():
                normalized_value = (
                    self._format_value(value)
                )

                lines.append(
                    f"{column}: "
                    f"{normalized_value}"
                )

            blocks.append(
                "\n".join(lines)
            )

        return "\n\n".join(blocks)

    def _rows_to_flat_text(
        self,
        rows: list[dict[str, Any]],
    ) -> str:
        """
        Convertit les résultats SQL en texte plat (sans en-têtes).

        Format utilisé en mode query pour un rendu plus naturel :

            colonne_a: valeur
            colonne_b: valeur
        """

        blocks: list[str] = []

        for row in rows:
            lines: list[str] = []
            for column, value in row.items():
                normalized_value = self._format_value(value)
                lines.append(f"{column}: {normalized_value}")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    # ==========================================================
    # Value Normalization
    # ==========================================================

    @staticmethod
    def _format_value(
        value: Any,
    ) -> str:
        """
        Convertit une valeur MySQL en représentation texte
        stable pour l'indexation RAG.
        """

        if value is None:
            return ""

        if isinstance(
            value,
            datetime,
        ):
            return value.isoformat(
                sep=" ",
            )

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, time):
            return value.isoformat()

        if isinstance(value, Decimal):
            return str(value)

        if isinstance(
            value,
            (dict, list, tuple),
        ):
            try:
                return json.dumps(
                    value,
                    ensure_ascii=False,
                    default=str,
                )
            except (TypeError, ValueError):
                return str(value)

        if isinstance(value, bytes):
            try:
                return value.decode(
                    "utf-8",
                )
            except UnicodeDecodeError:
                return value.hex()

        return str(value)

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        """
        Représentation de debug sans données sensibles.
        """

        return (
            f"{self.__class__.__name__}("
            f"source={super().source_name!r}, "
            f"table={self._table!r}, "
            f"has_query={self._query is not None}, "
            f"max_rows={self._max_rows!r})"
        )

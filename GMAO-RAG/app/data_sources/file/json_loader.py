"""
app/data_sources/file/json_loader.py
====================================

Description
-----------
Loader des fichiers JSON.

Cette classe permet de charger des documents JSON et de les
convertir en SourceDocument afin qu'ils puissent être utilisés
par le pipeline RAG.

Fonctionnalités :

- validation du fichier ;
- détection de l'encodage (mutualisée via
  ``app.data_sources.file.utils.detect_text_encoding``) ;
- lecture JSON ;
- validation de la profondeur d'imbrication (mutualisée via
  ``app.data_sources.file.validators.ensure_max_nesting_depth``) ;
- conversion en texte ;
- enrichissement des métadonnées.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from app.data_sources.file.file_source import FileSource
from app.data_sources.file.utils import detect_text_encoding
from app.exceptions import JSONParsingError
from app.models.document import SourceDocument


class JSONLoader(FileSource):
    """
    Loader des fichiers JSON.
    """

    # ==========================================================
    # Configuration
    # ==========================================================

    SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (
        ".json",
    )

    DEFAULT_ENCODINGS: Final[tuple[str, ...]] = (
        "utf-8",
        "utf-8-sig",
    )

    INDENT: Final[int] = 2

    MAX_NESTING_DEPTH: Final[int] = 50
    """
    Profondeur maximale d'imbrication autorisée pour un document
    JSON. Protège contre les documents pathologiquement imbriqués
    qui provoqueraient un ``RecursionError``.
    """

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(
        self,
        source: str | Path,
    ) -> None:
        """
        Initialise un loader JSON.
        """

        super().__init__(source)

        self._encoding: str | None = None

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def encoding(self) -> str | None:
        """
        Encodage détecté.
        """
        return self._encoding

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _json_to_text(
        self,
        data: Any,
    ) -> str:
        """
        Convertit une structure JSON en texte lisible pour l'indexation RAG.

        Chaque valeur scalaire est représentée sous la forme
        "chemin: valeur" (ex: 'user.address.city: Paris',
        'items[2].name: Widget'), ce qui préserve la structure
        hiérarchique du document tout en produisant un texte propre,
        sans le bruit syntaxique d'un dump JSON brut (accolades,
        guillemets, virgules).

        La profondeur d'imbrication est supposée déjà validée par
        l'appelant (voir
        ``app.data_sources.file.validators.ensure_max_nesting_depth``,
        appelée dans ``load()``) : cette méthode ne fait donc que la
        conversion, sans dupliquer le contrôle de profondeur.

        Parameters
        ----------
        data:
            Structure JSON déjà chargée (dict, list, str, int, float,
            bool ou None).

        Returns
        -------
        str
            Représentation textuelle du document, une entrée par ligne.

        Raises
        ------
        JSONParsingError
            Si une récursion excessive est tout de même rencontrée
            (garde-fou de dernier recours).
        """

        lines: list[str] = []

        def _walk(value: Any, path: str) -> None:
            if isinstance(value, dict):
                if not value:
                    lines.append(f"{path or '<root>'}: {{}}")
                    return

                for key, val in value.items():
                    child_path = f"{path}.{key}" if path else str(key)
                    _walk(val, child_path)

            elif isinstance(value, list):
                if not value:
                    lines.append(f"{path or '<root>'}: []")
                    return

                for index, item in enumerate(value):
                    child_path = f"{path}[{index}]"
                    _walk(item, child_path)

            elif value is None:
                lines.append(f"{path or '<root>'}: null")

            elif isinstance(value, bool):
                lines.append(f"{path or '<root>'}: {str(value).lower()}")

            else:
                lines.append(f"{path or '<root>'}: {value}")

        try:
            _walk(data, "")
        except RecursionError as exc:
            raise JSONParsingError(
                message=(
                    f"JSON structure in '{self.filename}' is too "
                    f"deeply nested to process."
                ),
                original=exc,
            ) from exc

        return "\n".join(lines)

    # ==========================================================
    # Public API
    # ==========================================================

    def load(self) -> SourceDocument:
        """
        Charge le fichier JSON.

        Returns
        -------
        SourceDocument
            Document chargé et normalisé.

        Raises
        ------
        EmptyFileError
            Si le fichier est vide ou ne contient que des espaces.

        JSONParsingError
            Si le contenu n'est pas un JSON valide, ou si la
            structure dépasse la profondeur maximale autorisée.

        InvalidEncodingError
            Si le fichier ne peut pas être décodé.
        """

        from app.data_sources.file.validators import (
            ensure_max_nesting_depth,
        )
        from app.exceptions import (
            EmptyFileError,
            InvalidEncodingError,
        )

        self.logger.info(
            "Loading JSON file '%s'.",
            self.path,
        )

        # ==========================================================
        # Validation
        # ==========================================================

        self.validate()

        # ==========================================================
        # Extension
        # ==========================================================

        self.ensure_extension(
            *self.SUPPORTED_EXTENSIONS,
        )

        # ==========================================================
        # Encoding
        # ==========================================================

        self._encoding = detect_text_encoding(
            self,
            self.DEFAULT_ENCODINGS,
        )

        if self._encoding is None:
            raise InvalidEncodingError(
                message=(
                    f"Unable to decode '{self.filename}'. "
                    f"Tried encodings: "
                    f"{', '.join(self.DEFAULT_ENCODINGS)}."
                ),
                details={
                    "path": str(self.path),
                    "encodings": list(self.DEFAULT_ENCODINGS),
                },
            )

        self.logger.debug(
            "Detected encoding: %s",
            self._encoding,
        )

        # ==========================================================
        # Read raw content
        # ==========================================================

        try:
            with self.open_file(
                mode="r",
                encoding=self._encoding,
            ) as file:
                raw_content = file.read()

        except UnicodeDecodeError as exc:
            raise InvalidEncodingError(
                message=(
                    f"Unable to decode "
                    f"'{self.filename}'."
                ),
                details={
                    "path": str(self.path),
                    "encoding": self._encoding,
                },
                original=exc,
            ) from exc

        # ==========================================================
        # Empty content
        # ==========================================================

        if not raw_content.strip():
            raise EmptyFileError(
                message=(
                    f"File '{self.path}' "
                    f"is empty."
                )
            )

        # ==========================================================
        # JSON Parsing
        # ==========================================================

        try:
            data = json.loads(raw_content)

        except json.JSONDecodeError as exc:
            raise JSONParsingError(
                message=(
                     f"Invalid JSON "
                    f"in '{self.filename}'."
                ),
                details={
                    "line": exc.lineno,
                    "column": exc.colno,
                    "position": exc.pos,
                },
                original=exc,
            ) from exc

        # ==========================================================
        # Nesting depth validation
        # ==========================================================

        ensure_max_nesting_depth(
            data,
            self.MAX_NESTING_DEPTH,
            self.filename,
        )

        # ==========================================================
        # Convert JSON to RAG text
        # ==========================================================

        content = self._json_to_text(data)

        # ==========================================================
        # Metadata
        # ==========================================================

        metadata = dict(
            self.metadata()
        )

        metadata.update(
            {
                "encoding": self._encoding,
                "root_type": type(data).__name__,
                "items_count": (
                    len(data)
                    if isinstance(
                        data,
                        (list, dict),
                    )
                    else 1
                ),
                "keys": (
                    list(data.keys())
                    if isinstance(data, dict)
                    else []
                ),
            }
        )

        # ==========================================================
        # Logging
        # ==========================================================

        self.logger.info(
            "JSON file '%s' loaded successfully.",
            self.filename,
        )

        # ==========================================================
        # SourceDocument
        # ==========================================================

        return SourceDocument(
            source_name=self.filename,
            source_type="json",
            source_path=self.path,
            content=content,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            updated_at=self.modified_at,
            metadata=metadata,
        )

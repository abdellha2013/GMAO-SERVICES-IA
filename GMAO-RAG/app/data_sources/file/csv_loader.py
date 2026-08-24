"""
app/data_sources/file/csv_loader.py
===================================

Description
-----------
Loader des fichiers CSV.

Cette classe permet de charger des fichiers CSV et de les
convertir en SourceDocument afin qu'ils puissent être utilisés
dans le pipeline RAG.

Fonctionnalités :

- validation du fichier ;
- détection de l'encodage ;
- détection automatique du séparateur ;
- conversion des lignes CSV en texte ;
- enrichissement des métadonnées.

La lecture complète du fichier est réalisée dans la méthode
load().
"""

from __future__ import annotations

import csv
from typing import Final

from app.data_sources.file.file_source import FileSource
from app.data_sources.file.utils import detect_text_encoding
from app.models.document import SourceDocument
from pathlib import Path


class CSVLoader(FileSource):
    """
    Loader des fichiers CSV.
    """

    # ==========================================================
    # Configuration
    # ==========================================================

    SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (
        ".csv",
    )

    DEFAULT_ENCODINGS: Final[tuple[str, ...]] = (
        "utf-8",
        "utf-8-sig",
    )

    DEFAULT_DELIMITERS: Final[tuple[str, ...]] = (
        ",",
        ";",
        "\t",
        "|",
    )

    SAMPLE_SIZE: Final[int] = 4096
    """
    Nombre d'octets utilisés pour détecter
    automatiquement le séparateur CSV.
    """

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(self, source: str | Path) -> None:
        """
        Initialise un nouveau loader CSV.

        Parameters
        ----------
        source:
            Chemin du fichier CSV.
        """

        super().__init__(source)

        self._encoding: str | None = None
        self._delimiter: str | None = None

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def encoding(self) -> str | None:
        """
        Encodage actuellement utilisé.
        """
        return self._encoding

    @property
    def delimiter(self) -> str | None:
        """
        Séparateur détecté.
        """
        return self._delimiter

    # ==========================================================
    # Public API
    # ==========================================================

    def load(self) -> SourceDocument:
        """
        Charge le fichier CSV.

        Returns
        -------
        SourceDocument
        """

        self.logger.info("Loading CSV file '%s'.", self.path)

        # Validation du fichier
        self.validate()

        # Vérification de l'extension
        self.ensure_extension(*self.SUPPORTED_EXTENSIONS)

        # Détection de l'encodage
        self._encoding = self._detect_encoding()

        self.logger.debug(
            "Detected encoding: %s",
            self._encoding,
        )

        # Lecture complète du fichier
        with self.open_file(
            mode="r",
            encoding=self._encoding,
        ) as file:

            sample = file.read(self.SAMPLE_SIZE)
            file.seek(0)

            # Détection du séparateur
            self._delimiter = self._detect_delimiter(sample)

            self.logger.debug(
                "Detected delimiter: %r",
                self._delimiter,
            )

            reader = csv.DictReader(
                file,
                delimiter=self._delimiter,
            )

            rows = list(reader)

        # Conversion en texte
        content = self._rows_to_text(rows)

        metadata = dict(self.metadata())

        metadata.update(
            {
                "encoding": self._encoding,
                "delimiter": self._delimiter,
                "rows_count": len(rows),
                "columns_count": len(reader.fieldnames or []),
                "headers": reader.fieldnames or [],
            }
        )

        self.logger.info(
            "CSV successfully loaded (%d rows).",
            len(rows),
        )

        return SourceDocument(
            source_name=self.filename,
            source_type="csv",
            source_path=self.path,
            content=content,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            updated_at=self.modified_at,
            metadata=metadata,
        )


    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _detect_encoding(self) -> str:
        """
        Détecte automatiquement l'encodage du fichier.

        Réutilise la logique mutualisée dans
        ``app.data_sources.file.utils.detect_text_encoding``.

        Returns
        -------
        str

        Raises
        ------
        InvalidEncodingError
        """

        from app.exceptions import InvalidEncodingError

        encoding = detect_text_encoding(
            self,
            self.DEFAULT_ENCODINGS,
            sample_only=True,
        )

        if encoding is not None:
            return encoding

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


    def _detect_delimiter(
        self,
        sample: str,
    ) -> str:
        """
        Détecte automatiquement le séparateur CSV.

        Parameters
        ----------
        sample:
            Premier extrait du fichier.

        Returns
        -------
        str
        """

        try:

            dialect = csv.Sniffer().sniff(
                sample,
                delimiters=self.DEFAULT_DELIMITERS,
            )

            return dialect.delimiter

        except csv.Error:

            self.logger.warning(
                "Unable to detect delimiter. "
                "Using ','."
            )

            return ","
    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _rows_to_text(
        self,
        rows: list[dict[str, str]],
    ) -> str:
        """
        Convertit les lignes CSV en texte exploitable par le pipeline RAG.

        Chaque ligne devient un bloc de texte de la forme :

            id: 1
            name: CNC-01
            status: Running

            id: 2
            name: CNC-02
            status: Maintenance

        Les lignes sont séparées par une ligne vide afin
        d'améliorer le découpage (chunking).

        Parameters
        ----------
        rows:
            Lignes lues par csv.DictReader.

        Returns
        -------
        str
            Représentation textuelle du fichier CSV.
        """

        if not rows:
            self.logger.warning(
                "CSV file '%s' contains no data rows.",
                self.path,
            )
            return ""

        documents: list[str] = []

        for row_index, row in enumerate(rows, start=1):

            lines: list[str] = []

            for key, value in row.items():

                # Ignore les colonnes invalides produites
                # par csv.DictReader.
                if key is None:
                    continue

                key = str(key).strip()

                if value is None:
                    value = ""
                else:
                    value = str(value).strip()

                lines.append(f"{key}: {value}")

            documents.append("\n".join(lines))

        self.logger.debug(
            "Converted %d CSV rows into text.",
            len(documents),
        )

        return "\n\n".join(documents)
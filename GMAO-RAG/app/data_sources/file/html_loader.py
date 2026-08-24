"""
app/data_sources/file/html_loader.py
====================================

Description
-----------
Loader des fichiers HTML.

Cette classe permet de charger des documents HTML et de convertir
leur contenu en texte exploitable par le pipeline RAG.

Fonctionnalités
----------------

- validation du fichier ;
- vérification de l'extension ;
- détection de l'encodage ;
- lecture du HTML ;
- extraction du texte ;
- suppression des éléments non pertinents ;
- conservation des métadonnées utiles ;
- création d'un SourceDocument.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from app.data_sources.file.file_source import FileSource
from app.data_sources.file.utils import detect_text_encoding
from app.models.document import SourceDocument


class HTMLLoader(FileSource):
    """
    Loader des fichiers HTML.

    Le HTML brut n'est pas directement envoyé au pipeline RAG.
    Le loader extrait le contenu textuel utile du document.
    """

    # ==========================================================
    # Configuration
    # ==========================================================

    SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (
        ".html",
        ".htm",
    )

    DEFAULT_ENCODINGS: Final[tuple[str, ...]] = (
        "utf-8",
        "utf-8-sig",
    )

    # Balises dont le contenu n'est généralement pas pertinent
    # pour le texte destiné au pipeline RAG.
    IGNORED_TAGS: Final[tuple[str, ...]] = (
        "script",
        "style",
        "noscript",
        "template",
    )

    # Séparateur utilisé entre les blocs de texte extraits.
    TEXT_SEPARATOR: Final[str] = "\n"

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(
        self,
        source: str | Path,
    ) -> None:
        """
        Initialise un loader HTML.

        Parameters
        ----------
        source:
            Chemin du fichier HTML.
        """

        super().__init__(source)

        self._encoding: str | None = None

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def encoding(self) -> str | None:
        """
        Retourne l'encodage détecté du fichier.
        """

        return self._encoding

    # ==========================================================
    # Public API
    # ==========================================================

    def load(self) -> SourceDocument:
        """
        Charge le fichier HTML.

        Returns
        -------
        SourceDocument
            Document HTML chargé et normalisé.

        Raises
        ------
        EmptyFileError
            Si le fichier est vide ou ne contient que des espaces.

        InvalidEncodingError
            Si le fichier ne peut pas être décodé.

        HTMLParsingError
            Si le document HTML ne peut pas être traité.
        """

        from app.exceptions import (
            EmptyFileError,
            HTMLParsingError,
            InvalidEncodingError,
        )

        self.logger.info(
            "Loading HTML file '%s'.",
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

        self._encoding = self._detect_encoding()

        self.logger.debug(
            "Detected encoding: %s",
            self._encoding,
        )

        # ==========================================================
        # Read raw HTML
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
        # HTML extraction
        # ==========================================================

        try:
            content = self._extract_text(
                raw_content,
            )

        except Exception as exc:
            raise HTMLParsingError(
                message=(
                    f"Unable to parse HTML "
                    f"file '{self.filename}'."
                ),
                details={
                    "path": str(self.path),
                },
                original=exc,
            ) from exc

        # ==========================================================
        # Validate extracted content
        # ==========================================================

        from app.data_sources.file.validators import ensure_non_empty_content

        ensure_non_empty_content(
            content,
            self.filename,
            logger=self.logger,
        )

        # ==========================================================
        # Metadata
        # ==========================================================

        metadata = dict(
            self.metadata()
        )

        metadata.update(
            {
                "encoding": self._encoding,
                "content_length": len(content),
            }
        )

        # ==========================================================
        # Logging
        # ==========================================================

        self.logger.info(
            "HTML file '%s' loaded successfully.",
            self.filename,
        )

        # ==========================================================
        # SourceDocument
        # ==========================================================
        # Réutilise les valeurs déjà calculées par self.metadata()
        # plutôt que de refaire des appels stat() supplémentaires.

        return SourceDocument(
            source_name=self.filename,
            source_type="html",
            source_path=self.path,
            content=content,
            mime_type=self.mime_type,
            size=metadata["size"],
            created_at=metadata["created_at"],
            updated_at=metadata["modified_at"],
            metadata=metadata,
        )

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _detect_encoding(self) -> str:
        """
        Détecte l'encodage du fichier HTML.

        Réutilise la logique mutualisée dans
        ``app.data_sources.file.utils.detect_text_encoding``.

        Returns
        -------
        str
            Encodage valide détecté.

        Raises
        ------
        InvalidEncodingError
            Si aucun encodage ne permet de lire le fichier.
        """

        from app.exceptions import InvalidEncodingError

        encoding = detect_text_encoding(
            self,
            self.DEFAULT_ENCODINGS,
        )

        if encoding is not None:
            return encoding

        raise InvalidEncodingError(
            message=(
                f"Unable to decode "
                f"'{self.filename}'. "
                f"Tried encodings: "
                f"{', '.join(self.DEFAULT_ENCODINGS)}."
            ),
            details={
                "path": str(self.path),
                "encodings": list(
                    self.DEFAULT_ENCODINGS
                ),
            },
        )

    def _extract_text(
        self,
        html_content: str,
    ) -> str:
        """
        Extrait le texte utile d'un document HTML.

        Les éléments non pertinents pour le pipeline RAG
        sont supprimés :

        - script
        - style
        - noscript
        - template

        Les blocs de texte sont ensuite nettoyés et séparés
        par des retours à la ligne.

        Parameters
        ----------
        html_content:
            Contenu HTML brut.

        Returns
        -------
        str
            Texte nettoyé et exploitable par le pipeline RAG.

        Raises
        ------
        HTMLParsingError
            Si BeautifulSoup ne peut pas traiter le document.
            (Levée par l'appelant, `load()`, qui capture toute
            exception issue de cette méthode.)
        """

        from bs4 import BeautifulSoup, Comment

        self.logger.debug(
            "Extracting text from HTML file '%s'.",
            self.filename,
        )

        soup = BeautifulSoup(
            html_content,
            "html.parser",
        )

        # ==========================================================
        # Remove ignored elements
        # ==========================================================

        for tag_name in self.IGNORED_TAGS:

            for tag in soup.find_all(tag_name):
                tag.decompose()

        # ==========================================================
        # Remove HTML comments
        # ==========================================================

        for comment in soup.find_all(
            string=lambda text: isinstance(text, Comment)
        ):
            comment.extract()

        # ==========================================================
        # Extract meaningful text
        # ==========================================================

        text = soup.get_text(
            separator=self.TEXT_SEPARATOR,
            strip=True,
        )

        # ==========================================================
        # Normalize lines
        # ==========================================================

        lines: list[str] = []

        for line in text.splitlines():

            cleaned = " ".join(
                line.split()
            )

            if cleaned:
                lines.append(cleaned)

        # ==========================================================
        # Final content
        # ==========================================================

        return self.TEXT_SEPARATOR.join(lines)
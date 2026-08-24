"""
app/data_sources/file/txt_loader.py
===================================

Loader des fichiers texte (.txt).

Cette classe charge un fichier texte brut et retourne une
instance de SourceDocument.

Encodages essayés automatiquement :

- utf-8
- utf-8-sig

Si aucun ne fonctionne, une InvalidEncodingError est levée.

La logique de chargement (validation, détection d'encodage,
construction du SourceDocument) est factorisée dans
``_load_as_text()`` afin d'être réellement réutilisable par les
loaders qui héritent de cette classe (voir ``MarkdownLoader``),
plutôt que d'être dupliquée.
"""

from __future__ import annotations

from typing import Final

from app.data_sources.file.file_source import FileSource
from app.data_sources.file.utils import detect_text_encoding
from app.exceptions import InvalidEncodingError
from app.models.document import SourceDocument


class TXTLoader(FileSource):
    """
    Loader des fichiers texte (.txt).
    """

    DEFAULT_ENCODINGS: Final[tuple[str, ...]] = (
        "utf-8",
        "utf-8-sig",
    )

    SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (".txt",)

    SOURCE_TYPE: Final[str] = "txt"

    def load(self) -> SourceDocument:
        """
        Charge un fichier texte.

        Returns
        -------
        SourceDocument

        Raises
        ------
        InvalidEncodingError
            Si aucun encodage compatible n'a été trouvé.
        """

        self.logger.info("Loading TXT file '%s'.", self.path)

        document = self._load_as_text(
            extensions=self.SUPPORTED_EXTENSIONS,
            source_type=self.SOURCE_TYPE,
        )

        self.logger.info(
            "TXT file '%s' loaded successfully using '%s'.",
            self.filename,
            document.metadata["encoding"],
        )

        return document

    # ==========================================================
    # Shared Loading Logic
    # ==========================================================

    def _load_as_text(
        self,
        *,
        extensions: tuple[str, ...],
        source_type: str,
    ) -> SourceDocument:
        """
        Valide, détecte l'encodage et construit un SourceDocument
        à partir d'un fichier texte brut.

        Factorisée afin d'être réutilisée telle quelle par les
        sous-classes qui ne diffèrent que par les extensions
        acceptées et le ``source_type`` retourné (ex:
        ``MarkdownLoader``).

        Parameters
        ----------
        extensions:
            Extensions de fichier acceptées.

        source_type:
            Valeur de ``SourceDocument.source_type`` à utiliser.

        Returns
        -------
        SourceDocument

        Raises
        ------
        InvalidEncodingError
            Si aucun encodage compatible n'a été trouvé.
        """

        # Validation générale
        self.validate()

        # Vérification de l'extension
        self.ensure_extension(*extensions)

        # Détection de l'encodage (logique mutualisée)
        encoding = detect_text_encoding(
            self,
            self.DEFAULT_ENCODINGS,
        )

        if encoding is None:
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
            "Detected encoding '%s' for '%s'.",
            encoding,
            self.filename,
        )

        content = self.read_text(
            encoding=encoding,
            errors="strict",
        )

        metadata = dict(self.metadata())
        metadata["encoding"] = encoding

        return SourceDocument(
            source_name=self.filename,
            source_type=source_type,
            source_path=self.path,
            content=content,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            updated_at=self.modified_at,
            metadata=metadata,
        )

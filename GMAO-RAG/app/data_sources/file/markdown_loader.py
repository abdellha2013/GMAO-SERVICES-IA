"""
app/data_sources/file/markdown_loader.py
========================================

Loader des fichiers Markdown (.md, .markdown).

Le Markdown étant un format texte, ce loader hérite directement
de TXTLoader et réutilise réellement toute sa logique via
``TXTLoader._load_as_text()`` :

- validation ;
- lecture du fichier ;
- gestion des erreurs ;
- détection de l'encodage (utf-8 -> utf-8-sig).

La seule différence est l'extension acceptée et le type de
source retourné ("markdown").
"""

from __future__ import annotations

from typing import Final

from app.data_sources.file.txt_loader import TXTLoader
from app.models.document import SourceDocument


class MarkdownLoader(TXTLoader):
    """
    Loader des fichiers Markdown.
    """

    SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (".md", ".markdown")

    SOURCE_TYPE: Final[str] = "markdown"

    def load(self) -> SourceDocument:
        """
        Charge un document Markdown.

        Réutilise la logique de détection d'encodage de
        ``TXTLoader`` via ``_load_as_text()``, plutôt que de la
        dupliquer avec un encodage figé.

        Returns
        -------
        SourceDocument
            Document contenant le texte Markdown brut.
        """

        self.logger.info("Loading Markdown file '%s'.", self.path)

        document = self._load_as_text(
            extensions=self.SUPPORTED_EXTENSIONS,
            source_type=self.SOURCE_TYPE,
        )

        self.logger.info(
            "Markdown file '%s' loaded successfully using '%s'.",
            self.filename,
            document.metadata["encoding"],
        )

        return document

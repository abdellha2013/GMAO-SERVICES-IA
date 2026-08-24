
"""
Loader spécialisé pour les fichiers PDF.

Ce loader :

- valide le fichier ;
- vérifie l'extension ;
- détecte le type MIME ;
- ouvre le document PDF ;
- extrait le texte page par page ;
- nettoie uniquement les artefacts évidents d'extraction ;
- conserve la structure des pages ;
- construit un SourceDocument standardisé.

Le résultat est utilisé par le pipeline RAG :

PDF
↓
PDFLoader
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

import re
from pathlib import Path
from typing import Final

from app.data_sources.file.file_source import FileSource
from app.models.document import SourceDocument


class PDFLoader(FileSource):
    """
    Loader pour les fichiers PDF.

    Parameters
    ----------
    source:
        Chemin du fichier PDF.
    """

    SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (".pdf",)

    # ------------------------------------------------------------------
    # Patterns d'artefacts connus produits par certaines extractions PDF.
    #
    # IMPORTANT :
    # Ces patterns sont volontairement stricts afin de ne pas supprimer
    # des caractères légitimes présents dans le document.
    # ------------------------------------------------------------------

    _PDF_ARTIFACT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
        # Certaines extractions PDF produisent des lignes de
        # séparation "cassées", composées uniquement de tirets,
        # d'apostrophes inversées (`) et de virgules
        # (ex: "--`,,,`---"), qui ne portent aucune information et
        # doivent être supprimées. Le pattern précédent
        # (r"^\s*--`{1,},+`{1,},*.*?---\s*$") appliquait des
        # quantificateurs sur des caractères isolés de façon
        # incohérente et ne correspondait, de fait, à quasiment
        # aucune ligne réelle. Une ligne n'est considérée comme un
        # artefact que si elle est composée EXCLUSIVEMENT de ces
        # caractères de séparation (au moins 3, pour éviter de
        # supprimer un contenu légitime court comme "---" seul
        # utilisé comme puce), ET contenir au moins une apostrophe
        # inversée : ce caractère est rare dans du texte normal et
        # sert de signal fort qu'il s'agit bien d'un artefact
        # d'extraction plutôt qu'une ligne de tirets légitime
        # (ex: séparateur Markdown "---"). À valider/affiner avec
        # des exemples réels d'extraction PDF rencontrés en
        # production.
        re.compile(r"^(?=[-`,\s]*`)[-`,\s]{3,}$"),
    )

    def __init__(self, source: str | Path) -> None:
        """
        Initialise le loader PDF.
        """
        super().__init__(source)

    # ==============================================================
    # Source Information
    # ==============================================================

    @property
    def source_name(self) -> str:
        """
        Retourne le nom du fichier source.

        Returns
        -------
        str
            Nom du fichier PDF.
        """
        return self.filename

    # ==============================================================
    # Text Normalization
    # ==============================================================

    @classmethod
    def _is_extraction_artifact(cls, line: str) -> bool:
        """
        Vérifie si une ligne correspond à un artefact connu
        d'extraction PDF.

        La vérification est volontairement conservatrice :
        seuls les patterns explicitement identifiés sont supprimés.

        Parameters
        ----------
        line:
            Ligne extraite du PDF.

        Returns
        -------
        bool
            True si la ligne est considérée comme un artefact.
        """
        normalized = line.strip()

        if not normalized:
            return False

        return any(
            pattern.fullmatch(normalized)
            for pattern in cls._PDF_ARTIFACT_PATTERNS
        )

    @classmethod
    def _clean_page_text(cls, text: str) -> str:
        """
        Nettoie le texte extrait d'une page PDF.

        Le nettoyage reste volontairement limité à :

        - suppression des caractères de contrôle problématiques ;
        - suppression des lignes vides en début/fin ;
        - suppression des artefacts PDF connus ;
        - réduction des espaces horizontaux excessifs.

        Aucun remplacement agressif des caractères ``-``, ``,`` ou
        ``````, car ces caractères peuvent faire partie du contenu réel.

        Parameters
        ----------
        text:
            Texte brut extrait de la page.

        Returns
        -------
        str
            Texte nettoyé.
        """
        if not text:
            return ""

        # Normalisation des fins de ligne.
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")

        cleaned_lines: list[str] = []

        for line in text.split("\n"):

            # Suppression de certains caractères de contrôle,
            # tout en conservant \t.
            line = "".join(
                character
                for character in line
                if character in {"\t"} or character.isprintable()
            )

            # Suppression des espaces en fin de ligne.
            line = line.rstrip()

            # Suppression uniquement des artefacts identifiés.
            if cls._is_extraction_artifact(line):
                continue

            cleaned_lines.append(line)

        # Supprime les lignes vides au début et à la fin.
        while cleaned_lines and not cleaned_lines[0].strip():
            cleaned_lines.pop(0)

        while cleaned_lines and not cleaned_lines[-1].strip():
            cleaned_lines.pop()

        # Réduit les espaces horizontaux excessifs sans modifier
        # les espaces normaux entre les mots.
        normalized_lines: list[str] = []

        for line in cleaned_lines:
            line = re.sub(r"[ \t]{2,}", " ", line)
            normalized_lines.append(line)

        return "\n".join(normalized_lines).strip()

    # ==============================================================
    # Load
    # ==============================================================

    def load(self) -> SourceDocument:
        """
        Charge et extrait le contenu d'un fichier PDF.

        Le traitement est effectué page par page afin de :

        - conserver la séparation logique des pages ;
        - isoler les erreurs d'extraction ;
        - nettoyer les artefacts d'extraction ;
        - produire des statistiques fiables dans les métadonnées.

        Returns
        -------
        SourceDocument
            Document PDF standardisé.

        Raises
        ------
        FileValidationError
            Si le fichier n'est pas valide.

        InvalidPDFError
            Si le fichier n'est pas un PDF lisible.

        FileLoadingError
            Si le PDF ne peut pas être chargé.
        """

        from pypdf.errors import PdfReadError

        from app.exceptions import (
            FileLoadingError,
            InvalidPDFError,
        )

        self.logger.info(
            "Loading PDF file '%s'.",
            self.path,
        )

        # ==========================================================
        # Validation
        # ==========================================================

        self.validate()

        self.ensure_extension(
            *self.SUPPORTED_EXTENSIONS
        )

        # ==========================================================
        # Import dependency
        # ==========================================================

        try:
            from pypdf import PdfReader

        except ImportError as exc:

            raise FileLoadingError(
                message=(
                    "The 'pypdf' package is required "
                    "to load PDF files."
                ),
                original=exc,
            ) from exc

        # ==========================================================
        # Load PDF
        # ==========================================================

        try:

            reader = PdfReader(self.path)

        except PdfReadError as exc:

            self.logger.exception(
                "PDF file '%s' is not a valid PDF document.",
                self.path,
            )

            raise InvalidPDFError(
                message=(
                    f"File '{self.filename}' is not a valid "
                    "PDF document."
                ),
                original=exc,
            ) from exc

        except Exception as exc:

            self.logger.exception(
                "Unable to open PDF file '%s'.",
                self.path,
            )

            raise FileLoadingError(
                message=(
                    f"Unable to load PDF file "
                    f"'{self.filename}'."
                ),
                original=exc,
            ) from exc

        # ==========================================================
        # Extract pages
        # ==========================================================

        pages: list[str] = []

        pages_with_text = 0
        pages_with_artifacts = 0

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):

            try:

                raw_text = page.extract_text() or ""

            except Exception as exc:

                self.logger.warning(
                    "Unable to extract text from page %d of '%s': %s",
                    page_number,
                    self.filename,
                    exc,
                )

                continue

            if not raw_text.strip():
                continue

            pages_with_text += 1

            # Détection avant nettoyage pour les statistiques.
            raw_lines = raw_text.splitlines()

            artifact_count_before = sum(
                1
                for line in raw_lines
                if self._is_extraction_artifact(line)
            )

            if artifact_count_before > 0:
                pages_with_artifacts += 1

                self.logger.debug(
                    "Detected %d PDF extraction artifact(s) "
                    "on page %d of '%s'.",
                    artifact_count_before,
                    page_number,
                    self.filename,
                )

            # Nettoyage contrôlé.
            cleaned_text = self._clean_page_text(
                raw_text
            )

            if cleaned_text:
                pages.append(cleaned_text)

        # ==========================================================
        # Build content
        # ==========================================================

        content = "\n\n".join(pages)

        # ==========================================================
        # Empty document
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
                "content_length": len(content),
                "pages_count": len(reader.pages),
                "pages_with_text": pages_with_text,
                "pages_loaded": len(pages),
                "pages_with_artifacts": pages_with_artifacts,
                "pdf_metadata": (
                    dict(reader.metadata)
                    if reader.metadata
                    else {}
                ),
            }
        )

        # ==========================================================
        # Result
        # ==========================================================

        self.logger.info(
            "PDF file '%s' loaded successfully "
            "(%d/%d pages with readable content).",
            self.filename,
            len(pages),
            len(reader.pages),
        )

        return SourceDocument(
            source_name=self.filename,
            source_type="pdf",
            source_path=self.path,
            content=content,
            mime_type=self.mime_type,
            size=self.size,
            created_at=self.created_at,
            updated_at=self.modified_at,
            metadata=metadata,
        )


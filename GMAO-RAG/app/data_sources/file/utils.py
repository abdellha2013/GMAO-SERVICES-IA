"""
app/data_sources/file/utils.py
===============================

Description
-----------
Fonctions utilitaires pures et réutilisables par les loaders de
fichiers.

Ce module ne contient aucune logique métier propre à un format de
fichier particulier, et ne lève aucune exception `GMAOError` : il
fournit des briques bas niveau que les loaders assemblent dans leur
méthode `load()`. La validation (qui lève des exceptions) va dans
`validators.py`, pas ici.

Contenu
-------
- Détection d'encodage texte, mutualisée entre TXT/CSV/JSON/HTML/
  Markdown (jusqu'ici dupliquée à l'identique dans plusieurs loaders).
- Construction des métadonnées d'un SourceDocument à partir de
  FileSource.metadata(), en un seul appel `stat()`.
- Normalisation de texte extrait (espaces, lignes vides).
- Formatage d'une taille de fichier lisible pour les logs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from app.data_sources.file.file_source import FileSource

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_TEXT_ENCODINGS",
    "detect_text_encoding",
    "build_document_metadata",
    "normalize_whitespace",
    "human_readable_size",
]

# ==========================================================
# Encoding
# ==========================================================

DEFAULT_TEXT_ENCODINGS: Final[tuple[str, ...]] = (
    "utf-8",
    "utf-8-sig",
)


def detect_text_encoding(
    source: "FileSource",
    encodings: tuple[str, ...] = DEFAULT_TEXT_ENCODINGS,
    *,
    sample_only: bool = False,
    sample_size: int = 4096,
) -> str | None:
    """
    Essaie successivement plusieurs encodages sur un fichier texte.

    Mutualise la boucle de détection d'encodage jusqu'ici dupliquée
    à l'identique dans TXTLoader, CSVLoader, JSONLoader et
    HTMLLoader.

    Parameters
    ----------
    source:
        Instance de FileSource (ou sous-classe) à tester. Doit
        exposer `open_file()`.

    encodings:
        Encodages à essayer, dans l'ordre.

    sample_only:
        Si True, ne lit qu'un échantillon (`sample_size` caractères)
        au lieu du fichier entier. Plus rapide mais moins fiable :
        un fichier peut être valide sur l'échantillon et invalide
        plus loin dans le flux.

    sample_size:
        Taille de l'échantillon lu si `sample_only` est True.

    Returns
    -------
    str | None
        Le premier encodage qui permet une lecture complète sans
        erreur, ou None si aucun des encodages fournis ne
        fonctionne. Ce module reste neutre vis-à-vis des exceptions
        du projet : c'est à l'appelant de lever `InvalidEncodingError`
        si le résultat est None.
    """

    for encoding in encodings:
        try:
            with source.open_file(mode="r", encoding=encoding) as file:
                if sample_only:
                    file.read(sample_size)
                else:
                    file.read()

            return encoding

        except UnicodeDecodeError:
            logger.debug(
                "Encoding '%s' failed for '%s'.",
                encoding,
                source.filename,
            )
            continue

    return None


# ==========================================================
# Metadata
# ==========================================================

def build_document_metadata(
    source: "FileSource",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Construit le dictionnaire de métadonnées d'un SourceDocument.

    Fusionne les métadonnées génériques du fichier
    (`FileSource.metadata()`) avec les métadonnées propres au format
    (`extra`). Un seul appel à `metadata()` garantit un unique accès
    disque (`stat()`), évitant les appels `self.size` /
    `self.created_at` / `self.modified_at` redondants observés dans
    plusieurs loaders.

    Parameters
    ----------
    source:
        Instance de FileSource dont on veut les métadonnées de base.

    extra:
        Métadonnées supplémentaires spécifiques au format (encodage
        détecté, nombre de lignes, nombre de tableaux...).

    Returns
    -------
    dict[str, Any]
        Dictionnaire fusionné. Contient toujours au minimum "size",
        "created_at" et "modified_at", à réutiliser pour construire
        le SourceDocument plutôt que de rappeler les properties.
    """

    metadata = dict(source.metadata())

    if extra:
        collisions = set(metadata) & set(extra)

        if collisions:
            logger.warning(
                "Metadata keys overridden for '%s': %s.",
                source.filename,
                sorted(collisions),
            )

        metadata.update(extra)

    return metadata


# ==========================================================
# Text normalization
# ==========================================================

def normalize_whitespace(text: str) -> str:
    """
    Nettoie un bloc de texte extrait (HTML, DOCX, PDF...).

    - Réduit les espaces multiples à un seul espace, ligne par ligne.
    - Supprime les lignes vides résultantes.
    - Préserve les sauts de ligne significatifs entre blocs.

    Parameters
    ----------
    text:
        Texte brut à nettoyer.

    Returns
    -------
    str
        Texte nettoyé.
    """

    lines: list[str] = []

    for line in text.splitlines():
        cleaned = " ".join(line.split())

        if cleaned:
            lines.append(cleaned)

    return "\n".join(lines)


# ==========================================================
# Logging helpers
# ==========================================================

def human_readable_size(num_bytes: int) -> str:
    """
    Formate une taille en octets pour l'affichage dans les logs.

    Example
    -------
    >>> human_readable_size(1536)
    '1.5 KB'
    """

    size = float(num_bytes)

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"
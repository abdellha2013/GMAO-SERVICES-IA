"""
app/data_sources/file/validators.py
====================================

Description
-----------
Fonctions de validation réutilisables par les loaders de fichiers.

Contrairement à `utils.py`, ce module lève directement les exceptions
métier du projet (`app.exceptions`) : il encapsule des règles de
validation communes à plusieurs formats, pour éviter de les réécrire
dans chaque loader.

Convention
----------
Chaque fonction est nommée `ensure_*` : elle ne retourne rien en cas
de succès, et lève l'exception `GMAOError` appropriée en cas d'échec.
Les imports d'exceptions restent locaux à chaque fonction, comme
partout ailleurs dans le projet, pour rester cohérent avec le style
des loaders.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

__all__ = [
    "ensure_non_empty_content",
    "ensure_within_size_limit",
    "ensure_zip_based_format",
    "ensure_max_nesting_depth",
]


def ensure_non_empty_content(
    content: str,
    filename: str,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """
    Signale un contenu texte extrait vide ou uniquement composé
    d'espaces.

    Ce contrôle ne lève volontairement pas d'exception : un document
    structurellement valide mais sans contenu exploitable (ex: DOCX
    sans texte, HTML sans balises visibles) n'est pas une erreur du
    fichier lui-même, seulement un cas dégradé que le pipeline Parser
    doit pouvoir gérer plus loin. Seul un avertissement est journalisé.

    Parameters
    ----------
    content:
        Contenu extrait à vérifier.

    filename:
        Nom du fichier, pour le message de log.

    logger:
        Logger à utiliser. Si None, aucun log n'est émis.
    """

    if not content.strip() and logger is not None:
        logger.warning(
            "File '%s' contains no readable content.",
            filename,
        )


def ensure_within_size_limit(
    path: Path,
    max_bytes: int,
) -> None:
    """
    Vérifie qu'un fichier ne dépasse pas une taille maximale.

    Parameters
    ----------
    path:
        Chemin du fichier à vérifier.

    max_bytes:
        Taille maximale autorisée, en octets.

    Raises
    ------
    FileTooLargeError
        Si le fichier dépasse `max_bytes`.
    """

    from app.exceptions import FileTooLargeError

    size = path.stat().st_size

    if size > max_bytes:
        raise FileTooLargeError(
            message=(
                f"File '{path.name}' ({size} bytes) exceeds the "
                f"maximum allowed size ({max_bytes} bytes)."
            ),
            details={
                "path": str(path),
                "size": size,
                "max_bytes": max_bytes,
            },
        )


def ensure_zip_based_format(path: Path) -> None:
    """
    Vérifie qu'un fichier censé être un format Office Open XML
    (DOCX, XLSX, PPTX — tous basés sur ZIP) est bien un ZIP valide,
    avant de le confier à une librairie tierce (python-docx,
    openpyxl...).

    Permet de lever une exception cohérente avec la hiérarchie du
    projet, plutôt que de laisser remonter l'exception brute de la
    librairie tierce (`zipfile.BadZipFile`,
    `docx.opc.exceptions.PackageNotFoundError`...).

    Parameters
    ----------
    path:
        Chemin du fichier à vérifier.

    Raises
    ------
    CorruptedFileError
        Si le fichier n'est pas un ZIP valide.
    """

    from app.exceptions import CorruptedFileError

    if not zipfile.is_zipfile(path):
        raise CorruptedFileError(
            message=(
                f"File '{path.name}' is not a valid "
                f"Office Open XML (ZIP-based) document."
            ),
            details={"path": str(path)},
        )


def ensure_max_nesting_depth(
    value: Any,
    max_depth: int,
    filename: str,
) -> None:
    """
    Vérifie qu'une structure de données imbriquée (typiquement un
    JSON déjà chargé) ne dépasse pas une profondeur maximale.

    Protège contre un `RecursionError` non contrôlé sur un document
    généré par un tiers avec une imbrication artificiellement
    profonde.

    Parameters
    ----------
    value:
        Structure à vérifier (dict, list, ou valeur scalaire).

    max_depth:
        Profondeur maximale autorisée.

    filename:
        Nom du fichier, pour le message d'erreur.

    Raises
    ------
    JSONParsingError
        Si la profondeur maximale est dépassée.
    """

    from app.exceptions import JSONParsingError

    def _depth(node: Any, current: int) -> int:
        if current > max_depth:
            raise JSONParsingError(
                message=(
                    f"Structure in '{filename}' exceeds the maximum "
                    f"nesting depth ({max_depth})."
                ),
                details={"max_depth": max_depth},
            )

        if isinstance(node, dict):
            return max(
                (_depth(v, current + 1) for v in node.values()),
                default=current,
            )

        if isinstance(node, list):
            return max(
                (_depth(v, current + 1) for v in node),
                default=current,
            )

        return current

    _depth(value, 0)
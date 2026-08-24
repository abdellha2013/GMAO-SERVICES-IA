"""
app/data_sources/file/file_source.py
===================================

Description
-----------
Implémentation de la classe abstraite FileSource.

Cette classe fournit toutes les fonctionnalités communes aux
sources de données basées sur des fichiers :

- validation du fichier ;
- récupération des métadonnées ;
- accès aux propriétés du fichier ;
- journalisation ;
- gestion des erreurs.

Les loaders spécialisés (TXT, PDF, DOCX, CSV, etc.) héritent
de cette classe.
"""

from __future__ import annotations

import mimetypes
from abc import abstractmethod
from pathlib import Path
from os import stat_result
from typing import BinaryIO, TextIO, Mapping
from datetime import datetime, timezone

from app.data_sources.interfaces.base_source import BaseSource
from app.models.document import SourceDocument
from app.exceptions import (
    EmptyFileError,
    FilePermissionError,
    FileValidationError,
    GMAOError,
    MissingFileError,
)

UTC = timezone.utc


class FileSource(BaseSource[Path]):
    """
    Classe abstraite représentant une source de données basée
    sur un fichier.

    Parameters
    ----------
    source:
        Chemin du fichier à charger.
    """

    MAX_FILE_SIZE_BYTES: int = 200 * 1024 * 1024
    """
    Taille maximale autorisée pour un fichier source, en octets
    (200 Mo par défaut). Les sous-classes peuvent surcharger cette
    constante si un format nécessite une limite différente.
    """

    def __init__(self, source: str | Path) -> None:
        """
        Initialise une nouvelle source de fichier.
        """

        path = Path(source).expanduser().resolve()

        super().__init__(path)

        self._mime_type: str | None = None

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def path(self) -> Path:
        """
        Retourne le chemin absolu du fichier.
        """
        return self.source

    @property
    def filename(self) -> str:
        """
        Nom du fichier.
        """
        return self.path.name

    @property
    def stem(self) -> str:
        """
        Nom du fichier sans extension.
        """
        return self.path.stem

    @property
    def extension(self) -> str:
        """
        Extension du fichier.

        Exemple
        --------
        '.pdf'
        '.txt'
        """
        return self.path.suffix.lower()

    @property
    def parent_directory(self) -> Path:
        """
        Dossier contenant le fichier.
        """
        return self.path.parent

    @property
    def source_name(self) -> str:
        """
        Nom lisible de la source de fichier.
        """
        return self.filename

    @property
    def size(self) -> int:
        """
        Taille du fichier en octets.
        """
        return self._stat().st_size

    @property
    def created_at(self) -> datetime:
        """
        Date de création.

        Returns
        -------
        datetime
        """
        return datetime.fromtimestamp(self._stat().st_ctime, tz=UTC)

    @property
    def modified_at(self) -> datetime:
        """
        Date de dernière modification.

        Returns
        -------
        datetime
        """
        return datetime.fromtimestamp(self._stat().st_mtime, tz=UTC)

    @property
    def mime_type(self) -> str:
        """
        Type MIME du fichier.
        """

        if self._mime_type is None:
            mime, _ = mimetypes.guess_type(self.path)
            self._mime_type = mime or "application/octet-stream"

        return self._mime_type

    # ==========================================================
    # Validation
    # ==========================================================

    def validate(self) -> None:
        """
        Vérifie que le fichier est valide.

        Raises
        ------
        MissingFileError
            Le fichier n'existe pas.

        FileValidationError
            Le chemin n'est pas un fichier.

        FilePermissionError
            Permission insuffisante.

        EmptyFileError
            Le fichier est vide.

        FileTooLargeError
            Le fichier dépasse la taille maximale autorisée
            (``MAX_FILE_SIZE_BYTES``).
        """

        self.logger.debug(
            "Validating file '%s'.",
            self.path,
        )

        if not self.path.exists():
            raise MissingFileError(
                message=f"File '{self.path}' does not exist."
            )

        if not self.path.is_file():
            raise FileValidationError(
                message=f"'{self.path}' is not a file."
            )

        if not self.path.stat().st_size:
            raise EmptyFileError(
                message=f"File '{self.path}' is empty."
            )

        from app.data_sources.file.validators import (
            ensure_within_size_limit,
        )

        ensure_within_size_limit(
            self.path,
            self.MAX_FILE_SIZE_BYTES,
        )

        try:
            with self.path.open("rb"):
                pass

        except PermissionError as exc:
            raise FilePermissionError(
                message=f"Permission denied for '{self.path}'.",
                original=exc,
            ) from exc

    # ==========================================================
    # Abstract API
    # ==========================================================

    @abstractmethod
    def load(self) -> SourceDocument:
        """
        Charge le contenu du fichier.

        Cette méthode doit être implémentée par les classes
        dérivées.
        """
        raise NotImplementedError
        # ==========================================================
    # File Operations
    # ==========================================================

    def open_file(
        self,
        mode: str = "r",
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> BinaryIO | TextIO:
        """
        Ouvre le fichier de manière sécurisée.

        Parameters
        ----------
        mode:
            Mode d'ouverture.

        encoding:
            Encodage utilisé pour les fichiers texte.

        errors:
            Politique de gestion des erreurs d'encodage.

        Returns
        -------
        IO
            Objet fichier ouvert.

        Raises
        ------
        FilePermissionError
            Si le fichier ne peut pas être ouvert.
        """

        self.logger.debug(
            "Opening file '%s' (mode=%s).",
            self.path,
            mode,
        )

        try:
            if "b" in mode:
                return self.path.open(mode)

            return self.path.open(
                mode=mode,
                encoding=encoding,
                errors=errors,
            )

        except FileNotFoundError as exc:
            raise MissingFileError(
                message=f"File '{self.path}' does not exist."
            ).with_original(exc) from exc

        except PermissionError as exc:
            raise FilePermissionError(
                message=f"Permission denied for '{self.path}'.",
                original=exc,
            ) from exc

        except IsADirectoryError as exc:
            raise FileValidationError(
                message=f"'{self.path}' is a directory, not a file."
            ).with_original(exc) from exc

    # ==========================================================
    # Read Helpers
    # ==========================================================

    def read_text(
        self,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> str:
        """
        Lit complètement le fichier texte.

        Returns
        -------
        str
        """

        self.logger.debug(
            "Reading text file '%s'.",
            self.path,
        )

        with self.open_file(
            mode="r",
            encoding=encoding,
            errors=errors,
        ) as file:
            return file.read()

    def read_bytes(self) -> bytes:
        """
        Lit complètement le fichier en binaire.

        Returns
        -------
        bytes
        """

        self.logger.debug(
            "Reading binary file '%s'.",
            self.path,
        )

        with self.open_file("rb") as file:
            return file.read()

    def read_lines(
        self,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> list[str]:
        """
        Lit toutes les lignes du fichier.

        Returns
        -------
        list[str]
        """

        self.logger.debug(
            "Reading lines from '%s'.",
            self.path,
        )

        with self.open_file(
            mode="r",
            encoding=encoding,
            errors=errors,
        ) as file:
            return file.readlines()

    # ==========================================================
    # Validation Helpers
    # ==========================================================

    def has_extension(
        self,
        *extensions: str,
    ) -> bool:
        """
        Vérifie si le fichier possède une extension autorisée.

        Example
        -------
        >>> self.has_extension(".pdf")
        >>> self.has_extension(".txt", ".md")
        """

        normalized = {
            ext.lower()
            if ext.startswith(".")
            else f".{ext.lower()}"
            for ext in extensions
        }

        return self.extension in normalized

    def ensure_extension(
        self,
        *extensions: str,
    ) -> None:
        """
        Vérifie que l'extension est autorisée.

        Raises
        ------
        FileValidationError
        """

        if not self.has_extension(*extensions):
            raise FileValidationError(
                message=(
                    f"Unsupported extension "
                    f"'{self.extension}'. "
                    f"Expected: {', '.join(extensions)}."
                )
            )

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _stat(self) -> stat_result:
        """
        Récupère les métadonnées du fichier de manière sûre.

        En cas d'échec d'accès, on lève l'exception custom appropriée
        plutôt qu'un OSError brut, en distinguant les causes.

        Raises
        ------
        MissingFileError
            Le fichier n'existe pas.

        FilePermissionError
            Permission insuffisante pour accéder au fichier.

        FileValidationError
            Autre erreur d'accès (ex: chemin invalide).
        """

        try:
            return self.path.stat()
        except FileNotFoundError as exc:
            self.logger.exception("File not found during stat: %s", self.path)
            raise MissingFileError(
                message=f"File '{self.path}' does not exist."
            ).with_original(exc) from exc
        except PermissionError as exc:
            self.logger.exception("Permission denied during stat: %s", self.path)
            raise FilePermissionError(
                message=f"Permission denied for '{self.path}'.",
                original=exc,
            ) from exc
        except OSError as exc:
            self.logger.exception("OS error during stat: %s", self.path)
            raise FileValidationError(
                message=f"Unable to access file '{self.path}'."
            ).with_original(exc) from exc

    def _connect(self) -> None:
        """
        Vérifie que le fichier est accessible en lecture.

        Cette implémentation par défaut est générique et peut être
        surchargée par les sous-classes nécessitant un comportement
        de connexion spécifique.

        Raises
        ------
        MissingFileError
            Si le fichier n'existe pas.

        FilePermissionError
            Si les permissions de lecture sont insuffisantes.

        FileValidationError
            Si le fichier ne peut pas être ouvert.
        """

        self.logger.debug(
            "Connecting to file '%s'.",
            self.path,
        )

        try:
            with self.path.open("rb"):
                pass

        except FileNotFoundError as exc:
            raise MissingFileError(
                message=f"File '{self.path}' does not exist.",
                original=exc,
            ) from exc

        except PermissionError as exc:
            raise FilePermissionError(
                message=f"Permission denied for '{self.path}'.",
                original=exc,
            ) from exc

        except OSError as exc:
            raise FileValidationError(
                message=f"Unable to access file '{self.path}'.",
                original=exc,
            ) from exc
    
    def _close(self) -> None:
        """
        Fermeture par défaut d'une source de fichier.

        Aucun nettoyage spécifique n'est nécessaire car les opérations
        sur le fichier utilisent des context managers locaux.
        Les sous-classes peuvent surcharger cette méthode si besoin.
        """

        self.logger.debug(
            "Closing file source '%s' (no-op).",
            self.path,
        )

    # ==========================================================
    # Metadata Helpers
    # ==========================================================

    def metadata(self) -> Mapping[str, object]:
        """
        Retourne les métadonnées du fichier.

        Un seul appel système est effectué afin de garantir la
        cohérence des informations retournées et d'éviter des
        accès disque inutiles.

        Returns
        -------
        Mapping[str, object]
            Dictionnaire contenant les métadonnées du fichier.
        """

        stat = self._stat()

        return {
            "filename": self.filename,
            "stem": self.stem,
            "extension": self.extension,
            "mime_type": self.mime_type,
            "size": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime, tz=UTC),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            "parent_directory": str(self.parent_directory),
        }
    # ==========================================================
    # Representation
    # ==========================================================

    def __str__(self) -> str:
        """
        Représentation lisible.
        """

        return str(self.path)

    def __repr__(self) -> str:
        """
        Représentation utilisée pour le débogage.
        """

        return (
            f"{self.__class__.__name__}("
            f"path={str(self.path)!r}, "
            f"extension={self.extension!r}, "
            f"size={self.size})"
        )
        # ==========================================================
    # Additional Properties
    # ==========================================================

    @property
    def exists(self) -> bool:
        """
        Indique si le fichier existe.
        """
        return self.path.exists()

    @property
    def is_empty(self) -> bool:
        """
        Indique si le fichier est vide.

        Un fichier inaccessible (introuvable, permissions,
        chemin invalide) est considéré comme "vide" par
        convention pour ce test rapide.

        Returns
        -------
        bool
        """
        try:
            return self.size == 0
        except GMAOError:
            return True
    @property
    def is_readable(self) -> bool:
        """
        Vérifie si le fichier est accessible en lecture.

        Returns
        -------
        bool
        """
        try:
            with self.path.open("rb"):
                return True
        except OSError:
            return False

    # ==========================================================
    # Utility Methods
    # ==========================================================

    def refresh(self) -> None:
        """
        Réinitialise les métadonnées mises en cache.

        Cette méthode est utile si le fichier a été modifié
        après la création de l'objet.
        """
        self._mime_type = None

    # ==========================================================
    # Equality
    # ==========================================================

    # Note: cette redéfinition de __eq__ est volontaire.
    # Elle restreint la comparaison aux instances de FileSource
    # plutôt qu'à n'importe quelle BaseSource partageant la même source.
    def __eq__(self, other: object) -> bool:
        """
        Compare deux sources de fichiers.

        Deux FileSource sont considérées égales si elles
        pointent vers le même fichier.
        """
        if not isinstance(other, FileSource):
            return NotImplemented

        return self.path == other.path

    def __hash__(self) -> int:
        """
        Retourne le hash basé sur le chemin absolu.
        """
        return hash(self.path)


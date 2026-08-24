"""
app/exceptions/file.py
======================

Description
-----------
Définition des exceptions spécifiques aux fichiers.

Toutes les erreurs liées aux fichiers doivent hériter de
`FileError`, qui est le SEUL point d'entrée pour un
``except FileError`` générique dans la couche de chargement
(loading).

Hiérarchie
----------
Exception
    └── GMAOError
            └── DataSourceError
                    ├── ValidationError
                    │       └── FileError
                    │               ├── FileValidationError
                    │               │       ├── MissingFileError
                    │               │       ├── EmptyFileError
                    │               │       ├── UnsupportedFileFormatError
                    │               │       ├── FilePermissionError
                    │               │       └── FileTooLargeError
                    │               └── FileLoadingError  (aussi LoadingError, cf. note)
                    │                       ├── InvalidPDFError
                    │                       ├── InvalidDOCXError
                    │                       ├── InvalidXLSXError
                    │                       ├── CorruptedFileError
                    │                       ├── InvalidEncodingError
                    │                       ├── JSONParsingError
                    │                       └── HTMLParsingError
                    └── LoadingError
                            └── FileLoadingError  (voir ci-dessus)

Note importante — pourquoi ``FileLoadingError(FileError, LoadingError)``
--------------------------------------------------------------------
Dans la version d'origine, ``FileLoadingError`` héritait uniquement de
``LoadingError`` (et non de ``FileError``). Résultat : un
``except FileError`` posé dans le pipeline de loading ne capturait NI
``FileLoadingError`` NI aucune de ses 7 sous-classes (PDF, DOCX, XLSX,
fichier corrompu, encodage invalide, JSON/HTML malformés) — soit la
majorité des erreurs réellement rencontrées lors du chargement d'un
fichier. Ces exceptions remontaient alors comme de simples
``DataSourceError`` non catégorisées.

L'héritage multiple ci-dessous corrige ce problème tout en conservant
les deux usages utiles :

- ``except FileError`` → capture TOUTES les erreurs fichier (validation
  ET chargement) ;
- ``except LoadingError`` → capture toutes les erreurs de chargement,
  qu'elles viennent d'un fichier ou d'une base de données.
"""

from __future__ import annotations

from .data_source import (
    LoadingError,
    ValidationError,
)

__all__ = [
    "FileError",
    "FileValidationError",
    "FileLoadingError",
    "MissingFileError",
    "EmptyFileError",
    "UnsupportedFileFormatError",
    "CorruptedFileError",
    "FilePermissionError",
    "FileTooLargeError",
    "InvalidEncodingError",
    "JSONParsingError",
    "HTMLParsingError",
    "InvalidPDFError",
    "InvalidDOCXError",
    "InvalidXLSXError",
]


class FileError(ValidationError):
    """
    Exception de base pour TOUTES les erreurs liées aux fichiers.

    C'est la classe à utiliser dans un ``except`` générique de la
    couche loading : ``except FileError:`` capture aussi bien les
    fichiers introuvables/vides/trop volumineux (validation) que les
    fichiers corrompus ou illisibles (chargement).
    """

    DEFAULT_MESSAGE = "A file error has occurred."
    DEFAULT_ERROR_CODE = "FILE_ERROR"
    DEFAULT_HTTP_STATUS = 400
    DEFAULT_RETRYABLE = False


class FileValidationError(FileError):
    """
    Le fichier est invalide avant même toute tentative de lecture.
    """

    DEFAULT_MESSAGE = "The file validation failed."
    DEFAULT_ERROR_CODE = "FILE_VALIDATION_ERROR"


class FileLoadingError(FileError, LoadingError):
    """
    Impossible de lire ou d'interpréter le contenu du fichier.

    Hérite à la fois de :

    - ``FileError`` → pour rester attrapable par un ``except
      FileError`` générique ;
    - ``LoadingError`` → pour rester attrapable par un ``except
      LoadingError`` générique (transversal à toutes les sources).
    """

    DEFAULT_MESSAGE = "Unable to load the file."
    DEFAULT_ERROR_CODE = "FILE_LOADING_ERROR"


class InvalidPDFError(FileLoadingError):
    """
    Exception levée lorsqu'un fichier PDF n'est pas
    un document PDF valide.

    Cela se produit notamment lorsque :

    - le fichier est corrompu ;
    - le fichier n'est pas un PDF valide ;
    - la structure interne du PDF est invalide.
    """

    DEFAULT_MESSAGE = "The PDF file is not a valid PDF document."
    DEFAULT_ERROR_CODE = "INVALID_PDF"


class InvalidDOCXError(FileLoadingError):
    """
    Exception levée lorsqu'un fichier DOCX n'est pas
    un document Microsoft Word valide.

    Cela se produit notamment lorsque :

    - le fichier est corrompu ;
    - le fichier n'est pas une archive ZIP valide ;
    - un fichier texte est renommé en .docx.
    """

    DEFAULT_MESSAGE = "The DOCX file is not a valid Microsoft Word document."
    DEFAULT_ERROR_CODE = "INVALID_DOCX"


class InvalidXLSXError(FileLoadingError):
    """
    Exception levée lorsqu'un fichier XLSX n'est pas
    un document Microsoft Excel valide.

    Cela se produit notamment lorsque :

    - le fichier est corrompu ;
    - le fichier n'est pas une archive ZIP valide ;
    - la structure interne du classeur est invalide.
    """

    DEFAULT_MESSAGE = "The XLSX file is not a valid Microsoft Excel workbook."
    DEFAULT_ERROR_CODE = "INVALID_XLSX"


class MissingFileError(FileValidationError):
    """
    Le fichier demandé est introuvable.

    Renommée depuis ``FileNotFoundError`` : ce nom masquait le builtin
    Python ``FileNotFoundError`` levé par ``open()``/``pathlib`` en cas
    d'erreur OS réelle. Après un ``from app.exceptions import
    FileNotFoundError``, un ``except FileNotFoundError`` ne capturait
    plus les vraies erreurs disque, seulement celle du projet — un bug
    silencieux particulièrement dangereux.
    """

    DEFAULT_MESSAGE = "The specified file was not found."
    DEFAULT_ERROR_CODE = "FILE_NOT_FOUND"
    DEFAULT_HTTP_STATUS = 404


class EmptyFileError(FileValidationError):
    """
    Le fichier est vide.
    """

    DEFAULT_MESSAGE = "The file is empty."
    DEFAULT_ERROR_CODE = "FILE_EMPTY"


class UnsupportedFileFormatError(FileValidationError):
    """
    Format de fichier non supporté.
    """

    DEFAULT_MESSAGE = "Unsupported file format."
    DEFAULT_ERROR_CODE = "FILE_UNSUPPORTED_FORMAT"


class CorruptedFileError(FileLoadingError):
    """
    Le fichier est corrompu ou illisible.
    """

    DEFAULT_MESSAGE = "The file is corrupted or unreadable."
    DEFAULT_ERROR_CODE = "FILE_CORRUPTED"
    DEFAULT_HTTP_STATUS = 400
    DEFAULT_RETRYABLE = False


class FilePermissionError(FileValidationError):
    """
    Permissions insuffisantes pour accéder au fichier.
    """

    DEFAULT_MESSAGE = "Permission denied while accessing the file."
    DEFAULT_ERROR_CODE = "FILE_PERMISSION_DENIED"
    DEFAULT_HTTP_STATUS = 403


class FileTooLargeError(FileValidationError):
    """
    Le fichier dépasse la taille maximale autorisée.
    """

    DEFAULT_MESSAGE = "The file exceeds the maximum allowed size."
    DEFAULT_ERROR_CODE = "FILE_TOO_LARGE"
    DEFAULT_HTTP_STATUS = 413


class InvalidEncodingError(FileLoadingError):
    """
    Encodage du fichier invalide.
    """

    DEFAULT_MESSAGE = "The file encoding is invalid or unsupported."
    DEFAULT_ERROR_CODE = "FILE_INVALID_ENCODING"
    DEFAULT_HTTP_STATUS = 400
    DEFAULT_RETRYABLE = False


class JSONParsingError(FileLoadingError):
    """
    Le contenu JSON est invalide ou malformé.
    """

    DEFAULT_MESSAGE = "The JSON content could not be parsed."
    DEFAULT_ERROR_CODE = "JSON_PARSING_ERROR"
    DEFAULT_HTTP_STATUS = 400
    DEFAULT_RETRYABLE = False


class HTMLParsingError(FileLoadingError):
    """
    Le contenu HTML est invalide ou ne peut pas être analysé.
    """

    DEFAULT_MESSAGE = "The HTML content could not be parsed."
    DEFAULT_ERROR_CODE = "HTML_PARSING_ERROR"
    DEFAULT_HTTP_STATUS = 400
    DEFAULT_RETRYABLE = False

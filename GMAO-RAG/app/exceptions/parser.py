"""
app/exceptions/parser.py
=========================

Exceptions spécifiques à la couche Parser.

Ce module définit la hiérarchie d'exceptions utilisée par le pipeline
de parsing. Toutes les exceptions héritent de ``GMAOError`` afin de
conserver un mécanisme d'erreur homogène dans toute l'application.

Hiérarchie
----------

GMAOError
└── ParserError
    ├── ParserValidationError
    ├── InvalidStrategyError
    ├── ParserStrategyNotRegisteredError
    ├── UnsupportedSourceTypeError
    ├── ParserExecutionError
    ├── EmptyDocumentError
    └── ParsedDocumentError

Note sur cette version corrigée
--------------------------------
La version d'origine réimplémentait un ``__init__`` quasi identique
dans CHAQUE sous-classe (message/details/original), sans jamais fixer
``error_code`` ni ``http_status``. Conséquence concrète : à la
différence des exceptions de ``data_source``/``file``/``database``,
toutes les erreurs de parsing ressortaient de ``to_dict()`` avec
``error_code=None`` et ``http_status=None`` — inutilisable telles
quelles pour une réponse API ou un log structuré, et incohérent avec
le reste du pipeline (loading → parsing → chunking).

On reprend ici le même pattern ``DEFAULT_MESSAGE`` /
``DEFAULT_ERROR_CODE`` / ``DEFAULT_HTTP_STATUS`` que
``DataSourceError``, avec un unique ``__init__`` factorisé dans
``ParserError``. Cela élimine la duplication, garantit un
``error_code``/``http_status`` cohérent partout, et permet toujours de
les surcharger ponctuellement via des kwargs si besoin
(``ParserExecutionError("...", http_status=500)``).
"""

from __future__ import annotations

from .base_exception import GMAOError

__all__ = [
    "ParserError",
    "ParserValidationError",
    "InvalidStrategyError",
    "ParserStrategyNotRegisteredError",
    "UnsupportedSourceTypeError",
    "ParserExecutionError",
    "EmptyDocumentError",
    "ParsedDocumentError",
]


class ParserError(GMAOError):
    """
    Exception de base pour toutes les erreurs de la couche Parser.

    Cette exception permet aux couches supérieures de capturer toutes
    les erreurs liées au parsing avec un seul ``except ParserError``.
    """

    DEFAULT_MESSAGE = "An error occurred in the parser layer."
    DEFAULT_ERROR_CODE = "PARSER_ERROR"
    DEFAULT_HTTP_STATUS = 422
    DEFAULT_RETRYABLE = False

    def __init__(
        self,
        message: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop(
                "error_code",
                self.DEFAULT_ERROR_CODE,
            ),
            http_status=kwargs.pop(
                "http_status",
                self.DEFAULT_HTTP_STATUS,
            ),
            **kwargs,
        )


class ParserValidationError(ParserError):
    """
    Levée lorsqu'une donnée d'entrée du Parser est invalide.

    Exemples
    --------
    - ``source_document`` invalide ou absent ;
    - ``source_type`` vide ;
    - configuration du Parser invalide ;
    - résultat de parsing incohérent ;
    - paramètre incompatible avec la stratégie sélectionnée.
    """

    DEFAULT_MESSAGE = "Invalid parser input or configuration."
    DEFAULT_ERROR_CODE = "PARSER_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class InvalidStrategyError(ParserError):
    """
    Levée lorsqu'une stratégie de parsing n'est pas valide.

    Exemples
    --------
    - objet qui n'est pas une classe ;
    - classe qui n'hérite pas de ``ParserStrategy`` ;
    - stratégie incompatible avec le contrat du Parser ;
    - stratégie instanciable mais mal configurée.
    """

    DEFAULT_MESSAGE = "Invalid parser strategy."
    DEFAULT_ERROR_CODE = "PARSER_INVALID_STRATEGY"
    DEFAULT_HTTP_STATUS = 500


class ParserStrategyNotRegisteredError(ParserError):
    """
    Levée lorsqu'aucune stratégie n'est enregistrée pour une source.

    Cette exception remplace notamment ``KeyError`` lorsqu'un appel à
    ``ParserRegistry.get()`` ou ``unregister()`` vise un ``source_type``
    inconnu.
    """

    DEFAULT_MESSAGE = (
        "No parser strategy is registered for the requested source type."
    )
    DEFAULT_ERROR_CODE = "PARSER_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 500


class UnsupportedSourceTypeError(ParserError):
    """
    Levée lorsqu'un ``source_type`` est valide mais non supporté.

    Différence avec ``ParserStrategyNotRegisteredError``
    ------------------------------------------------------
    ``ParserStrategyNotRegisteredError`` concerne principalement le
    registre.

    ``UnsupportedSourceTypeError`` concerne le Parser lorsqu'il reçoit
    une source dont le type ne possède aucune stratégie de parsing
    disponible.

    Exemple
    -------
    ``source_type="unknown"``
    """

    DEFAULT_MESSAGE = "The source type is not supported by the parser."
    DEFAULT_ERROR_CODE = "PARSER_UNSUPPORTED_SOURCE_TYPE"
    DEFAULT_HTTP_STATUS = 400


class ParserExecutionError(ParserError):
    """
    Levée lorsqu'une stratégie échoue pendant l'exécution du parsing.

    Cette exception sert à encapsuler les erreurs techniques provenant
    d'une bibliothèque externe ou d'une stratégie interne.

    Exemples
    --------
    - erreur lors du parsing HTML ;
    - erreur de décodage ;
    - erreur de lecture d'une structure ;
    - erreur inattendue dans une stratégie.

    L'exception originale peut être conservée dans ``original`` (ou via
    ``raise ... from original_exc``) sans exposer d'informations
    sensibles dans le message public.
    """

    DEFAULT_MESSAGE = "Parser execution failed."
    DEFAULT_ERROR_CODE = "PARSER_EXECUTION_ERROR"
    DEFAULT_HTTP_STATUS = 422


class EmptyDocumentError(ParserError):
    """
    Levée lorsqu'un document ne contient aucun contenu exploitable.

    Cette exception permet de distinguer un document réellement vide
    d'une erreur technique de parsing.

    Exemples
    --------
    - ``content == ""`` ;
    - contenu composé uniquement d'espaces ;
    - document dont le parsing produit un résultat vide.
    """

    DEFAULT_MESSAGE = "The document contains no parseable content."
    DEFAULT_ERROR_CODE = "PARSER_EMPTY_DOCUMENT"
    DEFAULT_HTTP_STATUS = 422


class ParsedDocumentError(ParserError):
    """
    Levée lorsqu'un résultat de parsing est invalide ou incohérent.

    Cette exception concerne la sortie du Parser plutôt que son entrée.

    Exemples
    --------
    - résultat ``ParsedDocument`` mal formé ;
    - contenu parsé absent alors qu'il est obligatoire ;
    - métadonnées incompatibles ;
    - structure de sortie incohérente ;
    - résultat impossible à transmettre au futur Chunker.
    """

    DEFAULT_MESSAGE = "The parser produced an invalid parsed document."
    DEFAULT_ERROR_CODE = "PARSER_INVALID_OUTPUT"
    DEFAULT_HTTP_STATUS = 500

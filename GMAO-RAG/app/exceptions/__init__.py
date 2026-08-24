"""
app/exceptions/__init__.py
==========================

Exceptions publiques du projet GMAO AI Service.

Ce module centralise toutes les exceptions personnalisées afin
de simplifier leur import dans le reste du projet.

Exemple
-------
Au lieu de :

    from app.exceptions.file import MissingFileError

on peut simplement écrire :

    from app.exceptions import MissingFileError
"""

from __future__ import annotations

from .base_exception import GMAOError

from .data_source import (
    AuthenticationError,
    CloseError,
    ConfigurationError,
    DataConnectionError,
    DataSourceError,
    LoadingError,
    PermissionDeniedError,
    UnsupportedSourceError,
    ValidationError,
)
from .file import (
    CorruptedFileError,
    EmptyFileError,
    FileError,
    FileLoadingError,
    FilePermissionError,
    FileTooLargeError,
    FileValidationError,
    HTMLParsingError,
    InvalidDOCXError,
    InvalidEncodingError,
    InvalidPDFError,
    InvalidXLSXError,
    JSONParsingError,
    MissingFileError,
    UnsupportedFileFormatError,
)
from .database import (
    DatabaseAuthenticationError,
    DatabaseConnectionError,
    DatabaseError,
    DatabaseLoadingError,
    DatabaseNotFoundError,
    DatabasePermissionError,
    DatabaseTimeoutError,
    DatabaseValidationError,
    DuplicateKeyError,
    EmptyResultError,
    ForeignKeyError,
    QueryExecutionError,
    TableNotFoundError,
    TransactionError,
)
from .parser import (
    EmptyDocumentError,
    InvalidStrategyError,
    ParsedDocumentError,
    ParserError,
    ParserExecutionError,
    ParserStrategyNotRegisteredError,
    ParserValidationError,
    UnsupportedSourceTypeError,
)
from .chunker import (
    ChunkerError,
    ChunkerValidationError,
    ChunkerStrategyNotRegisteredError,
    ChunkingError,
    ChunkSizeError,
    EmptyChunkError,
    InvalidChunkerStrategyError,
)
from .embedding import (
    EmbeddingEncodingError,
    EmbeddingError,
    EmbeddingModelError,
    EmbeddingStrategyNotRegisteredError,
    EmbeddingValidationError,
    InvalidEmbeddingStrategyError,
)
from .storage import (StorageError, StorageValidationError, StorageAlignmentError,
    InvalidStorageStrategyError, StorageStrategyNotRegisteredError,
    StorageConnectionError, StorageWriteError, PartialStorageError)
from .retrieval import (RetrievalError, RetrievalValidationError, EmptyQueryError,
    InvalidRetrievalStrategyError, RetrievalStrategyNotRegisteredError,
    RetrievalConnectionError, RetrievalExecutionError, IncompatibleEmbeddingModelError)
from .reranker import (RerankerError, RerankerValidationError,
    RerankerModelError, RerankingError, RerankerStrategyNotRegisteredError,
    InvalidRerankerStrategyError)
from .llm import (LLMError, LLMValidationError, LLMConnectionError,
    LLMRateLimitError, LLMModelError, LLMGenerationError, LLMStrategyNotRegisteredError,
    InvalidLLMStrategyError)




__all__ = [
    # Base
    "GMAOError",

    # Data Source
    "DataSourceError",
    "ValidationError",
    "ConfigurationError",
    "DataConnectionError",
    "AuthenticationError",
    "PermissionDeniedError",
    "LoadingError",
    "CloseError",
    "UnsupportedSourceError",

    # File
    "InvalidXLSXError",
    "FileError",
    "InvalidDOCXError",
    "FileValidationError",
    "FileLoadingError",
    "InvalidPDFError",
    "MissingFileError",
    "EmptyFileError",
    "UnsupportedFileFormatError",
    "CorruptedFileError",
    "FilePermissionError",
    "FileTooLargeError",
    "InvalidEncodingError",
    "JSONParsingError",
    "HTMLParsingError",

    # Database
    "DatabaseError",
    "DatabaseValidationError",
    "DatabaseConnectionError",
    "DatabaseAuthenticationError",
    "DatabasePermissionError",
    "DatabaseTimeoutError",
    "DatabaseLoadingError",
    "DatabaseNotFoundError",
    "QueryExecutionError",
    "DuplicateKeyError",
    "ForeignKeyError",
    "TableNotFoundError",
    "EmptyResultError",
    "TransactionError",

    # Parser
    "ParserError",
    "ParserValidationError",
    "InvalidStrategyError",
    "ParserStrategyNotRegisteredError",
    "UnsupportedSourceTypeError",
    "ParserExecutionError",
    "EmptyDocumentError",
    "ParsedDocumentError",

    # Chunker
    "ChunkerError",
    "ChunkerValidationError",
    "InvalidChunkerStrategyError",
    "ChunkerStrategyNotRegisteredError",
    "ChunkingError",
    "EmptyChunkError",
    "ChunkSizeError",

    # Embedding
    "EmbeddingError",
    "EmbeddingValidationError",
    "EmbeddingModelError",
    "EmbeddingStrategyNotRegisteredError",
    "EmbeddingEncodingError",
    "InvalidEmbeddingStrategyError",
    "StorageError", "StorageValidationError", "StorageAlignmentError",
    "InvalidStorageStrategyError", "StorageStrategyNotRegisteredError",
    "StorageConnectionError", "StorageWriteError", "PartialStorageError",
    "RetrievalError", "RetrievalValidationError", "EmptyQueryError",
    "InvalidRetrievalStrategyError", "RetrievalStrategyNotRegisteredError",
    "RetrievalConnectionError", "RetrievalExecutionError", "IncompatibleEmbeddingModelError",
    # Reranker
    "RerankerError", "RerankerValidationError", "RerankerModelError",
    "RerankingError", "RerankerStrategyNotRegisteredError",
    "InvalidRerankerStrategyError",
    # LLM
    "LLMError", "LLMValidationError", "LLMConnectionError",
    "LLMRateLimitError", "LLMModelError", "LLMGenerationError",
    "LLMStrategyNotRegisteredError", "InvalidLLMStrategyError",
]


# ==================================================================
# Lazy-loading fallback (PEP 562)
# ==================================================================
# Tous les noms de __all__ sont déjà importés (et donc déjà présents
# dans globals()) au moment où ce module est chargé. __getattr__
# n'est donc appelé par Python QUE pour un nom absent de globals(),
# c'est-à-dire un nom invalide. Ce mécanisme est conservé tel quel
# (utile si de futurs imports passent en lazy) mais corrigé :
# - la clé "chunker" manquait entièrement ;
# - "StrategyNotRegisteredError" ne correspondait à aucune classe
#   réellement définie dans parser.py (le vrai nom est
#   "ParserStrategyNotRegisteredError") : ce nom ne pouvait donc
#   jamais être résolu.
_SUBMODULES: dict[str, tuple[str, ...]] = {
    "data_source": (
        "DataSourceError",
        "ValidationError",
        "ConfigurationError",
        "DataConnectionError",
        "AuthenticationError",
        "PermissionDeniedError",
        "LoadingError",
        "CloseError",
        "UnsupportedSourceError",
    ),
    "file": (
        "InvalidXLSXError",
        "InvalidDOCXError",
        "FileError",
        "InvalidPDFError",
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
    ),
    "database": (
        "DatabaseError",
        "DatabaseValidationError",
        "DatabaseConnectionError",
        "DatabaseAuthenticationError",
        "DatabasePermissionError",
        "DatabaseTimeoutError",
        "DatabaseLoadingError",
        "DatabaseNotFoundError",
        "QueryExecutionError",
        "DuplicateKeyError",
        "ForeignKeyError",
        "TableNotFoundError",
        "EmptyResultError",
        "TransactionError",
    ),
    "parser": (
        "ParserError",
        "ParserValidationError",
        "InvalidStrategyError",
        "ParserStrategyNotRegisteredError",
        "UnsupportedSourceTypeError",
        "ParserExecutionError",
        "EmptyDocumentError",
        "ParsedDocumentError",
    ),
    "chunker": (
        "ChunkerError",
        "ChunkerValidationError",
        "InvalidChunkerStrategyError",
        "ChunkerStrategyNotRegisteredError",
        "ChunkingError",
        "EmptyChunkError",
        "ChunkSizeError",
    ),
    "embedding": (
        "EmbeddingError",
        "EmbeddingValidationError",
        "EmbeddingModelError",
        "EmbeddingStrategyNotRegisteredError",
        "EmbeddingEncodingError",
        "InvalidEmbeddingStrategyError",
    ),
    "storage": ("StorageError", "StorageValidationError", "StorageAlignmentError",
        "InvalidStorageStrategyError", "StorageStrategyNotRegisteredError",
        "StorageConnectionError", "StorageWriteError", "PartialStorageError"),
    "retrieval": ("RetrievalError", "RetrievalValidationError", "EmptyQueryError",
        "InvalidRetrievalStrategyError", "RetrievalStrategyNotRegisteredError",
        "RetrievalConnectionError", "RetrievalExecutionError", "IncompatibleEmbeddingModelError"),
    "reranker": ("RerankerError", "RerankerValidationError", "RerankerModelError",
        "RerankingError", "RerankerStrategyNotRegisteredError",
        "InvalidRerankerStrategyError"),
    "llm": ("LLMError", "LLMValidationError", "LLMConnectionError",
        "LLMRateLimitError", "LLMModelError", "LLMGenerationError",
        "LLMStrategyNotRegisteredError", "InvalidLLMStrategyError"),
}


def __getattr__(name: str):
    for module_name, names in _SUBMODULES.items():
        if name in names:
            module = __import__(
                f"{__name__}.{module_name}",
                fromlist=[name],
            )
            return getattr(module, name)

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


def __dir__() -> list[str]:
    return sorted(
        __all__ + list(globals().keys())
    )

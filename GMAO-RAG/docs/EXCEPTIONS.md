# Référence — Module `app.exceptions`

> **Objectif de ce document** : servir de référence unique et autosuffisante
> sur la hiérarchie d'exceptions du projet **RAG-GMAO**, pour :
> - les développeurs humains (comprendre quoi lever, quoi catcher) ;
> - les assistants IA / chatbots générant ou relisant du code sur ce
>   projet, **sans avoir besoin de relire les 12 fichiers source** à
>   chaque fois.
>
> Version documentée : v3 (ajout embedding/storage/retrieval/reranker/llm
> — voir section [Changelog](#changelog--historique-des-corrections)).

---

## 1. Vue d'ensemble

Le module `app/exceptions/` centralise **toutes** les exceptions
métier du pipeline RAG-GMAO (`loading → parsing → chunking → embedding
→ storage → retrieval → reranking → llm`). Il est composé de 12 fichiers :

| Fichier | Rôle |
|---|---|
| `base_exception.py` | Classe racine `GMAOError` (structure commune, sérialisation) |
| `data_source.py` | Erreurs génériques de source de données (base pour file & database) |
| `file.py` | Erreurs spécifiques aux fichiers (PDF, DOCX, XLSX, JSON, HTML...) |
| `database.py` | Erreurs spécifiques aux bases de données |
| `parser.py` | Erreurs de l'étage **parsing** du pipeline |
| `chunker.py` | Erreurs de l'étage **chunking** du pipeline |
| `embedding.py` | Erreurs de l'étage **embedding** du pipeline |
| `storage.py` | Erreurs de l'étage **storage** du pipeline |
| `retrieval.py` | Erreurs de l'étage **retrieval** du pipeline |
| `reranker.py` | Erreurs de l'étage **reranker** du pipeline |
| `llm.py` | Erreurs de l'étage **LLM** du pipeline |
| `__init__.py` | Point d'entrée unique : `from app.exceptions import ...` |

### Règle d'or

> **Toute exception métier du projet DOIT hériter de `GMAOError`.**
> Ne jamais lever une exception builtin nue (`ValueError`,
> `Exception`...) dans le code applicatif — toujours passer par une
> sous-classe de `GMAOError`, ou en créer une nouvelle si rien
> n'existe (voir [§8](#8-comment-ajouter-une-nouvelle-exception)).
>
> **Exception** : les erreurs de contrat détectées à la définition de
> classe (`__init_subclass__`) lèvent une sous-classe de `GMAOError`
> dédiée (ex. `InvalidRetrievalStrategyError`), pas un `TypeError` nu.
> Cela permet de catcher ces erreurs proprement si nécessaire, tout en
> conservant le comportement « échoue au chargement du module ».

---

## 2. Arbre d'héritage complet

```
Exception
└── GMAOError                                  (base_exception.py)
    │
    ├── DataSourceError                        (data_source.py)
    │   ├── ValidationError
    │   │   └── FileError                       (file.py)
    │   │       ├── FileValidationError
    │   │       │   ├── MissingFileError
    │   │       │   ├── EmptyFileError
    │   │       │   ├── UnsupportedFileFormatError
    │   │       │   ├── FilePermissionError
    │   │       │   └── FileTooLargeError
    │   │       └── FileLoadingError  ★ hérite AUSSI de LoadingError
    │   │           ├── InvalidPDFError
    │   │           ├── InvalidDOCXError
    │   │           ├── InvalidXLSXError
    │   │           ├── CorruptedFileError
    │   │           ├── InvalidEncodingError
    │   │           ├── JSONParsingError
    │   │           └── HTMLParsingError
    │   │
    │   ├── ConfigurationError
    │   ├── DataConnectionError
    │   │   ├── AuthenticationError
    │   │   └── PermissionDeniedError
    │   ├── LoadingError
    │   │   ├── FileLoadingError  ★ (voir ci-dessus, double héritage)
    │   │   └── DatabaseLoadingError            (database.py)
    │   │       ├── QueryExecutionError
    │   │       ├── TableNotFoundError
    │   │       ├── EmptyResultError
    │   │       ├── DuplicateKeyError
    │   │       └── ForeignKeyError
    │   ├── CloseError
    │   ├── UnsupportedSourceError
    │   │
    │   └── DatabaseError                       (database.py)
    │       ├── DatabaseValidationError
    │       ├── DatabaseConnectionError (hérite de DataConnectionError)
    │       │   ├── DatabaseAuthenticationError
    │       │   ├── DatabasePermissionError
    │       │   ├── DatabaseTimeoutError
    │       │   └── DatabaseNotFoundError
    │       └── TransactionError
    │
    ├── ParserError                             (parser.py)
    │   ├── ParserValidationError
    │   ├── InvalidStrategyError
    │   ├── ParserStrategyNotRegisteredError
    │   ├── UnsupportedSourceTypeError
    │   ├── ParserExecutionError
    │   ├── EmptyDocumentError
    │   └── ParsedDocumentError
    │
    └── ChunkerError                            (chunker.py)
        ├── ChunkerValidationError
        │   └── ChunkSizeError
        ├── InvalidChunkerStrategyError
        ├── ChunkerStrategyNotRegisteredError
        ├── ChunkingError
        └── EmptyChunkError

    ├── EmbeddingError                        (embedding.py)
    │   ├── EmbeddingValidationError
    │   ├── InvalidEmbeddingStrategyError
    │   ├── EmbeddingStrategyNotRegisteredError
    │   ├── EmbeddingExecutionError
    │   └── IncompatibleEmbeddingModelError
    │
    ├── StorageError                          (storage.py)
    │   ├── StorageValidationError
    │   ├── StorageAlignmentError
    │   ├── InvalidStorageStrategyError
    │   ├── StorageStrategyNotRegisteredError
    │   ├── StorageConnectionError
    │   ├── StorageWriteError
    │   └── PartialStorageError
    │
    ├── RetrievalError                        (retrieval.py)
    │   ├── RetrievalValidationError
    │   │   └── EmptyQueryError
    │   ├── InvalidRetrievalStrategyError
    │   ├── RetrievalStrategyNotRegisteredError
    │   ├── RetrievalConnectionError
    │   ├── RetrievalExecutionError
    │   └── IncompatibleEmbeddingModelError
    │
    ├── RerankerError                         (reranker.py)
    │   ├── RerankerValidationError
    │   ├── RerankerModelError
    │   ├── RerankingError
    │   ├── RerankerStrategyNotRegisteredError
    │   └── InvalidRerankerStrategyError
    │
    └── LLMError                              (llm.py)
        ├── LLMValidationError
        ├── LLMConnectionError
        ├── LLMRateLimitError
        ├── LLMModelError
        ├── LLMGenerationError
        ├── LLMStrategyNotRegisteredError
        └── InvalidLLMStrategyError
```

> ★ **Point important** : `FileLoadingError` hérite à la fois de
> `FileError` et de `LoadingError` (héritage multiple). Cela permet
> deux usages complémentaires :
> - `except FileError:` → capture **toutes** les erreurs fichier
>   (validation ET chargement) ;
> - `except LoadingError:` → capture toutes les erreurs de
>   chargement, qu'elles viennent d'un fichier ou d'une base de
>   données (utile pour un handler générique à l'étage *loading* du
>   pipeline).

---

## 3. La classe racine : `GMAOError`

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class GMAOError(Exception):
    message: str
    error_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    original: Exception | None = None
    http_status: int | None = None
```

| Membre | Type | Description |
|---|---|---|
| `message` | `str` | Message lisible (obligatoire, non vide). |
| `error_code` | `str \| None` | Code métier stable, ex. `"FILE_NOT_FOUND"`. Utilisé pour le routage d'erreurs côté API/logs. |
| `details` | `dict[str, Any]` | Infos techniques complémentaires (jamais de secrets). Toujours un `dict`, jamais `None` (garanti par `__post_init__`). |
| `original` | `Exception \| None` | Exception d'origine capturée manuellement via `.with_original(exc)`. |
| `http_status` | `int \| None` | Code HTTP à renvoyer si l'erreur remonte jusqu'à une API. |
| `has_details` (property) | `bool` | `True` si `details` n'est pas vide. |
| `cause` (property) | `Exception \| None` | Retourne `original` s'il existe, sinon retombe sur `__cause__`/`__context__` (posés par `raise ... from ...`). |
| `to_dict()` | `dict` | Représentation JSON-sérialisable, prête pour une réponse API ou un log structuré. |
| `with_original(exc)` | `GMAOError` | Retourne une **nouvelle** instance (l'objet est immuable/`frozen`) avec `original=exc`. |

**Immutabilité** : `GMAOError` est un dataclass `frozen=True`. On ne
peut **pas** faire `exc.details["x"] = 1` après coup — utiliser
`exc.with_original(...)` ou construire l'exception avec les bons
paramètres dès le départ.

---

## 4. Convention `DEFAULT_*` (à connaître avant de lever une exception)

Toutes les exceptions concrètes (hors `GMAOError` lui-même) suivent le
**même pattern** dans les 3 couches (`DataSourceError`, `ParserError`,
`ChunkerError`) :

```python
class MaFamilleError(GMAOError):
    DEFAULT_MESSAGE = "Message par défaut."
    DEFAULT_ERROR_CODE = "MON_CODE"
    DEFAULT_HTTP_STATUS = 400

    def __init__(self, message=None, **kwargs):
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop("error_code", self.DEFAULT_ERROR_CODE),
            http_status=kwargs.pop("http_status", self.DEFAULT_HTTP_STATUS),
            **kwargs,
        )
```

Conséquences pratiques :

- **On peut lever une exception sans argument** : `raise MissingFileError()`
  → utilise `DEFAULT_MESSAGE`/`DEFAULT_ERROR_CODE`/`DEFAULT_HTTP_STATUS`
  de la classe.
- **On peut personnaliser le message** : `raise MissingFileError("rapport_2024.pdf introuvable")`.
- **On peut surcharger le code/status ponctuellement** :
  `raise MissingFileError(http_status=410)`.
- **Chaque sous-classe hérite des `DEFAULT_*` de son parent** si elle
  ne les redéfinit pas. Toujours redéfinir au moins `DEFAULT_MESSAGE`
  et `DEFAULT_ERROR_CODE` pour toute nouvelle exception concrète.

---

## 5. Table de référence complète (toutes les exceptions)

### 5.1 Data Source (`data_source.py`)

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `DataSourceError` | `GMAOError` | `DATA_SOURCE_ERROR` | 500 | Base générique, ne pas lever directement en général |
| `ValidationError` | `DataSourceError` | `DATA_SOURCE_VALIDATION_ERROR` | 400 | Source de données invalide |
| `ConfigurationError` | `DataSourceError` | `DATA_SOURCE_CONFIGURATION_ERROR` | 500 | Config de connexion invalide (URL, credentials mal formés...) |
| `DataConnectionError` | `DataSourceError` | `DATA_SOURCE_CONNECTION_ERROR` | 503 | Connexion à la source impossible |
| `AuthenticationError` | `DataConnectionError` | `DATA_SOURCE_AUTHENTICATION_ERROR` | 401 | Échec d'authentification |
| `PermissionDeniedError` | `DataConnectionError` | `DATA_SOURCE_PERMISSION_DENIED` | 403 | Permissions insuffisantes |
| `LoadingError` | `DataSourceError` | `DATA_SOURCE_LOADING_ERROR` | 500 | Échec de chargement générique |
| `CloseError` | `DataSourceError` | `DATA_SOURCE_CLOSE_ERROR` | 500 | Échec à la fermeture de la source |
| `UnsupportedSourceError` | `DataSourceError` | `DATA_SOURCE_UNSUPPORTED` | 400 | Type de source non pris en charge |

> ⚠️ **Ne pas confondre avec les builtins Python** : `DataConnectionError`
> (et **non** `ConnectionError`) — le nom natif est volontairement évité
> pour ne jamais masquer le vrai `ConnectionError` réseau/OS.

### 5.2 File (`file.py`)

| Exception | Parent(s) | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `FileError` | `ValidationError` | `FILE_ERROR` | 400 | **Base commune à catcher pour toute erreur fichier** |
| `FileValidationError` | `FileError` | `FILE_VALIDATION_ERROR` | 400 | Fichier invalide avant lecture |
| `FileLoadingError` | `FileError` + `LoadingError` | `FILE_LOADING_ERROR` | 500 | Contenu illisible/non interprétable |
| `MissingFileError` | `FileValidationError` | `FILE_NOT_FOUND` | 404 | Fichier introuvable (⚠️ pas `FileNotFoundError`, voir §7) |
| `EmptyFileError` | `FileValidationError` | `FILE_EMPTY` | 500 (défaut hérité) | Fichier vide |
| `UnsupportedFileFormatError` | `FileValidationError` | `FILE_UNSUPPORTED_FORMAT` | 500 (défaut hérité) | Extension/format non supporté |
| `FilePermissionError` | `FileValidationError` | `FILE_PERMISSION_DENIED` | 403 | Droits insuffisants sur le fichier |
| `FileTooLargeError` | `FileValidationError` | `FILE_TOO_LARGE` | 413 | Taille max dépassée |
| `InvalidPDFError` | `FileLoadingError` | `INVALID_PDF` | 500 (défaut hérité) | PDF corrompu / invalide |
| `InvalidDOCXError` | `FileLoadingError` | `INVALID_DOCX` | 500 (défaut hérité) | DOCX corrompu / invalide |
| `InvalidXLSXError` | `FileLoadingError` | `INVALID_XLSX` | 500 (défaut hérité) | XLSX corrompu / invalide |
| `CorruptedFileError` | `FileLoadingError` | `FILE_CORRUPTED` | 400 | Fichier corrompu générique |
| `InvalidEncodingError` | `FileLoadingError` | `FILE_INVALID_ENCODING` | 400 | Encodage texte invalide |
| `JSONParsingError` | `FileLoadingError` | `JSON_PARSING_ERROR` | 400 | JSON malformé |
| `HTMLParsingError` | `FileLoadingError` | `HTML_PARSING_ERROR` | 400 | HTML malformé |

### 5.3 Database (`database.py`)

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `DatabaseError` | `DataSourceError` | `DATABASE_ERROR` | 500 | Base générique DB |
| `DatabaseValidationError` | `DatabaseError` | `DATABASE_VALIDATION_ERROR` | 400 | Config/paramètres DB invalides |
| `DatabaseConnectionError` | `DataConnectionError` | `DATABASE_CONNECTION_ERROR` | 503 | Connexion DB impossible (retryable) |
| `DatabaseAuthenticationError` | `DatabaseConnectionError` | `DATABASE_AUTHENTICATION_ERROR` | 401 | Auth DB refusée |
| `DatabasePermissionError` | `DatabaseConnectionError` | `DATABASE_PERMISSION_DENIED` | 403 | Droits DB insuffisants |
| `DatabaseTimeoutError` | `DatabaseConnectionError` | `DATABASE_TIMEOUT` | 504 | Timeout connexion (retryable) |
| `DatabaseNotFoundError` | `DatabaseConnectionError` | `DATABASE_NOT_FOUND` | 404 | Base inexistante |
| `DatabaseLoadingError` | `LoadingError` | `DATABASE_LOADING_ERROR` | 500 | Échec récupération données (retryable) |
| `QueryExecutionError` | `DatabaseLoadingError` | `DATABASE_QUERY_ERROR` | 500 | Requête SQL en échec |
| `TableNotFoundError` | `DatabaseLoadingError` | `DATABASE_TABLE_NOT_FOUND` | 404 | Table inexistante |
| `EmptyResultError` | `DatabaseLoadingError` | `DATABASE_EMPTY_RESULT` | 404 | Requête sans résultat |
| `TransactionError` | `DatabaseError` | `DATABASE_TRANSACTION_ERROR` | 500 | Échec transaction (retryable) |
| `DuplicateKeyError` | `DatabaseLoadingError` | `DATABASE_DUPLICATE_KEY` | 409 | Violation PK/UNIQUE |
| `ForeignKeyError` | `DatabaseLoadingError` | `DATABASE_FOREIGN_KEY` | 409 | Violation FK |

### 5.4 Parser (`parser.py`) — étage 2 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `ParserError` | `GMAOError` | `PARSER_ERROR` | 422 | **Base à catcher pour toute erreur de parsing** |
| `ParserValidationError` | `ParserError` | `PARSER_VALIDATION_ERROR` | 400 | Entrée/config du Parser invalide |
| `InvalidStrategyError` | `ParserError` | `PARSER_INVALID_STRATEGY` | 500 | Stratégie de parsing invalide (bug de code) |
| `ParserStrategyNotRegisteredError` | `ParserError` | `PARSER_STRATEGY_NOT_REGISTERED` | 500 | `source_type` inconnu du registre |
| `UnsupportedSourceTypeError` | `ParserError` | `PARSER_UNSUPPORTED_SOURCE_TYPE` | 400 | `source_type` reconnu mais non implémenté |
| `ParserExecutionError` | `ParserError` | `PARSER_EXECUTION_ERROR` | 422 | Échec technique pendant le parsing (encapsule une lib externe) |
| `EmptyDocumentError` | `ParserError` | `PARSER_EMPTY_DOCUMENT` | 422 | Document sans contenu exploitable |
| `ParsedDocumentError` | `ParserError` | `PARSER_INVALID_OUTPUT` | 500 | Sortie du Parser invalide/incohérente |

### 5.5 Chunker (`chunker.py`) — étage 3 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `ChunkerError` | `GMAOError` | `CHUNKER_ERROR` | 422 | **Base à catcher pour toute erreur de chunking** |
| `ChunkerValidationError` | `ChunkerError` | `CHUNKER_VALIDATION_ERROR` | 400 | Entrée/config du Chunker invalide |
| `InvalidChunkerStrategyError` | `ChunkerError` | `CHUNKER_INVALID_STRATEGY` | 500 | Stratégie de chunking invalide (bug de code) |
| `ChunkerStrategyNotRegisteredError` | `ChunkerError` | `CHUNKER_STRATEGY_NOT_REGISTERED` | 500 | `source_type` inconnu du registre |
| `ChunkingError` | `ChunkerError` | `CHUNKING_ERROR` | 422 | Échec technique pendant le chunking |
| `EmptyChunkError` | `ChunkerError` | `CHUNKER_EMPTY_CHUNK` | 422 | Chunk vide produit (ne doit pas aller à l'embedding) |
| `ChunkSizeError` | `ChunkerValidationError` | `CHUNKER_INVALID_CHUNK_SIZE` | 400 | `chunk_size`/`overlap` invalides (accepte `chunk_size=` et `overlap=` en kwargs, stockés dans `details`) |

### 5.6 Embedding (`embedding.py`) — étage 4 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `EmbeddingError` | `GMAOError` | `EMBEDDING_ERROR` | 500 | **Base à catcher pour toute erreur d'embedding** |
| `EmbeddingValidationError` | `EmbeddingError` | `EMBEDDING_VALIDATION_ERROR` | 400 | Entrée/config de l'embedder invalide |
| `InvalidEmbeddingStrategyError` | `EmbeddingError` | `EMBEDDING_INVALID_STRATEGY` | 500 | Classe non conforme au contrat `EmbeddingStrategy` |
| `EmbeddingStrategyNotRegisteredError` | `EmbeddingError` | `EMBEDDING_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `EmbeddingExecutionError` | `EmbeddingError` | `EMBEDDING_EXECUTION_ERROR` | 500 | Échec technique pendant le calcul d'embeddings |
| `IncompatibleEmbeddingModelError` | `EmbeddingError` | `EMBEDDING_INCOMPATIBLE_MODEL` | 400 | Dimension du vecteur inattendue |

### 5.7 Storage (`storage.py`) — étage 5 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `StorageError` | `GMAOError` | `STORAGE_ERROR` | 500 | **Base à catcher pour toute erreur de storage** |
| `StorageValidationError` | `StorageError` | `STORAGE_VALIDATION_ERROR` | 400 | Entrée/config du storage invalide |
| `StorageAlignmentError` | `StorageError` | `STORAGE_ALIGNMENT_ERROR` | 400 | Dimension vectorielle incohérente |
| `InvalidStorageStrategyError` | `StorageError` | `STORAGE_INVALID_STRATEGY` | 500 | Classe non conforme au contrat `StorageStrategy` |
| `StorageStrategyNotRegisteredError` | `StorageError` | `STORAGE_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `StorageConnectionError` | `StorageError` | `STORAGE_CONNECTION_ERROR` | 503 | Connexion au backend de storage impossible |
| `StorageWriteError` | `StorageError` | `STORAGE_WRITE_ERROR` | 500 | Échec d'écriture dans le backend |
| `PartialStorageError` | `StorageError` | `STORAGE_PARTIAL_ERROR` | 207 | Certains chunks stockés, d'autres non |

### 5.8 Retrieval (`retrieval.py`) — étage 6 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `RetrievalError` | `GMAOError` | `RETRIEVAL_ERROR` | 500 | **Base à catcher pour toute erreur de retrieval** |
| `RetrievalValidationError` | `RetrievalError` | `RETRIEVAL_VALIDATION_ERROR` | 400 | Configuration/paramètres invalides |
| `EmptyQueryError` | `RetrievalValidationError` | `RETRIEVAL_EMPTY_QUERY` | 400 | Requête vide ou constituée uniquement d'espaces |
| `InvalidRetrievalStrategyError` | `RetrievalError` | `RETRIEVAL_INVALID_STRATEGY` | 500 | Classe non conforme au contrat `RetrievalStrategy` |
| `RetrievalStrategyNotRegisteredError` | `RetrievalError` | `RETRIEVAL_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `RetrievalConnectionError` | `RetrievalError` | `RETRIEVAL_CONNECTION_ERROR` | 503 | Connexion Qdrant ou MySQL impossible |
| `RetrievalExecutionError` | `RetrievalError` | `RETRIEVAL_EXECUTION_ERROR` | 500 | Échec d'exécution de la requête |
| `IncompatibleEmbeddingModelError` | `RetrievalError` | `RETRIEVAL_INCOMPATIBLE_EMBEDDING_MODEL` | 400 | Dimension du query_vector ≠ dimension collection |

### 5.9 Reranker (`reranker.py`) — étage 7 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `RerankerError` | `GMAOError` | `RERANKER_ERROR` | 500 | **Base à catcher pour toute erreur de reranking** |
| `RerankerValidationError` | `RerankerError` | `RERANKER_VALIDATION_ERROR` | 400 | Entrée invalide (query vide, top_k invalide, etc.) |
| `RerankerModelError` | `RerankerError` | `RERANKER_MODEL_ERROR` | 500 | Échec de chargement ou d'exécution du modèle |
| `RerankingError` | `RerankerError` | `RERANKING_ERROR` | 500 | Échec technique pendant le reranking |
| `RerankerStrategyNotRegisteredError` | `RerankerError` | `RERANKER_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `InvalidRerankerStrategyError` | `RerankerError` | `RERANKER_INVALID_STRATEGY` | 500 | Classe non conforme au contrat `RerankerStrategy` |

### 5.10 LLM (`llm.py`) — étage 8 du pipeline

| Exception | Parent | `error_code` | HTTP | Cas d'usage |
|---|---|---|---|---|
| `LLMError` | `GMAOError` | `LLM_ERROR` | 500 | **Base à catcher pour toute erreur LLM** |
| `LLMValidationError` | `LLMError` | `LLM_VALIDATION_ERROR` | 400 | Entrée/config du LLM invalide |
| `LLMConnectionError` | `LLMError` | `LLM_CONNECTION_ERROR` | 502 | Connexion au provider LLM impossible |
| `LLMRateLimitError` | `LLMError` | `LLM_RATE_LIMIT_ERROR` | 429 | Quota ou rate limit dépassé |
| `LLMModelError` | `LLMError` | `LLM_MODEL_ERROR` | 500 | Erreur interne du modèle LLM |
| `LLMGenerationError` | `LLMError` | `LLM_GENERATION_ERROR` | 500 | Le LLM n'a pas produit de réponse valide |
| `LLMStrategyNotRegisteredError` | `LLMError` | `LLM_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `InvalidLLMStrategyError` | `LLMError` | `LLM_INVALID_STRATEGY` | 500 | Classe non conforme au contrat `LLMStrategy` |

---

## 6. Exemples d'usage

### 6.1 Lever une exception simple

```python
from app.exceptions import MissingFileError

if not path.exists():
    raise MissingFileError(f"Le fichier '{path}' est introuvable.")
```

### 6.2 Chaîner l'exception d'origine (2 façons, équivalentes via `.cause`)

```python
from app.exceptions import InvalidPDFError

try:
    reader = PdfReader(path)
except PdfReadError as exc:
    # Option A — idiome Python natif (recommandé)
    raise InvalidPDFError(f"Impossible de lire {path.name}") from exc

    # Option B — API interne équivalente
    # raise InvalidPDFError(f"Impossible de lire {path.name}").with_original(exc)
```

`err.cause` renverra l'exception d'origine dans les deux cas.

### 6.3 Ajouter des `details` structurés

```python
from app.exceptions import ChunkSizeError

if overlap >= chunk_size:
    raise ChunkSizeError(
        "overlap doit être strictement inférieur à chunk_size.",
        chunk_size=chunk_size,
        overlap=overlap,
    )
# e.details == {"chunk_size": ..., "overlap": ...}
```

### 6.4 Catcher au bon niveau de granularité

```python
from app.exceptions import FileError, ParserError, ChunkerError, GMAOError

try:
    raw = load_file(path)          # peut lever n'importe quelle FileError
    doc = parse(raw)               # peut lever n'importe quelle ParserError
    chunks = chunk(doc)            # peut lever n'importe quelle ChunkerError
except FileError as e:
    logger.error("Erreur de chargement: %s", e.to_dict())
    raise
except ParserError as e:
    logger.error("Erreur de parsing: %s", e.to_dict())
    raise
except ChunkerError as e:
    logger.error("Erreur de chunking: %s", e.to_dict())
    raise
except GMAOError as e:
    # Filet de sécurité générique pour toute autre erreur métier
    logger.error("Erreur GMAO non catégorisée: %s", e.to_dict())
    raise
```

### 6.5 Réponse API (FastAPI / Flask...)

```python
from app.exceptions import GMAOError

@app.exception_handler(GMAOError)
async def gmao_error_handler(request, exc: GMAOError):
    return JSONResponse(
        status_code=exc.http_status or 500,
        content=exc.to_dict(),
    )
```

---

## 7. Pièges connus / règles à ne jamais enfreindre

Ces règles proviennent d'un audit du module et de bugs **réellement
reproduits** (voir Changelog) — elles doivent être respectées pour
toute contribution future, humaine ou générée par IA.

1. **Ne jamais nommer une exception comme un builtin Python**
   (`FileNotFoundError`, `ConnectionError`, `TimeoutError`,
   `PermissionError`, `ValueError`...). Un `from app.exceptions import X`
   masquerait le builtin dans tout le fichier appelant, cassant les
   `except X:` censés attraper de vraies erreurs OS/réseau. Utiliser un
   nom explicite (`MissingFileError`, `DataConnectionError`...).

2. **Catcher `FileError`, jamais `FileValidationError` ou
   `FileLoadingError` isolément**, sauf besoin explicite de distinguer
   validation vs chargement. `FileError` est le seul point d'entrée
   garanti couvrir toutes les sous-classes fichier.

3. **Ne jamais passer `details=None` explicitement dans un nouvel
   `__init__` custom** sans le neutraliser (`dict(details or {})`).
   Bien que `GMAOError.__post_init__` normalise déjà `None → {}` en
   filet de sécurité, toute sous-classe qui construit ses propres
   `details` doit le faire proprement (voir `ChunkSizeError` en
   §5.5/§6.3 comme modèle).

4. **Toujours définir `DEFAULT_MESSAGE` ET `DEFAULT_ERROR_CODE`**
   (en MAJUSCULES, jamais `default_message`/`default_code` en
   minuscules) pour toute nouvelle exception concrète — sinon les
   valeurs sont silencieusement ignorées et remplacées par celles du
   parent.

5. **Les instances sont immuables** (`frozen=True`). Pour enrichir une
   exception déjà construite, utiliser `.with_original(exc)` (retourne
   une nouvelle instance) plutôt que d'essayer une affectation directe.

6. **Toujours importer depuis `app.exceptions` (le package), pas
   depuis un sous-module précis**, sauf besoin très spécifique :
   `from app.exceptions import MissingFileError`
   plutôt que `from app.exceptions.file import MissingFileError`.

---

## 8. Comment ajouter une nouvelle exception

Checklist pour une IA/un développeur qui doit créer une nouvelle
exception métier :

1. **Identifier la couche** : est-ce lié à une source de données
   générique, un fichier, une base de données, le parsing ou le
   chunking ?
2. **Trouver le parent le plus proche sémantiquement** dans l'arbre du
   §2 (ne pas hériter directement de `GMAOError` si une classe
   intermédiaire existe déjà).
3. **Définir au minimum** :
   ```python
   class MaNouvelleException(ParentApproprie):
       DEFAULT_MESSAGE = "Message clair en anglais ou français cohérent avec le reste du fichier."
       DEFAULT_ERROR_CODE = "PREFIXE_COURT_MAJUSCULE"
       DEFAULT_HTTP_STATUS = 400  # ou l'équivalent le plus proche du tableau §5
   ```
4. **Ne PAS réécrire `__init__`** sauf besoin réel de paramètres
   supplémentaires (voir `ChunkSizeError` pour un exemple correct avec
   `chunk_size`/`overlap`).
5. **Exporter la classe** dans :
   - `__all__` du fichier concerné ;
   - l'import + `__all__` de `app/exceptions/__init__.py` ;
   - le dictionnaire `_SUBMODULES` de `__init__.py` (pour le fallback
     lazy-loading).
6. **Ajouter une ligne dans la table de référence de ce document**
   (§5) et, si la hiérarchie change, mettre à jour l'arbre du §2.

---

## 9. Guide rapide pour un chatbot générant du code sur ce projet

- Si on te demande de gérer une erreur de **lecture de fichier PDF
  corrompu** → `raise InvalidPDFError(...)`, catchable par
  `except FileError:` ou `except InvalidPDFError:`.
- Si on te demande de gérer un **fichier absent** → `MissingFileError`,
  **jamais** `FileNotFoundError`.
- Si on te demande de gérer une **erreur de connexion DB** →
  `DatabaseConnectionError` (pas `ConnectionError`).
- Si on te demande une **exception de parsing** sans précision → base-toi
  sur `ParserExecutionError` (échec technique) ou
  `ParserValidationError` (entrée invalide) selon le contexte, jamais
  `ParserError` nu sauf pour catcher.
- Si on te demande une **exception de chunking liée à la taille** →
  `ChunkSizeError(chunk_size=..., overlap=...)`.
- Par défaut, **toujours** proposer `raise NouvelleErreur(...) from exc_original`
  quand une exception tierce est capturée, pour préserver la traçabilité
  (`.cause` la récupère automatiquement).
- Ne jamais suggérer de lever `Exception` ou une exception builtin nue
  dans le code métier du projet.

---

## Changelog — historique des corrections

| Version | Changement |
|---|---|
| v1 (audit initial) | Hiérarchie fonctionnelle mais : `FileError` ne couvrait pas `FileLoadingError` et ses enfants ; `FileNotFoundError`/`ConnectionError` masquaient les builtins Python ; `details=None` crashait `repr()` sur Parser/Chunker ; Parser/Chunker sans `error_code`/`http_status` ; `InvalidPDFError` utilisait des attributs mal nommés (`default_code`/`default_message`) ; imports absolus/relatifs incohérents ; entrée `chunker` manquante dans le fallback lazy-loading. |
| **v2 (actuelle)** | Tous les points ci-dessus corrigés et testés unitairement : héritage multiple `FileLoadingError(FileError, LoadingError)`, renommage `MissingFileError`/`DataConnectionError`, normalisation `details` dans `GMAOError.__post_init__`, pattern `DEFAULT_*` unifié sur les 3 couches, imports relatifs partout, `_SUBMODULES` complet et cohérent. |
| **v3** | Ajout des branches `EmbeddingError`, `StorageError`, `RetrievalError`, `RerankerError`, `LLMError` dans l'arbre §2. Ajout des sous-sections §5.6–5.10 dans la table de référence. Ajout de `InvalidRerankerStrategyError` et `InvalidLLMStrategyError` (déplacées depuis les registres vers `app/exceptions/`). Règle d'or étendue : `__init_subclass__` lève des sous-classes de `GMAOError`, pas des `TypeError` nus. |

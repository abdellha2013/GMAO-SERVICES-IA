# Référence — Module `app.storage`

> **Objectif de ce document** : fournir une référence autonome de la couche
> de stockage (*storage*) du projet **GMAO-RAG**, pour les développeurs et
> les assistants IA qui doivent l'utiliser ou l'étendre sans relire
> l'ensemble du code source.
>
> Le module reçoit une liste de `Chunk` et la liste d'`Embedding` alignée
> produite par `app.embedding`, et les persiste dans un ou plusieurs
> backends (MySQL, Qdrant). Il ne charge pas de données, ne parse pas les
> formats, ne découpe pas de texte et ne calcule pas d'embeddings.
>
> Document complémentaire à `EXCEPTIONS.md`, `CHUNKER.md`, `EMBEDDING.md`
> et `DATA_SOURCES.md`.
>
> Version documentée : v3 (post-correction — voir section
> [Changelog](#changelog--historique-des-corrections)).

---

## 1. Vue d'ensemble

`app.storage` est le cinquième étage du pipeline RAG :

```text
Fichier / Base de données / API
            ↓
     app.data_sources
            ↓
      SourceDocument
            ↓
        app.parser
            ↓
      ParsedDocument
            ↓
        app.chunker
            ↓
       list[Chunk]
            ↓
       app.embedding
            ↓
      list[Embedding]
            ↓
        app.storage
            ↓
     MySQL (chunk_rag, document_chunk, panne_chunk)
     Qdrant (collection vectorielle)
```

Sa responsabilité est de persister chaque paire `(Chunk, Embedding)` dans
un ou plusieurs backends, dans un ordre défini, en gérant l'échec partiel
d'une stratégie sans nécessairement faire échouer les autres.

Le module de storage ne fait pas :

- de lecture de fichier ou de connexion à une source de données amont ;
- de parsing, de découpage ou de calcul d'embeddings ;
- de génération d'identifiants métier (`id_document`, `id_panne`,
  `id_equipement`) — ces identifiants doivent déjà être présents dans
  `Chunk.metadata` avant d'atteindre ce module (voir [§7](#7-contrat-de-métadonnées)) ;
- de retry automatique ou de file d'attente — un échec est reporté, pas
  réessayé.

### Composition du package

| Fichier / package | Rôle |
|---|---|
| `app/storage/base.py` | contrats `StorageStrategy`, `StorageOutcome`, `StorageReport` |
| `app/storage/registry.py` | association `strategy_name` → classe de stratégie |
| `app/storage/orchestrator.py` | alignement, séquencement, agrégation, politique d'échec |
| `app/storage/strategies/mysql_storage.py` | backend relationnel (MySQL) |
| `app/storage/strategies/qdrant_storage.py` | backend vectoriel (Qdrant) |
| `app/storage/strategies/__init__.py` | export des stratégies et tuple `ALL_STRATEGIES` |
| `app/storage/__init__.py` | API publique et constructeurs de registre/orchestrateur par défaut |
| `app/exceptions/storage.py` | hiérarchie d'exceptions dédiée (voir [§8](#8-exceptions)) |

### Règle d'or

> Dans le code applicatif, toujours appeler `StorageOrchestrator.save(...)`
> / `StorageOrchestrator.delete(...)`, ou
> `build_default_orchestrator().save(...)`. **Ne jamais instancier une
> stratégie directement** : au-delà de la cohérence avec les autres
> modules du pipeline, c'est l'orchestrateur qui garantit l'alignement
> chunk/embedding, l'ordre MySQL → Qdrant, et la propagation du statut
> d'indexation entre les deux backends. Appeler une stratégie isolément
> contourne ces garanties.

---

## 2. Point d'entrée public

```python
from app.storage import build_default_orchestrator
from app.models.chunk import Chunk
from app.models.embedding import Embedding

orchestrator = build_default_orchestrator()

report = orchestrator.save(chunks, embeddings)

if report.has_failures:
    # report.failures est une liste de dicts JSON-sérialisables
    # (message, error_code, details) — voir §5.
    logger.error("Storage partiellement en échec: %s", report.failures)
```

`build_default_orchestrator(**options)` construit un registre prérempli
(MySQL puis Qdrant) via `build_default_registry()`, puis un
`StorageOrchestrator`. `build_default_registry()` **n'ouvre aucune
connexion et ne valide aucune variable d'environnement** : elle ne fait
qu'enregistrer des classes. Elle peut donc être appelée sans risque en
test ou en environnement local sans base configurée.

| Paramètre de l'orchestrateur | Défaut | Rôle |
|---|---|---|
| `strategy_sequence` | `("mysql", "qdrant")` | ordre d'exécution des stratégies ; MySQL doit précéder Qdrant (voir §7) |
| `stop_on_failure` | `False` | si `True`, la première `StorageError` interrompt la séquence et se propage telle quelle |
| `raise_on_partial_failure` | `True` | si `True`, lève `PartialStorageError` en fin d'appel quand le rapport contient des échecs et que `stop_on_failure` valait `False` |
| `**options` | — | transmis tels quels au constructeur de chaque stratégie (ex. `dsn=`, `collection_name=`) |

---

## 3. Contrat `StorageStrategy`

Toute stratégie doit hériter de `StorageStrategy` et déclarer un attribut
de classe `name` non vide :

```python
class StorageStrategy(ABC):
    name: str = ""  # attribut de CLASSE, pas une @property

    def supports(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> bool: ...
    def save(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> StorageOutcome: ...
    def delete(self, chunk_ids: Sequence[Any]) -> StorageOutcome: ...
```

| Membre | Responsabilité |
|---|---|
| `name` | nom stable de la stratégie, lu **sans instanciation** par le registre |
| `supports()` | test de compatibilité sans effet de bord |
| `save()` | persiste le batch, retourne un `StorageOutcome` |
| `delete()` | supprime les enregistrements identifiés par `chunk_ids`, retourne un `StorageOutcome` |

`name` est volontairement un attribut de classe et non une `@property`
d'instance : le registre doit pouvoir le lire sans construire la
stratégie, car construire `MySQLStorage` ouvre une connexion et valide
des variables d'environnement (voir §4). `__init_subclass__` valide à la
**définition** de la classe que `name` est une chaîne non vide — une
sous-classe mal formée échoue au chargement du module, pas au premier
appel.

Une stratégie doit lever une sous-classe de `StorageError` pour toute
erreur métier, et ne jamais laisser fuiter une exception SQLAlchemy ou
Qdrant brute.

---

## 4. `StorageRegistry`

`StorageRegistry` stocke des **classes**, jamais des instances — c'est le
point qui a été corrigé par rapport à une version précédente qui
instanciait la stratégie à l'enregistrement pour lire `.name`, ce qui
déclenchait une connexion DB dès `build_default_registry()`.

```python
from app.storage import StorageRegistry
from app.storage.strategies import MySQLStorage, QdrantStorage

registry = StorageRegistry()
registry.register(MySQLStorage)
registry.register(QdrantStorage)

registry.get("mysql")              # -> MySQLStorage (classe)
registry.has("MYSQL")              # -> True (normalisé)
registry.supported_strategies()     # -> ("mysql", "qdrant")
```

| Méthode | Effet |
|---|---|
| `register(strategy_class)` | enregistre la classe sous `strategy_class.name` normalisé ; **aucune instanciation** |
| `get(name)` | retourne la classe, lève `StorageStrategyNotRegisteredError` sinon |
| `has(name)` | renvoie `False` sans exception pour un nom invalide ou inconnu |
| `unregister(name)` | retire le mapping sur le nom normalisé ; lève `StorageStrategyNotRegisteredError` si absent (aucune instanciation non plus) |
| `clear()` | retire tous les mappings |
| `supported_strategies()` | retourne les noms enregistrés, triés |

`register()` échoue avec `InvalidStorageStrategyError` si la classe
n'hérite pas de `StorageStrategy` ou si `name` est vide, et avec
`StorageValidationError` si le nom est déjà pris par une autre classe.

---

## 5. `StorageOutcome` et `StorageReport`

```python
@dataclass(frozen=True, slots=True)
class StorageOutcome:
    strategy_name: str
    saved_ids: tuple[Any, ...] = ()
    failures: tuple[dict[str, Any], ...] = ()

    @property
    def success(self) -> bool: ...  # True si failures est vide

@dataclass(frozen=True, slots=True)
class StorageReport:
    outcomes: tuple[StorageOutcome, ...] = ()

    @property
    def failures(self) -> tuple[dict[str, Any], ...]: ...   # aplatit toutes les failures
    @property
    def has_failures(self) -> bool: ...
    @property
    def is_full_success(self) -> bool: ...                  # True si tous les outcomes ont réussi
```

Chaque entrée de `failures` est un dictionnaire JSON-sérialisable produit
par `exc.to_dict()` sur la `StorageError` capturée — `message`,
`error_code`, `details` d'origine sont donc conservés, pas remplacés par
un message générique.

`saved_ids` a un type volontairement générique (`tuple[Any, ...]`) : pour
`MySQLStorage`, ce sont des entiers auto-incrémentés (`id_chunk`) ; pour
`QdrantStorage`, ce sont les mêmes entiers réutilisés comme identifiants
de points. Ce n'est **pas** le même espace d'identifiants que
`Chunk.chunk_id` / `Embedding.chunk_id` (des chaînes, voir CHUNKER.md §8
et EMBEDDING.md §7) — ne pas confondre les deux.

---

## 6. `StorageOrchestrator`

```text
list[Chunk], list[Embedding]
      ↓
vérification d'alignement (longueur + identité logique chunk/embedding)
      ↓
pour chaque nom dans strategy_sequence :
    résolution via StorageRegistry.get(name)
    instanciation avec **options
    strategy.save(chunks, embeddings)  →  StorageOutcome
    si name == "qdrant" et succès : mise à jour du statut MySQL
      ↓
StorageReport(outcomes)
      ↓
si report.has_failures et pas stop_on_failure et raise_on_partial_failure :
    raise PartialStorageError
      ↓
retour du StorageReport
```

### 6.1 Alignement chunk/embedding

Avant toute écriture, l'orchestrateur vérifie que `chunks` et
`embeddings` ont la même longueur, puis que chaque paire partage la même
**identité logique**. Cette identité est calculée avec la même règle de
repli qu'`EMBEDDING.md` §7 pour `Embedding.chunk_id` :

```python
def _logical_chunk_id(chunk: Chunk) -> str:
    return chunk.chunk_id or f"{chunk.source_name}:{chunk.chunk_index}"
```

C'est un point important : `RecursiveChunker` (TXT, PDF, DOCX, HTML)
laisse `Chunk.chunk_id` à `None` (voir CHUNKER.md §7.1/§8), alors
qu'`Embedding.chunk_id` applique déjà ce repli à sa création. Comparer
directement `chunk.chunk_id != embedding.chunk_id` casserait donc
l'alignement pour tout document non-Markdown/non-structuré — c'est pour
cette raison que l'orchestrateur reconstruit l'identité logique du côté
chunk avant de comparer, plutôt que de comparer le champ brut.

Un désalignement réel (mauvais ordre, batch tronqué) lève toujours
`StorageAlignmentError`, avec `chunk_count`/`embedding_count` ou l'index
et les deux identifiants en cause dans `details`.

### 6.2 Séquencement et gestion des échecs

Chaque stratégie de `strategy_sequence` est résolue et instanciée à
chaque appel — l'instanciation peut légitimement échouer (ex. DSN absent)
et cet échec est traité comme celui de `save()`/`delete()` :

- si `stop_on_failure=True` : la `StorageError` d'origine se propage
  immédiatement, la séquence s'arrête ;
- si `stop_on_failure=False` (défaut) : l'échec est capturé, transformé
  en `StorageOutcome` avec `failures=(exc.to_dict(),)`, et la séquence
  continue avec la stratégie suivante.

### 6.3 Propagation du statut d'indexation (MySQL → Qdrant)

Après un `save()` Qdrant **réussi**, l'orchestrateur — pas
`QdrantStorage` — appelle `MySQLStorage.mark_indexed(chunk_ids)` pour
passer `chunk_rag.statut_embedding` à `'Indexe'`. `QdrantStorage` ne
connaît ni le schéma MySQL ni SQLAlchemy : ce découplage est volontaire,
pour que les deux stratégies restent remplaçables indépendamment. Si
`"mysql"` n'est pas dans le registre courant, cette étape est simplement
ignorée (pas d'erreur).

### 6.4 `delete()`

```python
report = orchestrator.delete(chunk_ids)
```

Symétrique à `save()` : parcourt `strategy_sequence`, applique la même
politique `stop_on_failure`/`raise_on_partial_failure`, retourne un
`StorageReport`. Il n'y a pas de vérification d'alignement (`chunk_ids`
est une simple séquence d'identifiants).

### 6.5 `PartialStorageError`

Levée en fin de `save()`/`delete()` quand :
- `report.has_failures` est vrai, **et**
- `stop_on_failure=False` (sinon l'erreur d'origine s'est déjà propagée), **et**
- `raise_on_partial_failure=True` (comportement par défaut).

`details={"failures": [...], "succeeded_strategies": [...]}` contient les
échecs et le nom des stratégies ayant réussi, sous une forme
JSON-sérialisable. Aucun objet `StorageReport` n'est attaché à l'exception.
Mettre `raise_on_partial_failure=False` pour ne recevoir qu'un
`StorageReport` et laisser la couche appelante (par ex. une route API)
décider elle-même du comportement à adopter face à un succès partiel.

---

## 7. Contrat de métadonnées

`app.storage` attend que certaines clés soient déjà présentes dans
`Chunk.metadata` **avant** d'atteindre ce module. `app.chunker` et
`app.embedding` ne les produisent pas ; elles sont injectées par
`MySQLLoader` lorsque l'appelant fournit `id_document` ou `id_panne`, puis
propagées sans modification par `parser` et `chunker`.

| Clé | Type | Requise par | Étage responsable de l'injection | Comportement si absente |
|---|---|---|---|---|
| `id_document` | `int` | `MySQLStorage.supports()` | `MySQLLoader`, argument explicite, existence validée en base | `supports()` renvoie `False` pour ce chunk ; `save()` lève `StorageValidationError` si appelé quand même |
| `id_panne` | `int` | `MySQLStorage.supports()` | `MySQLLoader`, argument explicite, existence validée en base | Idem `id_document` |
| `id_equipement` | `int \| None` | Qdrant (payload uniquement) | `MySQLLoader`, lu depuis le parent document/panne validé | Non bloquant : le point est écrit avec `id_equipement = None` |
| `id_chunk` | `int` | `QdrantStorage.supports()` | **généré par `MySQLStorage.save()`**, pas par un étage amont | `supports()` renvoie `False` tant que MySQL n'a pas tourné avant Qdrant dans `strategy_sequence` |

**Règle de séquencement** : `id_chunk` n'existe qu'après le passage de
`MySQLStorage.save()` (clé primaire auto-incrémentée de `chunk_rag`).
`strategy_sequence` doit donc toujours placer `"mysql"` avant `"qdrant"`
— c'est la valeur par défaut de l'orchestrateur, ne pas la réordonner
sans réimplémenter ce couplage autrement.

Pour une source MySQL destinée au stockage, l'appelant doit donc fournir un
et un seul parent (`id_document` ou `id_panne`) à `MySQLLoader`. Un résultat
MySQL générique, sans parent, reste chargeable mais n'est pas compatible avec
`MySQLStorage`.

---

## 8. Exceptions

```text
GMAOError
└── StorageError
    ├── StorageValidationError
    │   └── StorageAlignmentError
    ├── InvalidStorageStrategyError
    ├── StorageStrategyNotRegisteredError
    ├── StorageConnectionError
    ├── StorageWriteError
    └── PartialStorageError
```

| Exception | `error_code` | HTTP | Cas typique |
|---|---|---|---|
| `StorageError` | `STORAGE_ERROR` | 500 | Base générique, ne pas lever directement |
| `StorageValidationError` | `STORAGE_VALIDATION_ERROR` | 400 | Configuration ou métadonnées de chunk invalides (ex. `id_document`/`id_panne` absents) |
| `StorageAlignmentError` | `STORAGE_ALIGNMENT_ERROR` | 400 | `chunks`/`embeddings` non alignés (longueur ou identité logique) |
| `InvalidStorageStrategyError` | `STORAGE_INVALID_STRATEGY` | 500 | Classe non conforme à `StorageStrategy`, ou `name` absent/vide |
| `StorageStrategyNotRegisteredError` | `STORAGE_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `StorageConnectionError` | `STORAGE_CONNECTION_ERROR` | 500 | Échec d'établissement de connexion (host injoignable, auth refusée) — jamais un échec d'écriture sur une connexion déjà ouverte |
| `StorageWriteError` | `STORAGE_WRITE_ERROR` | 500 | Échec d'écriture/suppression sur une connexion déjà établie (contrainte violée, upsert Qdrant en échec) |
| `PartialStorageError` | `PARTIAL_STORAGE_ERROR` | 207 | Levée par l'orchestrateur quand certaines stratégies ont échoué et d'autres ont réussi |

**Distinction connexion / écriture** : `StorageConnectionError` est
réservée aux échecs d'établissement de connexion (ex. `OperationalError`
SQLAlchemy pour MySQL, échec de construction du `QdrantClient` pour
Qdrant). Toute erreur survenant pendant une opération sur une connexion
déjà ouverte (contrainte, upsert, delete) est un `StorageWriteError`.
Cette distinction reflète celle déjà établie entre
`DatabaseConnectionError` et `DatabaseLoadingError` dans `database.py`
(voir EXCEPTIONS.md §5.3) — à respecter pour toute nouvelle stratégie.

---

## 9. Ajouter une stratégie

1. Hériter de `StorageStrategy`.
2. Déclarer `name` comme **attribut de classe** non vide (pas une
   `@property`).
3. Ne rien faire de coûteux ou de risqué (connexion réseau, lecture
   d'environnement) en dehors de `__init__` — jamais à la simple
   définition de la classe.
4. Implémenter `supports()` sans effet de bord.
5. Implémenter `save()` : valider via `supports()`, encapsuler toute
   exception tierce dans `StorageConnectionError` (échec de connexion)
   ou `StorageWriteError` (échec d'écriture), retourner un
   `StorageOutcome`.
6. Implémenter `delete()` selon le même principe.
7. Ne jamais écrire dans le backend d'une autre stratégie directement
   (voir §6.3) — si un couplage inter-stratégies est nécessaire, il doit
   vivre dans l'orchestrateur, pas dans la stratégie.
8. Ajouter la classe au tuple `ALL_STRATEGIES` de `strategies/__init__.py`
   pour qu'elle soit enregistrée par défaut, et l'ajouter à
   `strategy_sequence` si elle doit tourner par défaut.

---

## 10. Bonnes pratiques

- Toujours passer par `StorageOrchestrator`, jamais par une stratégie
  instanciée directement (voir §1, règle d'or).
- Garder `"mysql"` avant `"qdrant"` dans `strategy_sequence` : `id_chunk`
  n'existe qu'après le passage de MySQL (voir §7).
- Traiter `report.has_failures` comme un signal exploitable, pas comme un
  simple booléen : chaque entrée de `report.failures` conserve `message`,
  `error_code` et `details` d'origine.
- Ne jamais mettre `raise_on_partial_failure=False` sans que la couche
  appelante inspecte explicitement `report.has_failures` ensuite — sinon
  un échec partiel passe silencieusement inaperçu.
- Ne pas contourner `supports()` : c'est le seul endroit qui encode le
  contrat de métadonnées attendu par chaque backend (voir §7).
- Vérifier avec le DBA si les FK `document_chunk`/`panne_chunk` →
  `chunk_rag` ont `ON DELETE CASCADE` ; `MySQLStorage.delete()` supprime
  explicitement les lignes filles avant `chunk_rag`, ce qui reste correct
  dans les deux cas mais n'a besoin d'exister que dans le second.

---

## Changelog — historique des corrections

| Version | Changement |
|---|---|
| v1 (état initial) | `StorageOrchestrator.save()` comparait `chunk.chunk_id == embedding.chunk_id` sans repli, cassant l'alignement pour tout document `RecursiveChunker` (TXT/PDF/DOCX/HTML) ; aucune méthode `delete()` sur l'orchestrateur ; `QdrantStorage` écrivait directement dans MySQL (couplage caché, connexion recréée à chaque appel) ; `StorageRegistry.register()`/`unregister()` instanciaient la stratégie pour lire `.name`, faisant échouer `build_default_registry()` sans variables d'environnement DB ; `StorageConnectionError` importée mais jamais levée dans `mysql_storage.py` ; échec Qdrant catégorisé à tort en `StorageConnectionError` au lieu de `StorageWriteError` ; `except StorageError` remplaçait le message d'erreur d'origine par un texte générique ; `PartialStorageError` définie mais jamais levée ; import dynamique `__import__(...)` au lieu d'un import standard ; `MySQLStorage.delete()` ne supprimait pas les lignes filles ; style de code condensé, non conforme PEP8. |
| v2 | Tous les points ci-dessus corrigés : alignement via `_logical_chunk_id()` avec repli identique à `EMBEDDING.md` ; `StorageOrchestrator.delete()` ajouté ; `mark_indexed()` isole la mise à jour de statut côté orchestrateur, `QdrantStorage` ne connaît plus MySQL ; `name` devenu attribut de classe, registre sans instanciation ; distinction `StorageConnectionError`/`StorageWriteError` cohérente avec `database.py` ; détails d'erreur préservés via `exc.to_dict()` ; `PartialStorageError` levée par défaut en fin de `save()`/`delete()` (contrôlable via `raise_on_partial_failure`) ; suppression des lignes filles avant `chunk_rag` ; style PEP8 partout. |
| **v3 (actuelle)** | `SentenceTransformerEmbedding.embed_query()` prend en charge le préfixe E5 `query: ` en réutilisant le cache du modèle des passages ; `MySQLLoader` injecte et valide le parent GMAO explicite (`id_document` ou `id_panne`) et propage `id_equipement` ; `PartialStorageError` n'attache pas de `StorageReport` post-construction et expose seulement des détails sérialisables. |

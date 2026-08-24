# Référence — Module `app.storage`

> **Objectif de ce document** : fournir une référence autonome de la couche
> de persistance (*Storage Layer*) du projet **GMAO-RAG**, pour les
> développeurs et les assistants IA qui doivent l'utiliser ou l'étendre
> sans relire l'ensemble du code source.
>
> Le module reçoit une liste de `Chunk` (`app.chunker`) et une liste
> d'`Embedding` (`app.embedding`) alignées par position, et les persiste
> dans les stores configurés (MySQL relationnel, Qdrant vectoriel). Il ne
> parse pas, ne découpe pas, ne calcule pas d'embedding.
>
> Document complémentaire à `EXCEPTIONS.md`, `CHUNKER.md`, `EMBEDDING.md`,
> `PARSER.md` et `DATA_SOURCES.md`.

---

## 1. Vue d'ensemble

`app.storage` est le **cinquième et dernier étage** du pipeline RAG :

```text
Fichier / Base de données / API
            ↓
     app.data_sources
            ↓
        app.parser
            ↓
        app.chunker
            ↓
       list[Chunk]
            ↓
       app.embedding
            ↓
      list[Embedding]
            ↓
        app.storage        (ce document)
            ↓
     MySQL (chunk_rag, document_chunk/panne_chunk)
     Qdrant (collection gmao_chunks)
```

Différence structurelle avec `app.chunker`/`app.embedding` : ces deux
modules **sélectionnent une** stratégie (routage par `source_type`, ou
nom de stratégie unique). `app.storage` **exécute plusieurs** stratégies
dans un ordre défini, parce qu'un même lot de `Chunk`/`Embedding` doit
être écrit dans MySQL **et** Qdrant — jamais l'un au choix de l'autre.

Le module de storage ne fait pas :

- de découpage ni de calcul d'embedding (responsabilité de `app.chunker`
  / `app.embedding`) ;
- de lecture ou de resélection de documents pour le retrieval (c'est le
  rôle d'un futur module de *recherche*, hors périmètre) ;
- de garantie de transaction distribuée entre MySQL et Qdrant — ce sont
  deux systèmes séparés, voir §5.2.

### Composition du package

| Fichier / package | Rôle |
|---|---|
| `base.py` | contrat abstrait `StorageStrategy` |
| `registry.py` | association `strategy_name` → classe de stratégie |
| `orchestrator.py` | séquencement, validation et exécution des stratégies actives |
| `strategies/mysql_storage.py` | persistance relationnelle (`chunk_rag`, `document_chunk`, `panne_chunk`) |
| `strategies/qdrant_storage.py` | persistance vectorielle (collection `gmao_chunks`) |
| `strategies/__init__.py` | export des stratégies et tuple `ALL_STRATEGIES` |
| `reconciliation.py` | détection et rattrapage des écritures partielles (§5.3) |
| `__init__.py` | API publique et constructeurs de registre/orchestrateur par défaut |

### Règle d'or

> Dans le code applicatif, toujours appeler `StorageOrchestrator.save(chunks, embeddings)`
> ou `build_default_orchestrator().save(chunks, embeddings)`. L'instanciation
> directe d'une stratégie est réservée aux tests ou à un besoin spécialisé
> explicitement identifié (ex. réindexation Qdrant seule, voir `reconciliation.py`).

---

## 2. Point d'entrée public

```python
from app.storage import build_default_orchestrator

orchestrator = build_default_orchestrator()
report = orchestrator.save(chunks, embeddings)

if report.has_failures:
    for failure in report.failures:
        logger.warning("Échec storage: %s", failure.to_dict())
```

`build_default_orchestrator()` construit un registre prérempli
(`MySQLStorage`, `QdrantStorage`) puis un `StorageOrchestrator` configuré
sur la séquence par défaut `("mysql", "qdrant")`.

| Paramètre de l'orchestrateur | Défaut | Rôle |
|---|---|---|
| `strategy_sequence` | `("mysql", "qdrant")` | ordre d'exécution — **jamais l'inverse**, voir §5.1 |
| `stop_on_failure` | `False` | si `True`, arrête la séquence au premier échec plutôt que de continuer et rapporter |

---

## 3. Contrat `StorageStrategy`

```python
class StorageStrategy(ABC):
    @property
    def name(self) -> str: ...

    def supports(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> bool: ...

    def save(self, chunks: Sequence[Chunk], embeddings: Sequence[Embedding]) -> StorageOutcome: ...

    def delete(self, chunk_ids: Sequence[int]) -> None: ...
```

| Membre | Responsabilité |
|---|---|
| `name` | nom stable utilisé comme clé de registre (`"mysql"`, `"qdrant"`) |
| `supports()` | test de compatibilité sans lancer l'écriture (ex. Qdrant refuse un lot sans `embedding.vector`) |
| `save()` | écrit le lot, retourne un `StorageOutcome` (succès/échec par item, jamais de levée pour un échec partiel — voir §5.1) |
| `delete()` | supprime par `chunk_id`, utilisé pour la réconciliation et les tests |

Une stratégie doit lever une sous-classe de `StorageError` uniquement
pour une erreur **bloquante** (connexion impossible, configuration
invalide). Un échec **par item** (ex. un seul chunk rejeté par une
contrainte) doit être reporté dans `StorageOutcome`, pas levé.

---

## 4. `StorageRegistry`

Même forme que `EmbeddingRegistry` : un **nom unique** par stratégie,
classes stockées, pas d'instances.

```python
from app.storage import StorageRegistry
from app.storage.strategies import MySQLStorage, QdrantStorage

registry = StorageRegistry()
registry.register(MySQLStorage)
registry.register(QdrantStorage)

registry.get("mysql")             # -> MySQLStorage
registry.has("QDRANT")            # -> True (normalisé)
registry.supported_strategies()   # -> ("mysql", "qdrant")
```

| Méthode | Effet |
|---|---|
| `register(strategy_class)` | instancie pour lire `.name`, puis enregistre |
| `get(name)` | retourne la classe, lève `StorageStrategyNotRegisteredError` sinon |
| `has(name)` | `False` sans exception pour un nom invalide ou inconnu |
| `unregister(name)` | retire le mapping |
| `clear()` | retire tous les mappings |
| `supported_strategies()` | noms enregistrés, triés |

---

## 5. `StorageOrchestrator`

```text
list[Chunk], list[Embedding]
      ↓
validation (même longueur, alignement chunk.chunk_id <-> embedding.chunk_id)
      ↓
pour chaque nom dans strategy_sequence :
      StorageRegistry.get(nom) -> instanciation -> strategy.supports() -> strategy.save()
      ↓
      agrégation dans StorageReport (succès / échecs par store, par item)
      ↓
retour du StorageReport (jamais de levée pour un échec partiel)
```

### 5.1 Pourquoi l'ordre `mysql` avant `qdrant` n'est pas arbitraire

`MySQLStorage` est exécuté **en premier** parce que c'est lui qui génère
`chunk_rag.id_chunk` (AUTO_INCREMENT) — cet identifiant est ensuite
**réutilisé tel quel comme ID de point Qdrant** (pas d'UUID séparé, pas
de `qdrant_point_id` à synchroniser en plus : un seul espace
d'identifiants, `id_chunk`, partagé par les deux stores). `QdrantStorage`
ne peut donc s'exécuter qu'après avoir reçu ces IDs.

Séquence détaillée exécutée par `MySQLStorage.save()` :

1. `INSERT` dans `chunk_rag` (transaction), `statut_embedding = 'En_attente'`.
2. `INSERT` dans `document_chunk` ou `panne_chunk` selon `chunk.source_type`
   (même transaction — garantit qu'un `chunk_rag` n'existe jamais sans
   son sous-type, voir `EXCEPTIONS.md` / discussion sur l'exclusivité).
3. Commit. Les `id_chunk` générés sont renvoyés dans le `StorageOutcome`.

Puis `QdrantStorage.save()` :

1. Pour chaque item, upsert d'un point `{id: id_chunk, vector, payload:
   {id_chunk, type_source, id_equipement}}` (payload minimal, voir §7).
2. Si succès : `UPDATE chunk_rag SET statut_embedding = 'Indexe' WHERE
   id_chunk = ...`.
3. Si échec : `statut_embedding` reste `'En_attente'` (ou passe à
   `'Échec'` après N tentatives) — **ligne MySQL jamais supprimée**, elle
   sert de trace pour la réconciliation.

### 5.2 Pas de transaction distribuée — assumé, pas caché

MySQL et Qdrant sont deux systèmes séparés : il n'y a pas de two-phase
commit entre eux. L'orchestrateur ne prétend pas garantir l'atomicité
inter-store ; il garantit seulement que :

- un `chunk_rag` sans écriture Qdrant réussie reste visible et détectable
  (`statut_embedding != 'Indexe'`) ;
- l'inverse (point Qdrant sans ligne MySQL) est **structurellement
  impossible**, puisque l'ID Qdrant est dérivé de l'ID MySQL et n'existe
  qu'après l'`INSERT`.

### 5.3 `reconciliation.py`

Fonction indépendante de l'orchestrateur, à exécuter en job planifié :

```python
from app.storage.reconciliation import reconcile_pending

report = reconcile_pending(older_than_minutes=30)
```

Sélectionne les `chunk_rag` avec `statut_embedding IN ('En_attente',
'Échec')` plus vieux que le seuil, relit `contenu` + régénère l'embedding
via `app.embedding`, et retente uniquement `QdrantStorage.save()` (jamais
`MySQLStorage.save()`, qui recréerait un doublon).

---

## 6. Stratégies concrètes

### 6.1 `MySQLStorage`

| Paramètre | Défaut | Rôle |
|---|---:|---|
| `dsn` | — (obligatoire) | chaîne de connexion SQLAlchemy |
| `batch_size` | `200` | taille de lot par `INSERT` |

Écrit dans `chunk_rag` + `document_chunk`/`panne_chunk` selon
`chunk.source_type` (`"mysql"`/`"pdf"`/... → mappé sur `"Document"` ou
`"Panne"` au niveau de la stratégie, pas dans `Chunk` lui-même qui reste
générique).

### 6.2 `QdrantStorage`

| Paramètre | Défaut | Rôle |
|---|---:|---|
| `host` | `"localhost"` | hôte Qdrant |
| `port` | `6333` | port Qdrant |
| `collection_name` | `"gmao_chunks"` | voir script de création de collection |
| `batch_size` | `100` | taille de lot par `upsert` |

Payload écrit : `id_chunk`, `type_source`, `id_equipement` uniquement
(voir échange précédent — pas de duplication de `contenu` ou d'IDs
récupérables via jointure MySQL).

---

## 7. Exceptions

```text
GMAOError
└── StorageError
    ├── StorageValidationError
    ├── InvalidStorageStrategyError
    ├── StorageStrategyNotRegisteredError
    ├── StorageConnectionError
    └── StorageWriteError
```

| Exception | Cas typique |
|---|---|
| `StorageValidationError` | `chunks`/`embeddings` désalignés, longueur différente, configuration invalide |
| `InvalidStorageStrategyError` | classe non conforme à `StorageStrategy` |
| `StorageStrategyNotRegisteredError` | nom de stratégie inconnu dans `strategy_sequence` |
| `StorageConnectionError` | MySQL ou Qdrant injoignable |
| `StorageWriteError` | échec bloquant pendant l'écriture (hors échec par item, qui va dans `StorageOutcome`) |

---

## 8. Ajouter une stratégie de storage

1. Hériter de `StorageStrategy`.
2. Implémenter `name`, `supports()`, `save()`, `delete()`.
3. `save()` ne lève jamais pour un échec par item — retourner un
   `StorageOutcome` avec le détail succès/échec.
4. Ajouter la classe au tuple `ALL_STRATEGIES` de `strategies/__init__.py`.
5. Décider sa position dans `strategy_sequence` par défaut : toute
   stratégie qui **génère** un identifiant partagé (comme MySQL ici) doit
   être avant toute stratégie qui le **consomme**.

---

## 9. Bonnes pratiques

- Toujours embedder avant de stocker : l'entrée attendue est
  `Sequence[Chunk]` + `Sequence[Embedding]` alignées, jamais l'un sans
  l'autre.
- Ne jamais faire porter `qdrant_point_id` par une colonne séparée
  synchronisée à la main : réutiliser `id_chunk` (MySQL) comme ID de
  point Qdrant élimine une classe entière de bugs de désynchronisation.
- Traiter `statut_embedding` comme la seule source de vérité sur l'état
  d'indexation — ne jamais dupliquer cette information côté Qdrant.
- Exécuter `reconcile_pending()` en job planifié, jamais en best-effort
  dans le chemin de requête utilisateur.
- Garder le payload Qdrant minimal (§6.2) : tout champ récupérable via
  `id_chunk` en une requête MySQL ne doit pas être dupliqué.

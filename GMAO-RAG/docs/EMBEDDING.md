# Référence — Module `app.embedding`

> **Objectif de ce document** : fournir une référence autonome de la couche
> d'embedding du projet **GMAO-RAG**, pour les développeurs et les
> assistants IA qui doivent l'utiliser ou l'étendre sans relire l'ensemble
> du code source.
>
> Le module reçoit une liste de `Chunk` produite par `app.chunker` et
> retourne une liste ordonnée d'`Embedding`. Il ne charge pas de données,
> ne parse pas les formats, ne découpe pas de texte et n'accède pas au
> Vector Store.
>
> Document complémentaire à `EXCEPTIONS.md`, `CHUNKER.md`, `PARSER.md` et
> `DATA_SOURCES.md`.

---

## 1. Vue d'ensemble

`app.embedding` est le quatrième et dernier étage du pipeline RAG :

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
      Vector Store / Retrieval
```

Sa responsabilité est de transformer chaque `Chunk` en un vecteur
numérique normalisé, tout en préservant le lien avec la source d'origine
et l'ordre des chunks fournis.

Le module d'embedding ne fait pas :

- de lecture de fichier ou de connexion à une base de données ;
- de parsing ou de découpage de texte ;
- de sélection de documents pour la recherche ;
- d'écriture ou de lecture dans un Vector Store.

### Composition du package

| Fichier / package | Rôle |
|---|---|
| `base.py` | contrat abstrait `EmbeddingStrategy` |
| `registry.py` | association `strategy_name` → classe de stratégie |
| `orchestrator.py` | validation, résolution et exécution de la stratégie |
| `strategies/sentence_transformer.py` | encodage local via Sentence Transformers |
| `strategies/__init__.py` | export des stratégies et tuple `ALL_STRATEGIES` |
| `__init__.py` | API publique et constructeurs de registre/orchestrateur par défaut |

### Règle d'or

> Dans le code applicatif, toujours appeler `EmbeddingOrchestrator.embed(chunks)`
> ou `build_default_orchestrator().embed(chunks)`. L'instanciation directe
> d'une stratégie est réservée aux tests ou à un besoin spécialisé
> explicitement identifié.

---

## 2. Point d'entrée public

```python
from app.embedding import build_default_orchestrator
from app.models.chunk import Chunk

chunks = [
    Chunk(
        content="Vérifier le niveau de lubrification.",
        chunk_index=0,
        source_name="manuel_maintenance.md",
        source_type="markdown",
    ),
]

orchestrator = build_default_orchestrator()
embeddings = orchestrator.embed(chunks)
```

`build_default_orchestrator()` construit un registre prérempli à partir
de `app.embedding.strategies.ALL_STRATEGIES` puis un `EmbeddingOrchestrator`
configuré sur la stratégie par défaut `"sentence-transformer"`.

| Paramètre de l'orchestrateur | Défaut | Rôle |
|---|---|---|
| `strategy_name` | `"sentence-transformer"` | nom (normalisé) de la stratégie à résoudre dans le registre |
| `**strategy_options` | — | transmis tels quels au constructeur de la stratégie résolue |

`build_default_orchestrator(**strategy_options)` transmet tout argument
nommé supplémentaire à la stratégie, par ex.
`build_default_orchestrator(device="cuda", batch_size=64)`.

---

## 3. Contrat `EmbeddingStrategy`

Toute stratégie doit hériter de `EmbeddingStrategy` et implémenter :

```python
class EmbeddingStrategy(ABC):
    @property
    def name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def supports(self, chunks: Sequence[Chunk]) -> bool: ...

    def embed(self, chunks: Sequence[Chunk]) -> list[Embedding]: ...
```

| Membre | Responsabilité |
|---|---|
| `name` | nom stable utilisé comme clé de registre |
| `model_name` | identifiant du modèle utilisé |
| `dimension` | dimensionnalité des vecteurs produits |
| `supports()` | test de compatibilité sans lancer l'encodage |
| `embed()` | retourne les `Embedding` dans le même ordre que `chunks` |

Une stratégie doit lever une sous-classe d'`EmbeddingError` pour les
erreurs métier. Elle doit retourner exactement `list[Embedding]`, un
élément par chunk, dans le même ordre.

---

## 4. `EmbeddingRegistry`

`EmbeddingRegistry` stocke des **classes** de stratégies, pas des
instances. Contrairement à `ChunkerRegistry` (routage par `source_type`,
plusieurs types par stratégie), une stratégie d'embedding est enregistrée
sous un **unique** nom : `instance.name`.

```python
from app.embedding import EmbeddingRegistry
from app.embedding.strategies import SentenceTransformerEmbedding

registry = EmbeddingRegistry()
registry.register(SentenceTransformerEmbedding)

registry.get("sentence-transformer")       # -> SentenceTransformerEmbedding
registry.has("SENTENCE-TRANSFORMER")        # -> True (normalisé)
registry.supported_strategies()             # -> tuple triée
```

| Méthode | Effet |
|---|---|
| `register(strategy_class)` | instancie la classe avec ses défauts pour lire `.name`, puis enregistre |
| `get(name)` | retourne la classe associée, lève `EmbeddingStrategyNotRegisteredError` sinon |
| `has(name)` | renvoie `False` sans exception pour un nom invalide ou inconnu |
| `unregister(name)` | retire le mapping, lève `EmbeddingStrategyNotRegisteredError` si absent |
| `clear()` | retire tous les mappings |
| `supported_strategies()` | retourne les noms enregistrés, triés |

`register()` échoue avec `EmbeddingValidationError` si le nom est déjà
pris par une autre classe, et avec `InvalidEmbeddingStrategyError` si la
classe n'hérite pas d'`EmbeddingStrategy` ou ne peut pas être instanciée
sans argument.

---

## 5. `EmbeddingOrchestrator`

```text
list[Chunk]
      ↓
validation (séquence non vide de Chunk)
      ↓
EmbeddingRegistry.get(strategy_name)
      ↓
instanciation de la stratégie avec **strategy_options
      ↓
strategy.supports(chunks)
      ↓
strategy.embed(chunks)
      ↓
validation de list[Embedding] (même longueur, même ordre, type Embedding)
```

Une nouvelle stratégie instanciée à chaque appel à `embed()` — l'état
lourd (le modèle chargé en mémoire) est mis en cache **au niveau classe**
par la stratégie elle-même (voir §6), donc réutiliser l'orchestrateur
pour plusieurs appels successifs ne recharge pas le modèle.

---

## 6. Stratégie `SentenceTransformerEmbedding`

Encode les chunks localement avec un modèle
[Sentence Transformers](https://www.sbert.net/), chargé paresseusement au
premier appel qui en a besoin (`embed()` ou l'accès à `.dimension` pour un
modèle non défini par défaut).

| Paramètre | Défaut | Rôle |
|---|---|---|
| `model_name` | `"intfloat/multilingual-e5-small"` | modèle Hugging Face à charger |
| `model_revision` | commit épinglé (`DEFAULT_MODEL_REVISION`) | révision figée pour la reproductibilité ; passer `None` explicitement pour utiliser `"main"` (flottant) |
| `batch_size` | `32` | taille de lot pour `model.encode()` |
| `normalize_embeddings` | `True` | normalisation L2 des vecteurs |
| `device` | `"auto"` | `"auto"`, `"cpu"` ou `"cuda"` |
| `document_prefix` | `"passage: "` | préfixe requis par le modèle E5 pour les documents indexés |

> Le modèle E5 par défaut attend `"passage: "` pour les documents indexés
> et `"query: "` pour les requêtes. `SentenceTransformerEmbedding.embed_query(
> query)` encode une requête avec ce second préfixe et retourne un
> `tuple[float, ...]` normalisé. Cette méthode utilise le même modèle que
> `embed()` ; elle ne crée pas de nouvel objet `Embedding`, car une requête
> n'est pas rattachée à un `Chunk`.

```python
strategy = SentenceTransformerEmbedding()
passage_embeddings = strategy.embed(chunks)
query_vector = strategy.embed_query("Pourquoi le moteur vibre-t-il ?")

assert len(query_vector) == passage_embeddings[0].dimension
```

### Cache modèle

Le modèle chargé (`sentence_transformers.SentenceTransformer`) est mis en
cache dans un dictionnaire **de classe**, `_model_cache`, sous la clé
`(model_name, model_revision, device)`. Toutes les instances de
`SentenceTransformerEmbedding` partageant la même clé réutilisent le même
modèle en mémoire ; `embed()` et `embed_query()` utilisent donc exactement
la même instance, sans rechargement.

Le chargement effectif d'un modèle est protégé par un verrou **propre à
sa clé de cache** (double-checked locking) : le chargement d'un modèle A
ne bloque jamais la lecture du cache ou le chargement d'un modèle B sous
une clé différente. Un verrou de classe distinct (`_cache_lock`) protège
uniquement la création de ces verrous par clé, jamais le chargement du
modèle lui-même.

`clear_model_cache()` vide le cache et les verrous associés — utile
principalement pour isoler des tests.

### Dimension

`dimension` est connue statiquement (`384`) pour le modèle par défaut.
Pour tout autre `model_name`, elle est résolue en interrogeant le modèle
chargé (`model.get_sentence_embedding_dimension()`), ce qui déclenche donc
le chargement du modèle dès le premier accès à `.dimension`, même sans
appeler `embed()`.

---

## 7. Modèle `Embedding` et métadonnées

Chaque appel à `embed()` retourne une liste d'`app.models.embedding.Embedding`.

| Champ | Signification |
|---|---|
| `chunk_id` | `chunk.chunk_id` si présent, sinon `"{source_name}:{chunk_index}"` |
| `vector` | tuple de floats, longueur égale à `dimension` |
| `model_name` | identifiant du modèle utilisé |
| `dimension` | dimensionnalité du vecteur |
| `metadata` | copie des métadonnées du chunk, enrichie par la stratégie |

`SentenceTransformerEmbedding` ajoute à `metadata` :

```python
{
    "embedding_strategy": "sentence-transformer",
    "embedding_model": ...,
    "embedding_model_revision": ...,
    "embedding_dimension": ...,
    "normalize_embeddings": ...,
}
```

---

## 8. Exceptions

```text
GMAOError
└── EmbeddingError
    ├── EmbeddingValidationError
    ├── InvalidEmbeddingStrategyError
    ├── EmbeddingStrategyNotRegisteredError
    ├── EmbeddingModelError
    └── EmbeddingEncodingError
```

| Exception | `error_code` | HTTP | Cas typique |
|---|---|---|---|
| `EmbeddingError` | `EMBEDDING_ERROR` | 500 | Base générique, ne pas lever directement en général |
| `EmbeddingValidationError` | `EMBEDDING_VALIDATION_ERROR` | 400 | Chunks invalides, configuration invalide, chunks non supportés par la stratégie |
| `InvalidEmbeddingStrategyError` | `EMBEDDING_INVALID_STRATEGY` | 500 | Classe non conforme à `EmbeddingStrategy` |
| `EmbeddingStrategyNotRegisteredError` | `EMBEDDING_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu |
| `EmbeddingModelError` | `EMBEDDING_MODEL_ERROR` | 500 | Dépendance manquante, échec de chargement du modèle, dimension invalide |
| `EmbeddingEncodingError` | `EMBEDDING_ENCODING_ERROR` | 500 | Échec d'encodage, nombre de vecteurs incohérent, vecteur invalide |

---

## 9. Ajouter une stratégie

1. Hériter d'`EmbeddingStrategy`.
2. Implémenter `name`, `model_name`, `dimension`, `supports()`, `embed()`.
3. Valider la configuration dans `__init__` et lever
   `EmbeddingValidationError` si nécessaire.
4. Retourner une `list[Embedding]` ordonnée, une par chunk.
5. Copier les métadonnées du chunk et ajouter les informations propres à
   la stratégie.
6. Encapsuler les erreurs imprévues dans une sous-classe d'`EmbeddingError`.
7. Ajouter la classe au tuple `ALL_STRATEGIES` de `strategies/__init__.py`
   pour qu'elle soit enregistrée par défaut via `build_default_registry()` —
   c'est la seule modification nécessaire, `build_default_registry()`
   n'a jamais besoin d'être modifiée.

---

## 10. Bonnes pratiques

- Toujours chunker avant d'embedder : l'entrée attendue est
  `Sequence[Chunk]`, jamais `ParsedDocument` ou une simple chaîne.
- Réutiliser un même `EmbeddingOrchestrator` (ou au moins des paramètres
  de stratégie identiques) pour bénéficier du cache modèle au niveau
  classe.
- Épingler `model_revision` en production pour la reproductibilité ; ne
  passer `model_revision=None` (→ `"main"`) que si le flottant est
  explicitement souhaité.
- Garder `document_prefix` cohérent avec le modèle utilisé — un modèle E5
  sans son préfixe `"passage: "` dégrade la qualité de la recherche.
- Conserver les métadonnées de provenance dans chaque `Embedding` : elles
  sont nécessaires au filtrage et à l'explication des résultats de
  retrieval.

# Référence — Module `app.retrieval`

> **Objectif de ce document** : fournir une référence autonome de la couche
> de recherche (*retrieval*) du projet **GMAO-RAG**, pour les développeurs
> et les assistants IA qui doivent l'utiliser ou l'étendre sans relire
> l'ensemble du code source.
>
> Le module reçoit une requête utilisateur (texte libre), l'encode en
> vecteur via `app.embedding`, recherche les chunks les plus proches dans
> Qdrant, hydrate les résultats depuis MySQL, et retourne un
> `RetrievalReport` ordonné par pertinence. Il ne charge pas de données,
> ne parse pas les formats, ne découpe pas de texte et ne calcule pas
> d'embeddings pour l'indexation.
>
> Document complémentaire à `EXCEPTIONS.md`, `EMBEDDING.md` et
> `STORAGE.md`.

---

## 1. Vue d'ensemble

`app.retrieval` est le sixième étage du pipeline RAG (phase de lecture) :

```text
       Requête utilisateur (texte libre)
                    ↓
         app.retrieval.orchestrator
                    ↓
         EmbeddingRegistry → embed_query(query)
                    ↓
              query_vector
                    ↓
       ┌───────────────────────────┐
       │  RetrievalStrategy        │
       │  ┌─────────────────────┐  │
       │  │ QdrantVectorRetrieval│──┼──→ Qdrant (recherche vectorielle)
       │  │   ou                │  │
       │  │ HybridRetrieval     │──┼──→ Qdrant + MySQL (RRF fusion)
       │  └─────────────────────┘  │
       └───────────────────────────┘
                    ↓
         MySQL (_hydrate : contenu, IDs parent, noms)
                    ↓
         RetrievalReport(results=[RetrievedChunk, ...])
```

Sa responsabilité est de transformer une question en une liste ordonnée
de chunks pertinents, en combinant si nécessaire recherche vectorielle
et recherche lexicale, tout enhydratant les métadonnées complètes depuis
MySQL.

Le module de retrieval ne fait pas :

- de lecture de fichier ou de connexion à une source de données amont ;
- de parsing, de découpage de texte ou de calcul d'embeddings
  d'indexation ;
- d'écriture dans Qdrant ou MySQL ;
- de génération de réponses — il retourne des chunks, pas des réponses.

### Composition du package

| Fichier / package | Rôle |
|---|---|
| `base.py` | contrat abstrait `RetrievalStrategy` |
| `registry.py` | association `strategy_name` → classe de stratégie |
| `orchestrator.py` | validation, encodage query, résolution stratégie, seuil score |
| `strategies/qdrant_retrieval.py` | recherche vectorielle Qdrant + hydration MySQL |
| `strategies/hybrid_retrieval.py` | fusion vectorielle + lexicale (RRF), dégradation gracieuse |
| `strategies/__init__.py` | export des stratégies et tuple `ALL_STRATEGIES` |
| `__init__.py` | API publique et constructeurs de registre/orchestrateur par défaut |
| `app/models/retrieval.py` | modèles `RetrievalFilter`, `RetrievedChunk`, `RetrievalReport` |
| `app/exceptions/retrieval.py` | hiérarchie d'exceptions dédiée (voir §9) |

### Règle d'or

> Dans le code applicatif, toujours appeler
> `RetrievalOrchestrator.retrieve(query)` ou
> `build_default_orchestrator().retrieve(query)`. L'instanciation directe
> d'une stratégie est réservée aux tests ou à un besoin spécialisé
> explicitement identifié.

---

## 2. Point d'entrée public

```python
from app.retrieval import build_default_orchestrator
from app.models.retrieval import RetrievalFilter

orchestrator = build_default_orchestrator()

report = orchestrator.retrieve(
    "Pourquoi la pompe vibre-t-elle ?",
    top_k=10,
    filters=RetrievalFilter(id_equipement=42),
)

for chunk in report.results:
    print(f"[{chunk.score:.3f}] {chunk.source_name}: {chunk.content[:80]}...")
```

`build_default_orchestrator(**options)` construit un registre prérempli
(`qdrant` puis `hybrid`) via `build_default_registry()`, un registre
d'embedding prérempli, puis un `RetrievalOrchestrator` configuré sur la
stratégie par défaut `"qdrant"`.

| Paramètre de l'orchestrateur | Défaut | Rôle |
|---|---|---|
| `strategy_name` | `"qdrant"` | nom de la stratégie de retrieval par défaut |
| `embedding_strategy_name` | `"sentence-transformer"` | nom de la stratégie d'encoding des requêtes |
| `embedding_options` | `None` | options transmises au constructeur de l'encodeur (**doivent** correspondre à l'indexation) |
| `default_top_k` | `5` | nombre de résultats par défaut |
| `max_top_k` | `50` | plafond absolu de résultats (truncation) |
| `score_threshold` | `None` | seuil minimal de score ; `None` désactive le filtrage |
| `**strategy_options` | — | transmis tels quels au constructeur de la stratégie résolue |

`build_default_orchestrator(**options)` transmet tout argument nommé
supplémentaire à la stratégie, par ex.
`build_default_orchestrator(collection_name="custom_collection")`.

---

## 3. Contrat `RetrievalStrategy`

Toute stratégie doit hériter de `RetrievalStrategy` et déclarer un
attribut de classe `name` non vide :

```python
class RetrievalStrategy(ABC):
    name: str = ""  # attribut de CLASSE, pas une @property

    def supports(self, filters: RetrievalFilter) -> bool: ...

    def retrieve(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int,
        filters: RetrievalFilter,
        query_text: str,
    ) -> list[RetrievedChunk]: ...
```

| Membre | Responsabilité |
|---|---|
| `name` | nom stable de la stratégie, lu **sans instanciation** par le registre |
| `supports()` | test de compatibilité sans effet de bord |
| `retrieve()` | exécute la recherche et retourne les `RetrievedChunk` ordonnés |

`name` est un attribut de classe (pas une `@property`) pour que le
registre puisse le lire sans instancier la stratégie — instancier
`QdrantVectorRetrieval` ouvre une connexion Qdrant et MySQL (voir §6).
`__init_subclass__` valide à la **définition** de la classe que `name`
est une chaîne non vide — une sous-classe mal formée échoue au chargement
du module, pas au premier appel.

Le `query_vector` est fourni par l'orchestrateur via `embed_query()` — la
stratégie ne doit **jamais** encoder la requête elle-même. Le
`query_text` est transmis tel quel pour les stratégies hybrides qui
effectuent une recherche lexicale en plus de la recherche vectorielle.

Une stratégie doit lever une sous-classe de `RetrievalError` pour toute
erreur métier, et ne jamais laisser fuiter une exception Qdrant ou
SQLAlchemy brute.

---

## 4. `RetrievalRegistry`

`RetrievalRegistry` stocke des **classes** de stratégies, jamais des
instances — même principe que `EmbeddingRegistry` et `StorageRegistry`.

```python
from app.retrieval import RetrievalRegistry
from app.retrieval.strategies import QdrantVectorRetrieval, HybridRetrieval

registry = RetrievalRegistry()
registry.register(QdrantVectorRetrieval)
registry.register(HybridRetrieval)

registry.get("qdrant")          # -> QdrantVectorRetrieval (classe)
registry.has("HYBRID")           # -> True (normalisé)
registry.supported_strategies()   # -> ("hybrid", "qdrant")
```

| Méthode | Effet |
|---|---|
| `register(strategy_class)` | enregistre la classe sous `strategy_class.name` normalisé ; **aucune instanciation** |
| `get(name)` | retourne la classe, lève `RetrievalStrategyNotRegisteredError` sinon |
| `has(name)` | renvoie `False` sans exception pour un nom invalide ou inconnu |
| `unregister(name)` | retire le mapping ; lève `RetrievalStrategyNotRegisteredError` si absent |
| `clear()` | retire tous les mappings |
| `supported_strategies()` | retourne les noms enregistrés, triés |

`register()` échoue avec `InvalidRetrievalStrategyError` si la classe
n'hérite pas de `RetrievalStrategy`, et avec `RetrievalValidationError`
si le nom est déjà pris par une autre classe.

---

## 5. `RetrievalOrchestrator`

```text
query (str)
      ↓
validation (chaîne non vide)
      ↓
EmbeddingRegistry.get(embedding_strategy_name)
      ↓
instanciation de l'encodeur + embed_query(query) → query_vector
      ↓
RetrievalRegistry.get(strategy_name)
      ↓
instanciation de la stratégie avec **strategy_options
      ↓
strategy.supports(filters)
      ↓
strategy.retrieve(query_vector, top_k, filters, query_text)
      ↓
filtrage par score_threshold (si défini)
      ↓
RetrievalReport(query, strategy_name, results, total_candidates)
```

### 5.1 Encodage de la requête

L'orchestrateur utilise **toujours** l'encodeur de requêtes
(`embed_query`), jamais l'encodeur de passages (`embed`). Cette
distinction est critique : les modèles E5 utilisent des préfixes
différents pour les documents indexés (`"passage: "`) et les requêtes
(`"query: "`). Utiliser le mauvais encodeur produit des vecteurs dans des
espaces vectoriels incompatibles, dégradant massivement la qualité de la
recherche.

### 5.2 `embedding_options` (critical)

.. important::

   `embedding_options` **doit** reproduire exactement les options utilisées
   lors de l'indexation (model_name, model_revision, device, prefixes…).
   Une divergence produit un vecteur de requête dans un espace vectoriel
   différent — la vérification de dimension ne détecte pas cette dérive.

   Idéalement, `app.embedding` et `app.retrieval` partagent la même source
   de vérité (variables d'environnement communes).

### 5.3 Truncation et seuil

- `effective_top_k = min(top_k or default_top_k, max_top_k)` : le
  plafond `max_top_k` est appliqué **avant** la requête, pour limiter le
  coût Qdrant/MySQL.
- `score_threshold` est appliqué **après** la récupération : seuls les
  chunks dont `score >= score_threshold` sont conservés dans le rapport.
  Le champ `total_candidates` du `RetrievalReport` reflète le nombre de
  résultats **avant** filtrage par seuil.

### 5.4 Politique d'erreur

Toute exception `GMAOError` (et sous-classes) est propagée telle quelle.
Toute autre exception inattendue est encapsulée dans un
`RetrievalExecutionError` avec `original=exc` pour préserver la cause
racine.

---

## 6. Stratégie `QdrantVectorRetrieval`

Recherche vectorielle dans Qdrant avec hydration MySQL pour récupérer le
contenu et les métadonnées complètes.

### 6.1 Architecture deux phases

Qdrant ne stocke que `id_chunk`, `type_source` et `id_equipement` dans
son payload — pas le contenu texte ni les IDs parent (`id_document`,
`id_panne`). La recherche se déroule donc en deux phases :

1. **Qdrant** : recherche vectorielle Approximate Nearest Neighbor (ANN)
   → retourne les IDs des points les plus proches avec leur score.
2. **MySQL** (`_hydrate`) : un seul `SELECT` avec `IN (:ids)` récupère
   le contenu, les noms de source et les IDs parent pour chaque chunk.

Les filtres applicables à chaque phase dépendent des données disponibles :

| Filtre | Qdrant (`_filter`) | MySQL (`_hydrate`) |
|---|---|---|
| `id_equipement` | `MatchValue` sur le payload | `COALESCE(d.id_equipement, p.id_equipement) = :id` |
| `source_type` | `MatchValue` sur `type_source` (coarse) | `LOWER(COALESCE(d.type_fichier, 'panne')) = :source_type` |
| `id_document` | coarse : `type_source == "Document"` | `d.id_document = :id_document` (exact) |
| `id_panne` | coarse : `type_source == "Panne"` | `p.id_panne = :id_panne` (exact) |
| `min_score` | — | filtrage post-requête dans `retrieve()` |

Lorsque `id_document` et `id_panne` sont tous deux définis, aucun filtre
coarse n'est appliqué dans Qdrant (ambiguïté) — le filtrage exact est
délégué entièrement à MySQL.

### 6.2 Paramètres

| Paramètre | Défaut | Rôle |
|---|---|---|
| `collection_name` | `os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks")` | nom de la collection Qdrant |
| `host` | `os.getenv("QDRANT_HOST", "localhost")` | hôte Qdrant |
| `port` | `int(os.getenv("QDRANT_PORT", "6333"))` | port Qdrant |
| `dsn` | `os.getenv("MYSQL_DSN")` ou construction depuis `GMAO_DB_*` | DSN MySQL pour l'hydration |

Le DSN MySQL est résolu dans cet ordre : paramètre `dsn` explicite →
variable `MYSQL_DSN` → construction automatique depuis `GMAO_DB_HOST`,
`GMAO_DB_USER`, `GMAO_DB_PASSWORD`, `GMAO_DB_PORT`, `GMAO_DB_NAME`.

### 6.3 Compatibilité dimension

Avant d'exécuter la requête, la stratégie vérifie que la dimension du
`query_vector` correspond à la dimension de la collection Qdrant.

**Collections à vecteurs nommés** : si `vectors` est un `dict` (vecteurs
nommés), la vérification utilise la première entrée. Un dict vide lève
`RetrievalExecutionError`.

Un mismatch lève `IncompatibleEmbeddingModelError` — cela arrive quand le
modèle d'embedding utilisé pour l'indexation diffère de celui utilisé pour
la requête.

### 6.4 `supports()`

Toujours `True` : `QdrantVectorRetrieval` accepte tous les filtres.
Les filtres non supportés par Qdrant sont délégués à MySQL dans
`_hydrate()`.

### 6.5 Cache de connexions

Le `QdrantClient` et le moteur SQLAlchemy sont mis en cache au niveau
de la classe (dict + verrou par clé) pour éviter de recréer une connexion
à chaque appel. `load_dotenv()` n'est exécuté qu'une fois au
chargement du module, pas à chaque instanciation.

### 6.6 DSN absent

Si `MYSQL_DSN` n'est pas configuré, `_hydrate()` lève
`RetrievalValidationError` (erreur de configuration, pas erreur de
connexion). `RetrievalConnectionError` est réservée aux échecs réels de
`create_engine(...).connect()`.

### 6.7 Limites du filtre `id_document`/`id_panne`

.. note::

   Le filtrage par `id_document` / `id_panne` est appliqué **après** que
   Qdrant a tronqué les candidats à `top_k` (même avec oversampling ×4).
   Avec un `top_k` faible et un document ciblé, il est possible qu'aucun
   chunk Qdrant n'appartienne au document demandé — la méthode retournera
   une liste vide ou incomplète sans erreur. L'oversampling ×4 atténue
   ce risque sans l'éliminer. Pour un filtrage garanti, augmenter `top_k`
   ou passer par `HybridRetrieval` (qui applique le filtre en SQL).

---

## 7. Stratégie `HybridRetrieval`

Fusionne les résultats de la recherche vectorielle (Qdrant) et de la
recherche lexicale (MySQL `LIKE`) via *Reciprocal Rank Fusion* (RRF).
En cas d'échec MySQL, dégrade gracieusement vers la recherche
vectorielle seule.

### 7.1 Paramètres

| Paramètre | Défaut | Rôle |
|---|---|---|
| `rrf_k` | `60` | paramètre de lissage RRF (plus grand = moins de poids aux top résultats) |
| `**options` | — | transmis à `QdrantVectorRetrieval` (collection_name, host, port, dsn) |

### 7.2 Algorithme RRF

Pour chaque chunk présent dans au moins un des deux sources :

```
score_rrf = Σ 1 / (rrf_k + rank_i)
```

où `rank_i` est le rang (1-indexé) du chunk dans chaque source. Un chunk
présent dans les deux sources aura un score plus élevé qu'un chunk
présent dans une seule source. `rrf_k = 60` est la valeur standard de la
littérature.

### 7.3 Fusion et déduplication

```python
merged: dict[chunk_id, (RetrievedChunk, score_rrf, debug_dict)]
```

Les deux sources sont fusionnées par `chunk_id`. Le `RetrievedChunk`
retourné est celui de la première source rencontrée (vectorielle en
priorité). Les rangs originaux sont préservés dans `metadata` :

```python
{
    "retrieval_debug": {
        "vector_rank": 3,     # présent dans la source vectorielle
        "lexical_rank": 7,    # présent dans la source lexicale
    }
}
```

Si la recherche lexicale échoue (MySQL injoignable uniquement — pas les
erreurs de validation), la dégradation gracieuse ajoute uniquement le
champ `vector_rank` dans `retrieval_debug` (le champ `lexical_rank` absent
suffit à signaler que le mode lexical n'a pas contribué).

### 7.4 Recherche lexicale (`_lexical`)

Effectue un `LIKE '%query_text%'` sur `chunk_rag.contenu`, avec jointures
vers `document` et `panne` pour appliquer les filtres. Tous les filtres
de `RetrievalFilter` sont supportés en MySQL, y compris `id_document`,
`id_panne`, `id_equipement` et `source_type`.

**Échappement LIKE** : les caractères `%`, `_` et `\` dans `query_text`
sont échappés avant construction du motif, avec la clause
`ESCAPE '\\'`. Cela évite les wildcards involontaires.

**DSN absent** : si `MYSQL_DSN` n'est pas configuré, `_lexical()` lève
`RetrievalValidationError` (configuration), pas `RetrievalConnectionError`.
La dégradation gracieuse dans `retrieve()` ne catch que
`RetrievalConnectionError` et `RetrievalExecutionError` — les erreurs de
validation remontent normalement.

Le score attribué aux résultats lexiaux est `1.0 / rank` (ordre de
grandeur), mais ce score n'est **jamais** utilisé directement : seul le
score RRF compte pour le classement final.

### 7.5 `supports()`

Délègue à `QdrantVectorRetrieval.supports()` (toujours `True`).

---

## 8. Modèles de données

### 8.1 `RetrievalFilter`

Contraintes optionnelles appliquées aux résultats de recherche.

| Champ | Type | Défaut | Validation |
|---|---|---|---|
| `id_document` | `int \| None` | `None` | entier strictement positif |
| `id_panne` | `int \| None` | `None` | entier strictement positif |
| `id_equipement` | `int \| None` | `None` | entier strictement positif |
| `source_type` | `str \| None` | `None` | chaîne non vide, normalisée en minuscules |
| `min_score` | `float \| None` | `None` | nombre fini |

`RetrievalFilter` est un dataclass `frozen=True` — les instances sont
immuables après création. `source_type` est normalisé (`strip().lower()`)
lors de l'initialisation.

### 8.2 `RetrievedChunk`

Un chunk retourné par une stratégie de recherche.

| Champ | Type | Signification |
|---|---|---|
| `chunk_id` | `str` | identifiant du chunk (converti depuis `id_chunk` MySQL) |
| `content` | `str` | texte du chunk |
| `score` | `float` | score de pertinence (RRF pour hybrid, score Qdrant pour vectoriel) |
| `rank` | `int` | rang final (1-indexé, après fusion et filtrage) |
| `source_name` | `str` | nom du fichier ou identifiant panne |
| `source_type` | `str` | type de source (`"document"`, `"panne"`, etc.) |
| `id_document` | `int \| None` | ID du document parent (si applicable) |
| `id_panne` | `int \| None` | ID de la panne parente (si applicable) |
| `id_equipement` | `int \| None` | ID de l'équipement lié |
| `metadata` | `dict[str, Any]` | métadonnées de debug (rangs par source, etc.) |
| `retrieval_strategy` | `str` | nom de la stratégie ayant produit le chunk |

`RetrievedChunk` est un dataclass `frozen=True` — les instances sont
immuables. `chunk_id` est une chaîne (converti depuis l'entier MySQL
`id_chunk`), pas un identifiant brut.

### 8.3 `RetrievalReport`

Rapport ordonné d'une seule requête utilisateur.

| Champ | Type | Signification |
|---|---|---|
| `query` | `str` | requête texte nettoyée (trim) |
| `strategy_name` | `str` | stratégie utilisée (normalisée) |
| `results` | `tuple[RetrievedChunk, ...]` | résultats ordonnés par pertinence décroissante |
| `total_candidates` | `int` | nombre de résultats **avant** filtrage par `score_threshold` |

Propriété `is_empty` : `True` si `results` est vide.

---

## 9. Exceptions

```text
GMAOError
└── RetrievalError
    ├── RetrievalValidationError
    │   └── EmptyQueryError
    ├── InvalidRetrievalStrategyError
    ├── RetrievalStrategyNotRegisteredError
    ├── RetrievalConnectionError
    ├── RetrievalExecutionError
    └── IncompatibleEmbeddingModelError
```

| Exception | `error_code` | HTTP | Cas typique |
|---|---|---|---|
| `RetrievalError` | `RETRIEVAL_ERROR` | 500 | Base générique, ne pas lever directement |
| `RetrievalValidationError` | `RETRIEVAL_VALIDATION_ERROR` | 400 | Configuration invalide, top_k/filtres/strategy_name invalides |
| `EmptyQueryError` | `RETRIEVAL_EMPTY_QUERY` | 400 | Requête vide ou constituée uniquement d'espaces |
| `InvalidRetrievalStrategyError` | `RETRIEVAL_INVALID_STRATEGY` | 500 | Classe non conforme à `RetrievalStrategy` |
| `RetrievalStrategyNotRegisteredError` | `RETRIEVAL_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `RetrievalConnectionError` | `RETRIEVAL_CONNECTION_ERROR` | 500 | Échec de connexion Qdrant ou MySQL |
| `RetrievalExecutionError` | `RETRIEVAL_EXECUTION_ERROR` | 500 | Échec d'exécution de la requête (Qdrant ou MySQL) |
| `IncompatibleEmbeddingModelError` | `RETRIEVAL_INCOMPATIBLE_EMBEDDING_MODEL` | 400 | Dimension du query_vector ≠ dimension de la collection Qdrant |

**Distinction connexion / exécution** : `RetrievalConnectionError` est
réservée aux échecs d'établissement de connexion (host injoignable, DSN
absent). `RetrievalExecutionError` couvre les échecs survenant pendant
l'exécution d'une requête sur une connexion déjà établie (timeout,
erreur de syntaxe SQL, etc.).

---

## 10. Ajouter une stratégie

1. Hériter de `RetrievalStrategy`.
2. Déclarer `name` comme **attribut de classe** non vide.
3. Ne rien faire de coûteux ou de risqué (connexion réseau, lecture
   d'environnement) en dehors de `__init__`.
4. Implémenter `supports()` sans effet de bord.
5. Implémenter `retrieve()` : valider via `supports()`, encapsuler
   toute exception tierce dans `RetrievalConnectionError` (connexion) ou
   `RetrievalExecutionError` (exécution), retourner une liste de
   `RetrievedChunk` ordonnée par rang décroissant.
6. Ne jamais encoder la requête dans la stratégie — le `query_vector`
   est fourni par l'orchestrateur.
7. Ajouter la classe au tuple `ALL_STRATEGIES` de
   `strategies/__init__.py` pour qu'elle soit enregistrée par défaut.

---

## 11. Bonnes pratiques

- Toujours passer par `RetrievalOrchestrator`, jamais par une stratégie
  instanciée directement (voir §1, règle d'or).
- Utiliser le même modèle d'embedding pour la requête que pour
  l'indexation — un mismatch produit des résultats aléatoires. La
  vérification de dimension dans `QdrantVectorRetrieval` est un filet de
  sécurité, pas un substitut à la cohérence.
- Ajuster `score_threshold` avec parcimonie : un seuil trop élevé élimine
  des résultats pertinents, un seuil trop bas retourne du bruit.
- Préférer `HybridRetrieval` quand la recherche lexicale apporte une
  valeur ajoutée (recherche par mots-clés techniques, noms d'équipements).
  La dégradation gracieuse garantit que l'absence de MySQL ne casse pas
  le pipeline.
- Préférer `QdrantVectorRetrieval` pour les cas simples ou quand MySQL
  n'est pas disponible — le module fonctionne avec Qdrant seul si le DSN
  n'est pas configuré (la recherche hybride échouera mais la vectorielle
  fonctionnera).
- Conserver les métadonnées `retrieval_debug` dans les résultats : elles
  permettent de diagnostiquer la contribution de chaque source dans un
  score hybride.
- Le `RetrievalReport.total_candidates` reflète le nombre de résultats
  **avant** filtrage par `score_threshold` — utile pour comprendre si un
  faible nombre de résultats est dû au seuil ou à la requête elle-même.

---

## 12. Changelog

### v2 (correction)

- **§1.1** — `embedding_options` ajouté à `RetrievalOrchestrator` pour
  configurer l'encodeur de requête avec les mêmes options que l'indexation.
- **§1.2** — Limite documentée : filtre `id_document`/`id_panne` appliqué
  après troncature Qdrant, avec oversampling ×4 pour atténuer.
- **§1.3** — Oversampling ×4 généralisé à `QdrantVectorRetrieval` pour
  éviter la troncature avant filtrage par `min_score`.
- **§1.4** — `TypeError` nu remplacé par `InvalidRetrievalStrategyError`
  dans `__init_subclass__`.
- **§1.5** — Cache de connexions `QdrantClient` et SQLAlchemy (class-level
  dict + RLock). `load_dotenv()` exécuté une seule fois au chargement.
- **§1.6** — `retrieve()` dans `QdrantVectorRetrieval` enveloppée dans la
  gestion d'erreurs complète (extraction IDs, hydratation, construction).
- **§1.7** — `except RetrievalError` dans `HybridRetrieval` remplacé par
  `except (RetrievalConnectionError, RetrievalExecutionError)`.
- **§1.8** — Code mort `lexical_unavailable` supprimé ; `vector_rank` seul
  dans `retrieval_debug` signale l'absence de mode lexical.
- **§1.9** — Caractères `%`, `_`, `\` échappés dans `_lexical()` avec
  clause `ESCAPE '\\'`.
- **§1.10** — DSN absent → `RetrievalValidationError` (pas ConnectionError)
  dans `_hydrate()` et `_lexical()`.
- **§1.11** — Collections Qdrant à vecteurs nommés (`dict`) gérées
  explicitement dans `_check_dimension()`.
- **§2.3** — `chunk_from_row()` exposé comme fonction publique partagée
  (utilisé par `QdrantVectorRetrieval` et `HybridRetrieval`).
- **§3** — Reformatage PEP8 complet (une instruction par ligne, docstrings
  sur toutes les classes et méthodes publiques).

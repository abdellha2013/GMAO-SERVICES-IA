# Référence — Module `app.reranker`

> **Objectif de ce document** : fournir une référence autonome de la couche
> de reranking (*reranking*) du projet **GMAO-RAG**, pour les développeurs
> et les assistants IA qui doivent l'utiliser ou l'étendre sans relire
> l'ensemble du code source.
>
> Le module reçoit une liste de chunks candidats (issus de `app.retrieval`),
> les évalue par paires (query, chunk) via un Cross-Encoder, et retourne
> une liste ordonnée de `RankedChunk` avec des scores de reranking.
> Il ne fait pas de recherche, ni de calcul d'embeddings, ni de génération
> de réponses.
>
> Document complémentaire à `RETRIEVAL.md`, `EXCEPTIONS.md` et `LLM.md`.

---

## 1. Vue d'ensemble

`app.reranker` est le septième étage du pipeline RAG (phase de reranking) :

```text
   RetrievalReport (chunks candidats)
              ↓
   app.reranker.orchestrator
              ↓
   RetrievalRegistry → strategy_name → CrossEncoderReranker
              ↓
   CrossEncoder model.predict(query, chunk) → scores
              ↓
   RankedChunk(results=[RankedChunk, ...])
```

Sa responsabilité est de réordonner les chunks candidats selon leur
pertinence réelle évaluée par un modèle Cross-Encoder, qui analyse
simultanément la requête et le contenu du chunk (contrairement à la
recherche vectorielle qui les encode séparément).

Le module de reranker ne fait pas :

- de recherche dans Qdrant ou MySQL ;
- de calcul d'embeddings ;
- de génération de réponses LLM ;
- de connexion réseau en dehors du chargement du modèle Cross-Encoder.

### Composition du package

| Fichier / package | Rôle |
|---|---|
| `base.py` | contrat abstrait `RerankerStrategy` |
| `registry.py` | association `strategy_name` → classe de stratégie |
| `orchestrator.py` | validation, résolution stratégie, calcul `effective_top_k` |
| `strategies/cross_encoder.py` | reranking par Cross-Encoder (sentence-transformers) |
| `strategies/__init__.py` | export des stratégies et tuple `ALL_STRATEGIES` |
| `__init__.py` | API publique et constructeurs de registre/orchestrateur par défaut |
| `app/models/reranking.py` | modèle `RankedChunk` |
| `app/exceptions/reranker.py` | hiérarchie d'exceptions dédiée (voir §9) |

### Règle d'or

> Dans le code applicatif, toujours appeler
> `RerankerOrchestrator.rerank(query, candidates)` ou
> `build_default_orchestrator().rerank(query, candidates)`. L'instanciation
> directe d'une stratégie est réservée aux tests ou à un besoin spécialisé
> explicitement identifié.

---

## 2. Point d'entrée public

```python
from app.reranker import build_default_orchestrator
from app.models.retrieval import RetrievedChunk

orchestrator = build_default_orchestrator()

ranked = orchestrator.rerank(
    "Pourquoi la pompe vibre-t-elle ?",
    candidates=chunks,  # list[RetrievedChunk]
    top_k=5,
)

for chunk in ranked:
    print(f"[{chunk.rerank_score:.3f}] {chunk.source_name}: {chunk.content[:80]}...")
```

`build_default_orchestrator(**options)` construit un registre prérempli
(`cross-encoder`) via `build_default_registry()`, puis un
`RerankerOrchestrator` configuré sur la stratégie par défaut
`"cross-encoder"`.

| Paramètre de l'orchestrateur | Défaut | Rôle |
|---|---|---|
| `strategy_name` | `"cross-encoder"` | nom de la stratégie de reranking par défaut |
| `default_top_k` | `10` | nombre de résultats par défaut |
| `max_top_k` | `50` | plafond absolu de résultats (truncation) |
| `**strategy_options` | — | transmis tels quels au constructeur de la stratégie résolue |

`build_default_orchestrator(**options)` transmet tout argument nommé
supplémentaire à la stratégie, par ex.
`build_default_orchestrator(model_name="custom-model")`.

---

## 3. Contrat `RerankerStrategy`

Toute stratégie doit hériter de `RerankerStrategy` et déclarer un
attribut de classe `name` non vide :

```python
class RerankerStrategy(ABC):
    name: str = ""  # attribut de CLASSE, pas une @property

    def supports(self, query: str, candidates: Sequence[RetrievedChunk]) -> bool: ...

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
        *,
        top_k: int,
        **kwargs: Any,
    ) -> list[RankedChunk]: ...
```

| Membre | Responsabilité |
|---|---|
| `name` | nom stable de la stratégie, lu **sans instanciation** par le registre |
| `supports()` | test de compatibilité sans effet de bord |
| `rerank()` | exécute le reranking et retourne les `RankedChunk` ordonnés |

`name` est un attribut de classe (pas une `@property`) pour que le
registre puisse le lire sans instancier la stratégie. `__init_subclass__`
valide à la **définition** de la classe que `name` est une chaîne non
vide — une sous-classe mal formée échoue au chargement du module avec
`InvalidRerankerStrategyError`.

Le `query` est fourni tel quel par l'orchestrateur. Les `candidates`
sont les `RetrievedChunk` issus de la couche retrieval. Le `top_k`
est calculé par l'orchestrateur (`effective_top_k`).

Une stratégie doit lever une sous-classe de `RerankerError` pour toute
erreur métier, et ne jamais laisser fuiter une exception tierce brute.

---

## 4. `RerankerRegistry`

`RerankerRegistry` stocke des **classes** de stratégies, jamais des
instances — même principe que `RetrievalRegistry`.

```python
from app.reranker import RerankerRegistry
from app.reranker.strategies import CrossEncoderReranker

registry = RerankerRegistry()
registry.register(CrossEncoderReranker)

registry.get("cross-encoder")          # -> CrossEncoderReranker (classe)
registry.has("CROSS-ENCODER")           # -> True (normalisé)
registry.supported_strategies()         # -> ("cross-encoder",)
```

| Méthode | Effet |
|---|---|
| `register(strategy_class)` | enregistre la classe sous `strategy_class.name` normalisé ; aucune instanciation |
| `get(name)` | retourne la classe, lève `RerankerStrategyNotRegisteredError` sinon |
| `has(name)` | renvoie `False` sans exception pour un nom invalide ou inconnu |
| `unregister(name)` | retire le mapping ; lève `RerankerStrategyNotRegisteredError` si absent |
| `clear()` | retire tous les mappings |
| `supported_strategies()` | retourne les noms enregistrés, triés |

`register()` échoue avec `InvalidRerankerStrategyError` si la classe
n'hérite pas de `RerankerStrategy`, et avec `RerankerValidationError`
si le nom est déjà pris par une autre classe.

---

## 5. `RerankerOrchestrator`

```text
query (str) + candidates (Sequence[RetrievedChunk])
      ↓
validation (chaîne non vide, séquence de RetrievedChunk)
      ↓
effective_top_k = min(top_k or default_top_k, max_top_k)
      ↓
RerankerRegistry.get(strategy_name)
      ↓
instanciation de la stratégie avec **strategy_options
      ↓
strategy.supports(query, candidates)
      ↓
strategy.rerank(query, candidates, top_k=effective_top_k)
      ↓
validation du type de retour (list[RankedChunk])
      ↓
list[RankedChunk] ordonnée par rang décroissant
```

### 5.1 Truncation

- `effective_top_k = min(top_k or default_top_k, max_top_k)` : le
  plafond `max_top_k` est appliqué **avant** le reranking, pour limiter
  le coût de prédiction du Cross-Encoder.

### 5.2 Politique d'erreur

Toute exception `GMAOError` (et sous-classes) est propagée telle quelle.
Toute autre exception inattendue est encapsulée dans un
`RerankingError` avec `original=exc` pour préserver la cause racine.

### 5.3 Validation de sortie

L'orchestrateur valide que `rerank()` retourne bien un `list` contenant
uniquement des objets `RankedChunk`. Une sortie invalide lève
`RerankerValidationError`.

---

## 6. Stratégie `CrossEncoderReranker`

Reranking par modèle Cross-Encoder via `sentence-transformers`.

### 6.1 Paramètres

| Paramètre | Défaut | Rôle |
|---|---|---|
| `model_name` | `"BAAI/bge-reranker-v2-m3"` | nom du modèle HuggingFace |
| `batch_size` | `16` | taille des lots pour la prédiction |
| `device` | `"auto"` | device de calcul (`"auto"`, `"cpu"`, `"cuda"`) |

### 6.2 Cache de modèle

Le modèle est chargé de manière paresseuse (lazy loading) au premier
appel à `rerank()`, puis mis en cache au niveau de la classe
(`ClassVar[dict]`). Le cache est cléé par `(model_name, device)` et
protégé par un `RLock` + verrou par clé pour un accès thread-safe
(double-checked locking).

`clear_model_cache()` vide le cache (utile pour les tests isolés).

### 6.3 Algorithme

1. Validation des entrées (query non vide, candidates = `Sequence[RetrievedChunk]`, top_k > 0).
2. Chargement du modèle (cache ou création).
3. Construction des paires `[[query, chunk.content], ...]`.
4. Prédiction `model.predict(pairs, batch_size=...)` → scores bruts.
5. Tri par score décroissant.
6. Troncature au `top_k` premiers résultats.
7. Construction des `RankedChunk` avec `rank` (1-indexé), `rerank_score`,
   et fusion des métadonnées (ajout de `retrieval_rank`).

### 6.4 `supports()`

Vérifie que `query` est une chaîne non vide et que `candidates` est
une séquence de `RetrievedChunk`.

---

## 7. Modèle de données

### 7.1 `RankedChunk`

Un chunk retourné par une stratégie de reranking.

| Champ | Type | Signification |
|---|---|---|
| `chunk_id` | `str` | identifiant du chunk |
| `content` | `str` | texte du chunk |
| `source_name` | `str` | nom du fichier ou identifiant panne |
| `source_type` | `str` | type de source |
| `retrieval_score` | `float` | score original de la recherche (avant reranking) |
| `rerank_score` | `float` | score du Cross-Encoder (après reranking) |
| `rank` | `int` | rang final (1-indexé, après reranking) |
| `id_document` | `int \| None` | ID du document parent (si applicable) |
| `id_panne` | `int \| None` | ID de la panne parente (si applicable) |
| `id_equipement` | `int \| None` | ID de l'équipement lié |
| `metadata` | `dict[str, Any]` | métadonnées (inclut `retrieval_rank` ajouté par le reranker) |
| `retrieval_strategy` | `str` | nom de la stratégie ayant produit le chunk |
| `reranker_strategy` | `str` | nom de la stratégie de reranking |

`RankedChunk` est un dataclass `frozen=True` — les instances sont
immuables. La validation en `__post_init__` vérifie les types, exclut
les booléens des `int`/`float`, et impose des chaînes non vides.

---

## 8. Exceptions

```text
GMAOError
└── RerankerError
    ├── RerankerValidationError
    ├── RerankerModelError
    ├── RerankingError
    ├── RerankerStrategyNotRegisteredError
    └── InvalidRerankerStrategyError
```

| Exception | `error_code` | HTTP | Cas typique |
|---|---|---|---|
| `RerankerError` | `RERANKER_ERROR` | 500 | Base générique, ne pas lever directement |
| `RerankerValidationError` | `RERANKER_VALIDATION_ERROR` | 400 | Entrée invalide (query vide, top_k invalide, etc.) |
| `RerankerModelError` | `RERANKER_MODEL_ERROR` | 500 | Échec de chargement ou d'exécution du modèle |
| `RerankingError` | `RERANKING_ERROR` | 500 | Échec technique pendant le reranking |
| `RerankerStrategyNotRegisteredError` | `RERANKER_STRATEGY_NOT_REGISTERED` | 400 | Nom de stratégie inconnu du registre |
| `InvalidRerankerStrategyError` | `RERANKER_INVALID_STRATEGY` | 500 | Classe non conforme au contrat `RerankerStrategy` |

---

## 9. Ajouter une stratégie

1. Hériter de `RerankerStrategy`.
2. Déclarer `name` comme **attribut de classe** non vide.
3. Ne rien faire de coûteux ou de risqué en dehors de `__init__`.
4. Implémenter `supports()` sans effet de bord.
5. Implémenter `rerank()` : valider les entrées, encapsuler toute
   exception tierce dans `RerankingError`, retourner une liste de
   `RankedChunk` ordonnée par rang décroissant.
6. Ajouter la classe au tuple `ALL_STRATEGIES` de
   `strategies/__init__.py` pour qu'elle soit enregistrée par défaut.

---

## 10. Bonnes pratiques

- Toujours passer par `RerankerOrchestrator`, jamais par une stratégie
  instanciée directement (voir §1, règle d'or).
- Ajuster `top_k` avec parcimonie : le Cross-Encoder est coûteux en
  calcul. `top_k` = 10–20 est un bon compromis entre qualité et coût.
- Le `rerank_score` n'est **pas** comparable entre modèles différents.
  Un score de 0.8 avec `bge-reranker-v2-m3` n'a pas la même signification
  qu'avec un autre modèle. Ne pas mélanger les scores de modèles
  différents dans un même classement.
- Conserver les métadonnées `retrieval_rank` dans les résultats : elles
  permettent de diagnostiquer l'impact du reranking par rapport à la
  recherche initiale.
- Pour les tests, utiliser `CrossEncoderReranker.clear_model_cache()` pour
  isoler les cas de test et éviter les fuites de mémoire.

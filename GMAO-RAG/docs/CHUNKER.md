# Référence — Module `app.chunker`

> **Objectif de ce document** : fournir une référence autonome de la couche de découpage (*chunking*) du projet **GMAO-RAG**, pour les développeurs et les assistants IA qui doivent l'utiliser ou l'étendre sans relire l'ensemble du code source.
>
> Le module reçoit un `ParsedDocument` produit par `app.parser` et retourne une liste ordonnée de `Chunk`. Il ne charge pas de données, ne parse pas les formats et ne génère pas les embeddings.

---

## 1. Vue d'ensemble

`app.chunker` est le troisième étage du pipeline RAG :

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
      Vector Store / Retrieval
```

Sa responsabilité est de fragmenter un contenu déjà normalisé en unités adaptées à l'indexation sémantique, tout en préservant le lien avec la source d'origine.

Le chunker ne fait pas :

- de lecture de fichier ou de connexion à une base de données ;
- de parsing ou de nettoyage de format lourd ;
- de sélection de documents pour la recherche ;
- de calcul d'embeddings ou d'accès à un Vector Store.

### Composition du package

| Fichier / package | Rôle |
|---|---|
| `base.py` | contrat abstrait `ChunkerStrategy` |
| `registry.py` | association `source_type` → classe de stratégie |
| `orchestrator.py` | validation, résolution et exécution de la stratégie |
| `strategies/recursive.py` | découpage récursif du texte libre |
| `strategies/markdown.py` | découpage sensible aux titres Markdown |
| `strategies/structured.py` | découpage par enregistrements structurés |
| `strategies/__init__.py` | export des stratégies et tuple `ALL_STRATEGIES` |
| `__init__.py` | API publique et constructeurs de registre/orchestrateur par défaut |

### Règle d'or

> Dans le code applicatif, toujours appeler `ChunkerOrchestrator.chunk(parsed_document)` ou `build_default_orchestrator().chunk(parsed_document)`. L'instanciation directe d'une stratégie est réservée aux tests ou à un besoin spécialisé explicitement identifié.

---

## 2. Point d'entrée public

```python
from app.chunker import build_default_orchestrator
from app.models.parsing import ParsedDocument

document = ParsedDocument(
    source_name="manuel_maintenance.md",
    source_type="markdown",
    content="# Inspection\n\nVérifier le niveau de lubrification.",
    metadata={"mime_type": "text/markdown"},
)

orchestrator = build_default_orchestrator(
    chunk_size=500,
    chunk_overlap=50,
)
chunks = orchestrator.chunk(document)
```

`build_default_orchestrator()` construit un registre prérempli puis un `ChunkerOrchestrator`. Les stratégies `MarkdownChunker`, `StructuredChunker` et `RecursiveChunker` sont enregistrées automatiquement.

| Paramètre | Défaut de l'orchestrateur | Validation |
|---|---:|---|
| `chunk_size` | `500` | entier strictement positif |
| `chunk_overlap` | `50` | entier positif ou nul, strictement inférieur à `chunk_size` |

Les tailles sont exprimées en **caractères Python**, et non en tokens ni en octets. Les stratégies utilisées directement ont leurs propres défauts (`1000` et `100`), mais ceux de l'orchestrateur prévalent dans le pipeline normal.

---

## 3. Routage des stratégies

Le registre sélectionne une stratégie à partir de `ParsedDocument.source_type`, après `strip().lower()`.

| Types de source | Stratégie | Découpage principal |
|---|---|---|
| `txt`, `text`, `pdf`, `docx`, `html` | `RecursiveChunker` | frontières sémantiques décroissantes |
| `markdown`, `md` | `MarkdownChunker` | titres, paragraphes, lignes, mots |
| `json`, `csv`, `xlsx`, `mysql` | `StructuredChunker` | enregistrements, lignes, mots |

Ainsi, `" PDF "` est traité comme `"pdf"`. Si aucun mapping n'existe, le registre lève `ChunkerStrategyNotRegisteredError` avec les types supportés.

`MarkdownChunker.supports()` accepte aussi les MIME types `text/markdown` et `text/x-markdown`. Le registre est cependant résolu avant cet appel : pour bénéficier du routage automatique, un document Markdown doit avoir `source_type="markdown"` ou `"md"`.

---

## 4. Contrat `ChunkerStrategy`

Toute stratégie doit hériter de `ChunkerStrategy` et implémenter les membres suivants :

```python
class ChunkerStrategy(ABC):
    @property
    def name(self) -> str: ...

    @property
    def source_types(self) -> tuple[str, ...]: ...

    def supports(self, document: ParsedDocument) -> bool: ...

    def chunk(self, document: ParsedDocument) -> list[Chunk]: ...
```

| Membre | Responsabilité |
|---|---|
| `name` | nom lisible et stable de la stratégie |
| `source_types` | tuple des types de source pris en charge |
| `supports()` | test de compatibilité sans lancer le découpage |
| `chunk()` | retourne les `Chunk` dans l'ordre du document |

Une stratégie doit lever une sous-classe de `ChunkerError` pour les erreurs métier. Elle doit retourner exactement `list[Chunk]`, jamais une liste de chaînes, un tuple ou un générateur.

---

## 5. `ChunkerRegistry`

`ChunkerRegistry` stocke des **classes** de stratégies, pas des instances. Une stratégie peut déclarer plusieurs types dans `source_types`.

```python
from app.chunker import ChunkerRegistry
from app.chunker.strategies import RecursiveChunker

registry = ChunkerRegistry()
registry.register(RecursiveChunker)

registry.get("pdf")            # -> RecursiveChunker
registry.has("PDF")            # -> True
registry.supported_types()      # -> tuple trié
```

| Méthode | Effet |
|---|---|
| `register(strategy_class)` | valide puis enregistre tous les types déclarés |
| `get(source_type)` | retourne la classe associée |
| `has(source_type)` | renvoie `False` sans exception pour une entrée invalide ou inconnue |
| `unregister(source_type)` | retire le mapping d'un seul type |
| `clear()` | retire tous les mappings |
| `supported_types()` | retourne les clés enregistrées, triées |

L'enregistrement est atomique : si l'un des types est déjà associé à une autre stratégie, aucun mapping de la nouvelle classe n'est ajouté. Retirer `"pdf"` ne retire pas les autres types qui pointent vers la même classe.

---

## 6. `ChunkerOrchestrator`

`ChunkerOrchestrator` est le point unique de coordination. Il ne contient aucune logique propre à Markdown, au texte libre ou aux données structurées.

```text
ParsedDocument
      ↓
validation de document et source_type
      ↓
ChunkerRegistry.get(source_type)
      ↓
instanciation de la stratégie avec chunk_size / chunk_overlap
      ↓
strategy.supports(document)
      ↓
strategy.chunk(document)
      ↓
validation de list[Chunk]
```

Avant l'exécution, l'orchestrateur vérifie que l'entrée est un `ParsedDocument`, que `source_type` est une chaîne non vide et que `content` contient du texte. Après l'exécution, il vérifie que le retour est une liste et que chaque élément est un `Chunk`.

Une nouvelle stratégie enregistrée doit accepter les arguments nommés `chunk_size` et `chunk_overlap`, faute de quoi l'orchestrateur lève `ChunkingError` à l'instanciation.

---

## 7. Stratégies concrètes

### 7.1 `RecursiveChunker`

Cette stratégie s'applique au texte libre : TXT, texte générique, texte extrait de PDF/DOCX et HTML déjà converti en texte par le parser.

Elle essaie successivement les séparateurs :

```python
("\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", "")
```

Le découpage essaie donc les paragraphes, les lignes, les phrases, puis les mots. Si aucun séparateur ne convient, une coupe forcée est appliquée. Elle recule jusqu'au dernier espace disponible ; en l'absence d'espace, elle découpe au nombre de caractères demandé. Cette dernière étape gère correctement les URL, identifiants ou tokens très longs.

L'overlap est prélevé sur la fin du morceau **original** précédent, ajusté à une frontière de mot et ajouté seulement s'il ne fait pas dépasser `chunk_size`. Il n'est pas cumulé entre chunks successifs.

Le constructeur direct accepte aussi `separators`, un tuple personnalisé. Cette option n'est pas exposée par l'orchestrateur.

### 7.2 `MarkdownChunker`

Cette stratégie normalise les fins de lignes, puis sépare le contenu aux titres ATX (`#` à `######`). Elle ne traite pas comme un titre une ligne qui se trouve dans un bloc de code délimité par des backticks ou par `~~~`.

Chaque section est groupée par paragraphes. Un paragraphe trop grand est ensuite découpé par lignes, puis par mots. L'overlap est ajouté seulement si le chunk suivant ne commence pas par un titre et si la taille maximale reste respectée. Ce choix évite de préfixer artificiellement une nouvelle section par le contenu de la précédente.

### 7.3 `StructuredChunker`

Cette stratégie traite JSON, CSV, XLSX et résultats MySQL après parsing.

| Source | Extraction des enregistrements |
|---|---|
| JSON valide | un élément par élément de liste ; un objet entier pour un dictionnaire ; sérialisation JSON indentée UTF-8 |
| JSON non valide | repli sur les lignes non vides |
| CSV / XLSX / MySQL | une ligne non vide par enregistrement |

Les enregistrements sont regroupés tant que leur taille totale reste sous la limite. Un enregistrement trop grand est séparé par lignes, puis par mots. L'overlap utilise le suffixe du chunk précédent et est ignoré s'il ferait dépasser `chunk_size`.

Pour les données tabulaires et MySQL, la qualité dépend du texte construit par le parser : conserver une ligne logique par enregistrement est donc la convention à respecter en amont.

### 7.4 Limites de taille réelles

Les trois stratégies empêchent l'overlap de dépasser la taille cible. `RecursiveChunker` garantit aussi la découpe d'un token sans espace plus long que `chunk_size`.

`MarkdownChunker` et `StructuredChunker` terminent au niveau des mots. Un unique mot sans espace plus long que `chunk_size` peut donc dépasser la limite. Si cette contrainte est bloquante pour le modèle d'embedding, utiliser `RecursiveChunker` ou ajouter une stratégie spécialisée.

---

## 8. Modèle `Chunk` et métadonnées

Chaque stratégie retourne `app.models.chunk.Chunk`.

| Champ | Signification |
|---|---|
| `content` | texte non vide du morceau |
| `chunk_index` | position de base zéro dans le document |
| `source_name` | identifiant de la source d'origine |
| `source_type` | type de source normalisé en minuscules |
| `metadata` | copie des métadonnées parser enrichie par le chunker |
| `start_char`, `end_char` | offsets optionnels, non renseignés par les stratégies actuelles |
| `total_chunks` | total optionnel, non renseigné par les stratégies actuelles |
| `chunk_id` | identifiant optionnel |

Toutes les stratégies préservent les métadonnées existantes et ajoutent :

```python
{
    "chunker": "recursive" | "markdown" | "structured",
    "chunk_size": ...,
    "chunk_overlap": ...,
    "chunk_index": ...,
}
```

`StructuredChunker` ajoute `structured_source_type`. `MarkdownChunker` et `StructuredChunker` définissent `chunk_id` avec la forme `"{source_name}:{index}"`. `RecursiveChunker` laisse `chunk_id` à `None`.

Le modèle `Chunk` valide son contenu, son index, sa provenance et ses métadonnées lors de la construction. Un chunk vide ou un index négatif ne peut donc pas être retourné normalement.

---

## 9. Exceptions

```text
GMAOError
└── ChunkerError
    ├── ChunkerValidationError
    │   └── ChunkSizeError
    ├── InvalidChunkerStrategyError
    ├── ChunkerStrategyNotRegisteredError
    ├── ChunkingError
    └── EmptyChunkError
```

| Exception | Cas typique |
|---|---|
| `ChunkerValidationError` | document, source type, taille, overlap ou configuration invalide |
| `InvalidChunkerStrategyError` | classe non conforme à `ChunkerStrategy` |
| `ChunkerStrategyNotRegisteredError` | type non enregistré |
| `ChunkingError` | erreur inattendue pendant l'instanciation ou le découpage |
| `EmptyChunkError` | exception disponible pour une future stratégie qui détecte explicitement un chunk vide |
| `ChunkSizeError` | exception spécialisée disponible pour une validation de taille dédiée |

Les stratégies actuelles emploient principalement `ChunkerValidationError` et `ChunkingError`.

---

## 10. Ajouter une stratégie

1. Hériter de `ChunkerStrategy`.
2. Accepter `chunk_size` et `chunk_overlap` dans `__init__`.
3. Valider la configuration et lever `ChunkerValidationError` si nécessaire.
4. Déclarer un tuple non vide de `source_types` uniques.
5. Implémenter `supports()` sans effet de bord.
6. Retourner une `list[Chunk]` ordonnée, avec des `chunk_index` de base zéro.
7. Copier les métadonnées du document et ajouter les informations propres à la stratégie.
8. Encapsuler les erreurs imprévues dans `ChunkingError`.
9. Enregistrer la classe dans un `ChunkerRegistry`, puis l'ajouter à `ALL_STRATEGIES` seulement si elle doit devenir une stratégie par défaut.

---

## 11. Bonnes pratiques

- Toujours parser avant de chunker : l'entrée attendue est `ParsedDocument`, jamais `SourceDocument` ou une simple chaîne.
- Définir correctement `source_type`, car il détermine la stratégie. Un Markdown étiqueté `txt` ne conservera pas ses frontières de titres.
- Ajuster `chunk_size` au modèle d'embedding cible : une taille en caractères n'est pas une taille en tokens.
- Garder un overlap utile mais modéré ; un overlap excessif augmente la duplication et la taille de l'index.
- Conserver les métadonnées de provenance dans chaque chunk : elles sont nécessaires au filtrage et à l'explication des résultats de retrieval.
- Tester tout nouveau découpage sur des documents techniques réels : manuels, historiques d'intervention et exports d'équipements présentent des structures différentes.

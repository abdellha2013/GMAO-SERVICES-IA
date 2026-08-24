# Référence — Module `app.parser`

> **Objectif de ce document** : servir de référence unique et autosuffisante
> sur la couche de parsing (*Parser Layer*) du projet **RAG-GMAO**, pour :
> - les développeurs humains (comprendre quoi appeler, quoi hériter) ;
> - les assistants IA / chatbots générant ou relisant du code sur ce
>   projet, **sans avoir besoin de relire tout le code source** à chaque
>   fois.
>
> Version documentée : v2 (post-audit du 15/08/2026 — voir section
> [Changelog](#changelog--historique-des-corrections)). Corrections
> vérifiées fonctionnellement (import complet, enregistrement et
> exécution réelle de chaque stratégie, cas d'erreur reproduits) avant
> rédaction de ce document — voir `FIX_PARSER_MODULE.md` pour le détail
> point par point des corrections appliquées.
>
> Document complémentaire à `EXCEPTIONS.md` (référence du module
> `app.exceptions`, utilisé massivement ici) et à `DATA_SOURCES.md`
> (étage amont du pipeline, producteur des `SourceDocument` consommés
> ici).

---

## 1. Vue d'ensemble

Le module `app/parser/` est le **deuxième étage** du pipeline RAG :

```
Fichier / Base de données / API
            ↓
   app.data_sources        (voir DATA_SOURCES.md)
            ↓
      SourceDocument
            ↓
   app.parser   (ce document — ParserOrchestrator)
            ↓
     ParsedDocument
            ↓
       app.chunker
            ↓
       Chunks → Embedding
```

Sa seule responsabilité est de transformer un `SourceDocument` déjà
chargé (texte brut extrait, aucun accès disque/réseau/DB à ce stade)
en un `ParsedDocument` normalisé, en gérant proprement :

- la sélection de la stratégie de parsing adaptée au `source_type` ;
- la validation du document et de son contenu ;
- la normalisation du texte (encodage de ligne, espaces, structure
  minimale) sans réinterpréter la sémantique métier du contenu ;
- la traduction de toute erreur en exception métier du projet
  (`app.exceptions`, voir `EXCEPTIONS.md`).

Le parser **ne fait pas** :
- de lecture de fichier, de connexion base de données ou d'appel
  réseau (responsabilité de `app.data_sources`) ;
- de découpage en chunks ni de génération d'embeddings (responsabilité
  de `app.chunker`) ;
- de sélection d'une autre stratégie que celle résolue par le registre
  (aucune stratégie ne doit en appeler une autre).

### Composition du package

| Fichier | Rôle |
|---|---|
| `base.py` | Contrat abstrait `ParserStrategy` — interface minimale (`name`, `supports()`, `parse()`) |
| `strategies/base.py` | `BaseParserStrategy` — validations et helpers communs à toutes les stratégies concrètes |
| `strategies/text.py` | `TextParser` — texte brut (`txt`, `pdf`, `docx` déjà extraits) |
| `strategies/markdown.py` | `MarkdownParser` — Markdown (`markdown`, `md`) |
| `strategies/html.py` | `HTMLParser` — HTML (`html`, `htm`) |
| `strategies/structured.py` | `StructuredParser` — données structurées (`json`, `csv`, `xlsx`) |
| `strategies/database.py` | `DatabaseParser` — résultats de requêtes (`mysql`) |
| `registry.py` | `ParserRegistry` — associe `source_type` ↔ classe de stratégie |
| `orchestrator.py` | `ParserOrchestrator` — point d'entrée unique, résout et exécute la stratégie |
| `__init__.py` (racine) | Ré-exporte l'API publique du package entier |

### Règle d'or

> **Toute stratégie de parsing DOIT hériter de `ParserStrategy`**
> (directement ou, en pratique, via `BaseParserStrategy`), et DOIT être
> consommée via `ParserOrchestrator.parse()` — jamais en instanciant
> et en appelant une stratégie concrète directement dans le code
> applicatif, sauf à l'intérieur du package lui-même ou dans des tests
> unitaires ciblés.

---

## 2. `ParserStrategy` — le contrat commun

Fichier : `base.py`.

```python
class ParserStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def supports(self, document: SourceDocument) -> bool: ...

    @abstractmethod
    def parse(self, document: SourceDocument) -> ParsedDocument: ...
```

Le contrat est intentionnellement minimal :
`SourceDocument -> ParsedDocument`.

- `name` : identifiant unique utilisé pour le logging, le diagnostic
  et les opérations de registre.
- `supports(document)` : **détermine seulement** la compatibilité,
  **ne parse jamais**. Ne doit pas avoir d'effet de bord.
- `parse(document)` : réalise la transformation effective. Doit lever
  une `ParserError` (ou sous-classe) en cas d'échec — jamais une
  exception Python nue.

Une stratégie **ne doit jamais** sélectionner une autre stratégie —
cette responsabilité appartient exclusivement au registre et à
l'orchestrateur.

### 2.1 `BaseParserStrategy` — socle commun

Fichier : `strategies/base.py`. Implémente `ParserStrategy` et
apporte à toutes les stratégies concrètes :

| Méthode | Rôle |
|---|---|
| `_validate_document(document)` | Vérifie le type (`SourceDocument`), et que `source_name`/`source_type`/`content` sont des chaînes non vides |
| `_validate_content(document)` | Appelle `_validate_document()` puis vérifie que `content` n'est pas vide/whitespace-only |
| `_normalize_source_type(document)` | Retourne `source_type` validé, normalisé (`strip().lower()`) |
| `_get_text_content(document)` | Retourne `content` validé et `strip()` |
| `_build_parsed_document(document, content, **overrides)` | Construit le `ParsedDocument` final en préservant la provenance (`source_name`, `source_type`, `source_path`, `mime_type`, `size`, `created_at`, `updated_at`) et en horodatant `parsed_at` (UTC) ; lève `ParserError` si la construction échoue |

Toute nouvelle stratégie doit hériter de `BaseParserStrategy`, pas
directement de `ParserStrategy`, sauf besoin architectural très
spécifique.

### 2.2 Pattern de validation commun (`parse()`)

Les 5 stratégies concrètes suivent **toutes** le même schéma dans
`parse()` — c'est le contrat implicite à respecter pour toute
nouvelle stratégie :

```python
def parse(self, document: SourceDocument) -> ParsedDocument:
    self._validate_content(document)          # hérité de BaseParserStrategy

    if not self.supports(document):
        raise ParserValidationError(
            message="<Strategy> does not support this document.",
            details={
                "source_type": document.source_type,
                "mime_type": document.mime_type,
                "strategy": self.name,
            },
        )

    content = ...  # normalisation spécifique à la stratégie

    if not content:
        raise ParserValidationError(...)

    return self._build_parsed_document(document, content, **overrides)
```

Aucune stratégie ne doit redéfinir `_validate_document()` avec une
logique divergente (c'était un bug identifié dans `MarkdownParser`,
corrigé — voir Changelog).

---

## 3. Table de référence des stratégies

| Stratégie | `source_type` gérés | MIME secondaire | Dépendance tierce | Exceptions spécifiques possibles |
|---|---|---|---|---|
| `TextParser` | `txt`, `pdf`, `docx` | — | — | `ParserValidationError` |
| `MarkdownParser` | `markdown`, `md` | `text/markdown`, `text/x-markdown` | — | `ParserValidationError` |
| `HTMLParser` | `html`, `htm` | `text/html`, `application/xhtml+xml` | `beautifulsoup4` | `ParserValidationError` |
| `StructuredParser` | `json`, `csv`, `xlsx` | `application/json`, `text/csv`, formats Office | — (stdlib `json`) | `ParserValidationError` (JSON malformé inclus) |
| `DatabaseParser` | `mysql` | `application/x-mysql-resultset` | — | `ParserValidationError` |

Toutes les exceptions ci-dessus héritent de `ParserError` (voir
`EXCEPTIONS.md` §5.4) — `except ParserError:` les capture toutes.

### 3.1 `TextParser` — texte brut

`pdf` et `docx` sont routés vers `TextParser` et non vers une
stratégie dédiée : `PDFLoader`/`DOCXLoader` (voir `DATA_SOURCES.md`
§3.3) ont **déjà extrait le texte brut** en amont, avant que le
document n'atteigne le parser. Ce n'est pas une erreur de mapping —
ne pas "corriger" ce routage sans revoir toute la couche
`data_sources`.

Normalisation appliquée : `strip()` uniquement, aucune autre
transformation (pas de suppression d'espaces internes significatifs,
pas de détection/changement d'encodage — déjà géré en amont).

### 3.2 `MarkdownParser` — Markdown

Normalisation appliquée, dans `_normalize_content()` :
- `\r\n`/`\r` → `\n` ;
- suppression des espaces/tabs en fin de ligne ;
- réduction des lignes vides consécutives à 2 maximum ;
- suppression des lignes vides en début/fin de document.

La syntaxe Markdown elle-même (titres, listes, liens, emphase) est
**intentionnellement préservée** — ce parser ne convertit jamais en
HTML.

Expose également `extract_headings(content) -> list[str]`, une
méthode statique indépendante du flux `parse()` principal, pensée
pour être réutilisée par une future stratégie de chunking sémantique.

### 3.3 `HTMLParser` — HTML

Utilise `BeautifulSoup` (`html.parser`) pour :
- retirer les éléments non textuels (`script`, `style`, `noscript`,
  `template`) avant extraction ;
- extraire le texte avec `get_text(separator="\n")` ;
- normaliser (espaces multiples réduits, lignes vides supprimées).

### 3.4 `StructuredParser` — JSON / CSV / XLSX

| `source_type` | Traitement |
|---|---|
| `json` | `json.loads()` puis re-sérialisation déterministe (`indent=2`, `sort_keys=True`, `ensure_ascii=False`) |
| `csv`, `xlsx` | Normalisation textuelle uniquement (`strip()` ligne par ligne) — l'extraction elle-même est déjà faite par le loader amont (`CSVLoader`/`XLSXLoader`, voir `DATA_SOURCES.md` §3.3) |
| autre (fallback MIME) | Résolution par `mime_type` si `source_type` n'est pas canonique |

**Règle stricte : un JSON malformé lève toujours
`ParserValidationError`**, quel que soit le contenu de
`document.metadata`. Il n'existe **aucun fallback silencieux** qui
retraiterait un JSON invalide comme du contenu tabulaire — un tel
fallback a existé, masquait des erreurs de `JSONLoader` en amont
(voir `DATA_SOURCES.md` §3.3, `JSONParsingError`), et a été supprimé
(voir Changelog). Ne jamais le réintroduire sans validation explicite
de l'équipe métier, et si un cas légitime l'exige un jour : logger un
`logger.warning(...)` explicite, chaîner l'exception d'origine
(`raise ... from exc`), et documenter précisément la condition dans
la docstring de `parse()`.

### 3.5 `DatabaseParser` — résultats MySQL

Ne se connecte jamais à une base de données et n'exécute aucun SQL —
`MySQLSource`/`MySQLLoader` (voir `DATA_SOURCES.md` §4) ont déjà
produit le texte du `SourceDocument.content` en amont. Ce parser ne
fait que valider et normaliser ce texte déjà extrait.

Expose des helpers statiques réutilisables (utiles aussi côté tests
ou avant chargement dans `SourceDocument.content`) :

```python
DatabaseParser.format_value(value)       # -> str, un type Python -> une représentation stable
DatabaseParser.format_row(row: dict)     # -> "col1: val1 | col2: val2 | ..."
DatabaseParser.format_rows(rows: list)   # -> une ligne formatée par entrée, séparées par \n
```

`format_value()` gère explicitement : `None` → `"NULL"`, `bool` →
`"TRUE"`/`"FALSE"`, `datetime`/`date`/`time` → ISO 8601, `Decimal` →
représentation décimale fixe (`format(value, "f")`), `dict`/`list`/
`tuple` → JSON UTF-8 (`ensure_ascii=False`), tout le reste →
`str(value)`.

---

## 4. `ParserRegistry` — association `source_type` ↔ stratégie

Fichier : `registry.py`.

Le registre **stocke des classes**, pas des instances. Il ne réalise
aucun parsing lui-même — cette responsabilité appartient à
l'orchestrateur (§5).

```python
registry = ParserRegistry()
registry.register(TextParser)          # enregistre sous "txt", "pdf", "docx"
                                        # (SUPPORTED_SOURCE_TYPES de TextParser)

strategy_cls = registry.get("txt")     # -> TextParser
registry.has("txt")                    # -> True
"txt" in registry                      # -> True (idem, via __contains__)
len(registry)                          # -> nombre de source_type enregistrés
registry.supported_types()             # -> tuple trié de tous les source_type enregistrés
registry.unregister("txt")
registry.clear()                       # vide le registre (tests, réinitialisation)
```

### 4.1 `register(strategy)`

Une stratégie est enregistrée sous **chaque** `source_type` déclaré
dans son attribut de classe `SUPPORTED_SOURCE_TYPES`. Si cet attribut
est absent, le registre retombe sur `strategy().name` comme unique
`source_type` (compatibilité ascendante avec des stratégies à un seul
type).

```python
class SUPPORTED_SOURCE_TYPES = frozenset({"json", "csv", "xlsx"})
```

| Exception | Condition |
|---|---|
| `InvalidStrategyError` | `strategy` n'est pas une classe, ou n'hérite pas de `ParserStrategy` |
| `ParserValidationError` | Un `source_type` dérivé de `strategy` est déjà enregistré par une autre classe |

La validation passe **exclusivement** par `_validate_strategy()` —
`register()` ne doit jamais dupliquer ce contrôle manuellement (c'était
un bug corrigé, voir Changelog).

### 4.2 `get(source_type)` / `unregister(source_type)`

| Exception | Condition |
|---|---|
| `ParserValidationError` | `source_type` n'est pas une chaîne, ou est vide après normalisation |
| `ParserStrategyNotRegisteredError` | Aucune stratégie enregistrée pour ce `source_type` |

`has(source_type)` est volontairement tolérante : un `source_type`
invalide retourne `False` plutôt que de lever une exception (utile
pour des vérifications défensives sans `try/except`).

---

## 5. `ParserOrchestrator` — point d'entrée unique

Fichier : `orchestrator.py`.

```python
from app.parser import ParserRegistry, ParserOrchestrator, TextParser

registry = ParserRegistry()
registry.register(TextParser)
# ... enregistrer les autres stratégies nécessaires

orchestrator = ParserOrchestrator(registry)
parsed = orchestrator.parse(source_document)   # -> ParsedDocument
```

`parse(document)` :
1. résout la classe de stratégie via `registry.get(document.source_type)` ;
2. instancie la stratégie ;
3. vérifie `strategy.supports(document)` — filet de sécurité si le
   registre et la stratégie divergeraient un jour ;
4. délègue à `strategy.parse(document)`.

| Exception | Condition |
|---|---|
| `ParserStrategyNotRegisteredError` | Aucune stratégie enregistrée pour `document.source_type` (propagée depuis le registre, catchable via `except ParserError:` ou `except GMAOError:`) |
| `ParserError` | La stratégie résolue ne supporte finalement pas le document (incohérence registre/stratégie) |
| *(toute sous-classe de `ParserError`)* | Levée par la stratégie elle-même pendant `parse()` |

C'est le **seul point d'entrée public** attendu pour parser un
document dans le pipeline RAG — ne jamais appeler
`strategy_cls().parse(document)` directement dans le code applicatif
en contournant l'orchestrateur, sauf test unitaire ciblé sur une
stratégie isolée.

---

## 6. Table de correspondance avec `app.exceptions`

Toutes les exceptions levées par `app.parser` proviennent de la
hiérarchie documentée dans `EXCEPTIONS.md` §5.4. Rappel des points
d'entrée génériques les plus utiles pour capturer au bon niveau :

| Contexte | Exception à catcher |
|---|---|
| N'importe quelle erreur de ce package | `GMAOError` |
| N'importe quelle erreur de parsing (base à catcher en priorité) | `ParserError` |
| Document ou `source_type` invalide, contenu vide/malformé | `ParserValidationError` |
| Classe de stratégie invalide passée à `register()` (bug de code) | `InvalidStrategyError` |
| `source_type` inconnu du registre | `ParserStrategyNotRegisteredError` |

```python
from app.exceptions import ParserError, ParserStrategyNotRegisteredError, GMAOError
from app.parser import ParserOrchestrator

try:
    parsed = orchestrator.parse(document)
except ParserStrategyNotRegisteredError as e:
    logger.warning("Type de source non supporté: %s", e.to_dict())
except ParserError as e:
    logger.error("Erreur de parsing: %s", e.to_dict())
except GMAOError as e:
    logger.error("Erreur non catégorisée du pipeline: %s", e.to_dict())
```

---

## 7. Pièges connus / règles à ne jamais enfreindre

Ces règles proviennent de l'audit du module du 15/08/2026 (voir
`FIX_PARSER_MODULE.md` et Changelog) — à respecter pour toute
contribution future, humaine ou générée par IA.

1. **Toujours importer les exceptions depuis le package `app.exceptions`**,
   jamais depuis un sous-module (`app.exceptions.parser`, etc.), sauf
   besoin très spécifique — voir `EXCEPTIONS.md` §7 règle 6.

2. **`ParserStrategy` (le contrat abstrait) s'importe depuis
   `app.parser.base`**, pas depuis `app.parser.strategies.base`
   (`BaseParserStrategy`, l'implémentation concrète). Le registre et
   toute nouvelle stratégie doivent respecter cette distinction pour
   ne pas coupler le contrat à une implémentation.

3. **Ne jamais lever `TypeError`/`ValueError`/`Exception` nus** dans le
   code applicatif du parser — toujours une sous-classe de
   `ParserError`. `_validate_strategy()` est le point de contrôle
   unique pour valider qu'une classe est une stratégie recevable ;
   `register()` doit l'appeler plutôt que de dupliquer le contrôle.

4. **Toutes les stratégies concrètes suivent le même schéma de
   validation dans `parse()`** (§2.2) : `_validate_content()` héritée,
   puis `supports()` vérifié explicitement avec levée d'une
   `ParserValidationError` dédiée. Ne pas surcharger
   `_validate_document()` avec une logique divergente par stratégie.

5. **Un JSON malformé ne doit jamais être requalifié silencieusement**
   en contenu tabulaire ou en tout autre format de repli. Toute
   erreur de parsing JSON doit remonter comme `ParserValidationError`.

6. **Une stratégie ne sélectionne jamais une autre stratégie.** La
   résolution `source_type -> stratégie` est strictement
   la responsabilité de `ParserRegistry` + `ParserOrchestrator`.

7. **`supports()` ne doit jamais avoir d'effet de bord ni parser quoi
   que ce soit** — elle ne fait que répondre à une question de
   compatibilité (`source_type`/`mime_type`).

8. **Ne jamais nommer une exception ou une variable comme un builtin
   Python** — voir `EXCEPTIONS.md` §7 règle 1.

---

## 8. Comment ajouter une nouvelle stratégie de parsing

Checklist pour une IA/un développeur qui doit ajouter le support d'un
nouveau `source_type` :

1. Créer `app/parser/strategies/<format>.py`, classe
   `<Format>Parser(BaseParserStrategy)`.
2. Définir `SUPPORTED_SOURCE_TYPES: frozenset[str]` (et, si pertinent,
   `SUPPORTED_MIME_TYPES` comme indicateur secondaire dans
   `supports()`).
3. Implémenter `name` (property), `supports()` et `parse()` en suivant
   **strictement** le pattern commun décrit en §2.2.
4. Dans `parse()`, terminer par `self._build_parsed_document(document,
   content, **overrides)` — ne jamais construire un `ParsedDocument`
   manuellement.
5. Ajouter l'import + export dans `strategies/__init__.py::__all__`,
   puis dans `parser/__init__.py::__all__`.
6. Enregistrer la stratégie auprès du `ParserRegistry` utilisé par le
   pipeline (`registry.register(<Format>Parser)`).
7. Documenter la nouvelle stratégie dans la table §3 de ce document.
8. Vérifier qu'aucune logique de normalisation n'est dupliquée avec
   une stratégie existante — factoriser dans
   `strategies/base.py::BaseParserStrategy` si la logique est
   réellement commune à plusieurs stratégies.

---

## Changelog — historique des corrections

| Version | Changement |
|---|---|
| v1 (état initial) | `registry.get()`/`unregister()` levaient `NameError` (référence à `StrategyNotRegisteredError`, un nom inexistant) au lieu de `ParserStrategyNotRegisteredError` ; `register()` levait un `TypeError` Python nu au lieu d'utiliser `_validate_strategy()` (implémentée mais jamais appelée) ; `text.py`/`database.py` importaient les exceptions depuis un sous-module (`app.exceptions.parser`) au lieu du package ; `registry.py` importait `ParserStrategy` depuis `app.parser.strategies.base` (implémentation) au lieu de `app.parser.base` (contrat) ; `StructuredParser` masquait silencieusement un JSON malformé en le retraitant comme du contenu tabulaire selon `metadata.get("root_type")` ; `MarkdownParser` redéfinissait `_validate_document()` avec une logique divergente des 4 autres stratégies ; imports inutilisés, import relatif isolé, docstring corrompue et anomalies PEP8 mineures. |
| **v2 (actuelle)** | Tous les points ci-dessus corrigés et vérifiés fonctionnellement (import complet du package, enregistrement et exécution réelle des 5 stratégies, `registry.get()`/`unregister()` sur type inconnu, `register()` sur classe invalide, JSON malformé avec et sans métadonnées, `ParserOrchestrator.parse()` de bout en bout) : `ParserStrategyNotRegisteredError` et `InvalidStrategyError` catchables via `ParserError`/`GMAOError`, les 5 stratégies homogènes sur le même schéma de validation, aucun fallback silencieux sur JSON invalide, imports d'exceptions 100% conformes à `EXCEPTIONS.md` §7 règle 6. |

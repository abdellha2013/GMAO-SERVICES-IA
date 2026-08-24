# Référence — Module `app.data_sources`

> **Objectif de ce document** : servir de référence unique et autosuffisante
> sur la couche de chargement de données (*Data Source Layer*) du projet
> **RAG-GMAO**, pour :
> - les développeurs humains (comprendre quoi appeler, quoi hériter) ;
> - les assistants IA / chatbots générant ou relisant du code sur ce
>   projet, **sans avoir besoin de relire tout le code source** à chaque
>   fois.
>
> Version documentée : v2 (post-audit — voir section
> [Changelog](#changelog--historique-des-corrections)). Corrections
> vérifiées fonctionnellement (import complet, chargement réel de
> chaque format, cas d'erreur, cycle de vie MySQL) avant rédaction de ce
> document.
>
> Document complémentaire à `EXCEPTIONS.md` (référence du module
> `app.exceptions`, utilisé massivement ici).

---

## 1. Vue d'ensemble

Le module `app/data_sources/` est le **premier étage** du pipeline RAG :

```
Fichier / Base de données / API
            ↓
   app.data_sources  (ce document)
            ↓
      SourceDocument
            ↓
   app.parser   (ParserOrchestrator)
            ↓
     ParsedDocument
            ↓
   app.chunker
            ↓
       Chunks → Embedding
```

Sa seule responsabilité est de transformer **n'importe quelle source de
données brute** (fichier local, base MySQL, API...) en un objet
`SourceDocument` normalisé, en gérant proprement :

- la validation de la source (existe-t-elle, est-elle lisible, dans le
  bon format ?) ;
- la connexion et sa fermeture (fichier ouvert, session SQL...) ;
- la traduction de toute erreur technique (SDK tiers, OS, réseau) en
  exception métier du projet (`app.exceptions`, voir `EXCEPTIONS.md`) ;
- la construction de métadonnées exploitables par les étages suivants.

### Composition du package

| Sous-package / fichier | Rôle |
|---|---|
| `interfaces/base_source.py` | Classe abstraite `BaseSource` — contrat commun (Template Method Pattern) |
| `file/` | Sources de type fichier (txt, md, csv, json, html, docx, pdf, xlsx) |
| `database/` | Sources de type base de données (MySQL) |
| `api/` | Réservé aux sources API — **existe mais est vide, non implémenté** |
| `orchestrator.py` | Point d'entrée unique, résout le type de source et délègue |
| `__init__.py` (racine) | Ré-exporte l'API publique du package entier |

### Règle d'or

> **Toute source de données DOIT hériter de `BaseSource`**, directement
> ou via une classe intermédiaire (`FileSource`, `MySQLSource`...), et
> DOIT être consommée via `.read()` (jamais `.load()` directement), sauf
> à l'intérieur du package lui-même pour construire un nouveau
> comportement composé.

---

## 2. `BaseSource` — le contrat commun (Template Method Pattern)

Fichier : `interfaces/base_source.py`.

```python
class BaseSource(ABC, Generic[T]):
    def __init__(self, source: T) -> None: ...

    # Abstrait — à implémenter par chaque sous-classe concrète
    def validate(self) -> None: ...        # vérifie la source
    def _connect(self) -> None: ...        # ouvre la connexion
    def load(self) -> SourceDocument: ...  # charge les données
    def _close(self) -> None: ...          # libère les ressources

    @property
    def source_name(self) -> str: ...      # nom lisible (abstrait)

    # Concret — fourni par BaseSource, à NE PAS redéfinir sans raison
    def read(self) -> SourceDocument: ...  # POINT D'ENTRÉE PUBLIC
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def ensure_connected(self) -> None: ...
    def ensure_open(self) -> None: ...
    def reset(self) -> None: ...
```

### 2.1 Cycle de vie — `read()`

`read()` est **le seul point d'entrée public recommandé**. Il exécute,
dans l'ordre, et avec gestion d'erreurs + logging à chaque étape :

```
1. validate()              -> lève ValidationError si invalide
2. _connect_with_state()   -> lève DataConnectionError si échec
3. load()                  -> lève LoadingError si échec
4. _close_with_state()     -> toujours exécuté (finally), lève CloseError si échec
```

Les transitions d'état (`SourceState.INITIALIZED → CONNECTED →
CLOSED / ERROR`) sont gérées automatiquement, sous verrou
(`RLock`), pour rester cohérentes même en environnement multi-thread.

> ⚠️ **Piège corrigé (v1 → v2)** : ne **jamais** appeler `.load()`
> directement sur une source pour la "charger" — cela saute la
> validation (selon les loaders), la connexion, et surtout la
> **fermeture garantie** des ressources. Toujours passer par `.read()`,
> ou par les fonctions publiques du package (`load_file()`,
> `load_database()`, `DataSourceOrchestrator.load()`), qui appellent
> `.read()` en interne.

### 2.2 États (`SourceState`)

| État | Signification |
|---|---|
| `INITIALIZED` | Instance créée, aucune connexion ouverte |
| `CONNECTED` | Connexion active |
| `CLOSED` | Ressources libérées (état terminal normal) |
| `ERROR` | Une étape a échoué ; la source ne doit plus être réutilisée sans `reset()` |

Propriétés dérivées utiles : `is_connected`, `is_closed`, `is_error`,
`is_ready` (`connected AND NOT closed`), `status` (`"connected"` /
`"closed"` / `"disconnected"`).

### 2.3 Context manager

```python
with SomeLoader("file.txt") as loader:
    document = loader.read()
# .close() appelé automatiquement à la sortie du bloc
```

---

## 3. `app.data_sources.file` — sources fichiers

### 3.1 Hiérarchie

```
BaseSource[Path]
 └── FileSource                 (file_source.py)
      ├── TXTLoader              (.txt)
      │    └── MarkdownLoader    (.md, .markdown) — hérite de TXTLoader
      ├── CSVLoader              (.csv)
      ├── JSONLoader             (.json)
      ├── HTMLLoader             (.html, .htm)
      ├── DOCXLoader             (.docx)
      ├── PDFLoader              (.pdf)
      └── XLSXLoader             (.xlsx)
```

### 3.2 `FileSource` — socle commun

Apporte à tous les loaders fichiers :

- résolution du chemin absolu (`Path(source).expanduser().resolve()`) ;
- propriétés : `path`, `filename`, `stem`, `extension`, `mime_type`,
  `size`, `created_at`, `modified_at`, `parent_directory` ;
- `validate()` : existence, type "fichier régulier", taille non nulle,
  **taille maximale** (`MAX_FILE_SIZE_BYTES`, 200 Mo par défaut,
  surchargeable par sous-classe), lisibilité ;
- `metadata()` : dictionnaire de métadonnées en **un seul appel
  `stat()`** (évite les accès disque redondants) ;
- `open_file()` / `read_text()` / `read_lines()` : accès fichier
  sécurisé, avec traduction des erreurs OS en exceptions métier ;
- `has_extension()` / `ensure_extension()` : validation d'extension.

### 3.3 Table de référence des loaders fichiers

| Loader | Extensions | Dépendance tierce | Exceptions spécifiques possibles |
|---|---|---|---|
| `TXTLoader` | `.txt` | — | `InvalidEncodingError` |
| `MarkdownLoader` | `.md`, `.markdown` | — | `InvalidEncodingError` (hérite de `TXTLoader`, voir §3.4) |
| `CSVLoader` | `.csv` | — (stdlib `csv`) | `InvalidEncodingError` |
| `JSONLoader` | `.json` | — (stdlib `json`) | `InvalidEncodingError`, `JSONParsingError`, `EmptyFileError` |
| `HTMLLoader` | `.html`, `.htm` | `beautifulsoup4` | `InvalidEncodingError`, `HTMLParsingError`, `EmptyFileError` |
| `DOCXLoader` | `.docx` | `python-docx` | `CorruptedFileError` (format ZIP invalide), `InvalidDOCXError`, `FileLoadingError` |
| `PDFLoader` | `.pdf` | `pypdf` | `InvalidPDFError`, `FileLoadingError` |
| `XLSXLoader` | `.xlsx` | `openpyxl` | `CorruptedFileError` (format ZIP invalide), `InvalidXLSXError`, `FileLoadingError` |

Toutes les exceptions ci-dessus héritent de `FileError` (voir
`EXCEPTIONS.md` §5.2) — `except FileError:` les capture toutes.

### 3.4 Réutilisation de logique entre loaders (`MarkdownLoader`)

`MarkdownLoader` hérite de `TXTLoader` et **réutilise réellement** sa
logique de validation + détection d'encodage via la méthode protégée
partagée `TXTLoader._load_as_text(extensions=..., source_type=...)`.
Seuls diffèrent : les extensions acceptées et la valeur
`source_type` du `SourceDocument` retourné (`"txt"` vs `"markdown"`).

C'est le patron à suivre pour tout nouveau loader texte proche d'un
loader existant : factoriser dans une méthode protégée partagée plutôt
que dupliquer `load()`.

### 3.5 Détection d'encodage — logique mutualisée

Tous les loaders texte (`TXTLoader`, `CSVLoader`, `HTMLLoader`,
`JSONLoader`) s'appuient sur la fonction utilitaire commune :

```python
from app.data_sources.file.utils import detect_text_encoding

encoding = detect_text_encoding(
    source,                      # instance FileSource
    encodings=("utf-8", "utf-8-sig"),
    sample_only=False,           # True = ne teste qu'un échantillon (plus rapide, moins fiable)
)
# -> str (encodage valide) ou None (aucun ne fonctionne)
```

`detect_text_encoding()` est **neutre** : elle retourne `None` en cas
d'échec plutôt que de lever une exception. Chaque loader garde une
méthode privée `_detect_encoding()` fine, qui appelle la fonction
mutualisée puis lève `InvalidEncodingError` avec un message/détails
adaptés au contexte si le résultat est `None`. Ne jamais réimplémenter
la boucle `for encoding in (...): try/except UnicodeDecodeError` à la
main dans un nouveau loader — toujours passer par
`detect_text_encoding()`.

### 3.6 Validations mutualisées (`validators.py`)

| Fonction | Utilisée par | Exception levée |
|---|---|---|
| `ensure_within_size_limit(path, max_bytes)` | `FileSource.validate()` | `FileTooLargeError` |
| `ensure_zip_based_format(path)` | `DOCXLoader`, `XLSXLoader` (avant ouverture par la lib tierce) | `CorruptedFileError` |
| `ensure_max_nesting_depth(value, max_depth, filename)` | `JSONLoader` | `JSONParsingError` |
| `ensure_non_empty_content(content, filename, logger=...)` | `PDFLoader`, `DOCXLoader`, `XLSXLoader`, `HTMLLoader` | *(aucune — log un warning uniquement)* |

Contrairement à `utils.py`, ces fonctions lèvent directement des
exceptions métier. Convention : préfixe `ensure_*`, aucun retour en cas
de succès.

### 3.7 Point d'entrée public — `app.data_sources.file`

```python
from app.data_sources.file import load_file, get_loader_class

document = load_file("rapport_maintenance.pdf")   # résolution auto par extension

loader_cls = get_loader_class("data.csv")          # -> CSVLoader
```

- `get_loader_class(path)` lève `UnsupportedFileFormatError` si
  l'extension est absente ou inconnue.
- `load_file(path)` résout le loader puis appelle `.read()` (cycle de
  vie complet garanti).

---

## 4. `app.data_sources.database` — sources base de données

### 4.1 Hiérarchie

```
BaseSource[str]
 └── MySQLSource      (mysql_source.py)   — connexion + exécution SQL
      └── MySQLLoader (mysql_loader.py)   — SQL → SourceDocument
```

`MySQLSource` ne construit **jamais** de `SourceDocument` : c'est la
responsabilité exclusive de `MySQLLoader`.

### 4.2 `MySQLSource` — connexion et exécution

Dépendances : `sqlalchemy` + `pymysql` (import différé, uniquement au
moment de `_connect()`, pour ne pas alourdir l'import du package si
MySQL n'est pas utilisé).

Paramètres de connexion (`__init__`) :

| Paramètre | Obligatoire | Défaut |
|---|---|---|
| `host`, `database`, `user` | oui | — |
| `password` | non | `""` |
| `port` | non | `3306` |
| `charset` | non | `"utf8mb4"` |
| `connect_timeout` | non | `10` (secondes) |

`validate()` vérifie la présence et le type de chaque paramètre
(`DatabaseValidationError` sinon) **sans** tenter de connexion réseau.

`_connect()` traduit les erreurs SQLAlchemy/PyMySQL en exceptions
métier selon le code errno MySQL :

| Errno MySQL | Exception levée |
|---|---|
| `1044, 1045, 1142` (accès refusé) | `DatabaseAuthenticationError` |
| `1049` (base inconnue) | `DatabaseNotFoundError` |
| `2002, 2003, 2005` (connexion impossible) | `DatabaseConnectionError` |
| timeout détecté dans le message | `DatabaseTimeoutError` |
| tout autre `OperationalError` | `DatabaseConnectionError` |
| driver absent (`sqlalchemy`/`pymysql` non installés) | `DatabaseConnectionError` |

`execute_query(sql, params)` exécute une requête **paramétrée**
(jamais d'interpolation directe de valeurs) et traduit les erreurs
d'intégrité/programmation :

| Situation | Exception |
|---|---|
| Violation `UNIQUE`/`PRIMARY KEY` (errno `1062`) | `DuplicateKeyError` |
| Violation `FOREIGN KEY` (errno `1216, 1217, 1451, 1452`) | `ForeignKeyError` |
| Table inexistante (errno `1146`) | `TableNotFoundError` |
| Autre erreur SQL | `QueryExecutionError` |

`validate_identifier(name)` **doit toujours** être utilisée pour tout
nom de table/colonne injecté directement dans une requête (les
identifiants SQL ne peuvent pas être passés en paramètre lié) — motif
`^[A-Za-z_][A-Za-z0-9_]{0,63}$`, sinon `DatabaseValidationError`.

`connect()` / `close()` / `ensure_connected()` **ne sont pas
redéfinis** dans `MySQLSource` : ce sont ceux de `BaseSource`, qui
appellent en interne `_connect()`/`_close()`. Ne pas les redéfinir dans
une future sous-classe sans passer par `_connect_with_state()` /
`_close_with_state()`, sous peine de casser le suivi d'état
(`SourceState`) et les verrous de concurrence.

### 4.3 `MySQLLoader` — SQL → `SourceDocument`

```python
MySQLLoader(
    host="localhost", database="gmao", user="root", password="secret",
    table="interventions",      # XOR query
    query=None,
    max_rows=5000,               # > 0, <= MAX_ROWS_LIMIT (100 000)
    params=None,                 # dict, utilisé uniquement avec `query`
    id_document=None,            # XOR id_panne ; parent GMAO optionnel
    id_panne=None,
)
```

Règles métier (validées dans `__init__`, `DatabaseValidationError`
sinon) :

- **`table` et `query` sont mutuellement exclusifs** — exactement l'un
  des deux doit être fourni.
- Mode `table` → requête construite automatiquement :
  `SELECT * FROM {table_validé} LIMIT {max_rows}` (le nom de table
  passe par `validate_identifier()`).
- Mode `query` → la requête est exécutée telle quelle, avec `params`
  liés (pas de `LIMIT` injecté automatiquement — à la charge de
  l'appelant).
- `max_rows` doit être un entier strictement positif, et ne peut pas
  dépasser `MySQLLoader.MAX_ROWS_LIMIT`.
- Pour un résultat destiné au pipeline de stockage GMAO, fournir exactement
  un parent : `id_document` **ou** `id_panne`. L'ID doit être un entier
  strictement positif ; le loader vérifie son existence dans la table
  `document` ou `panne` avant de charger le résultat.

Quand un parent GMAO est fourni, `MySQLLoader` ajoute `id_document` ou
`id_panne`, ainsi que `id_equipement` lu depuis ce parent, à
`SourceDocument.metadata`. Le parser et les chunkers propagent ces clés vers
`Chunk.metadata`, ce qui satisfait le contrat de `MySQLStorage`. Une requête
générique sans parent reste prise en charge, mais ses chunks ne peuvent pas
être enregistrés par `MySQLStorage`.

```python
document = load_database(
    driver="mysql",
    host="localhost", database="gmao", user="root",
    query="SELECT description FROM panne WHERE id_panne = :id",
    params={"id": 7},
    id_panne=7,
)
```

Conversion des résultats (`_rows_to_text`) : chaque ligne SQL devient un
bloc de paires `colonne: valeur`, séparé des autres lignes par une ligne vide
(favorise un bon découpage par le Chunker). Les numéros de ligne techniques
ne sont pas ajoutés, afin qu'ils ne soient jamais indexés. Les types complexes (`datetime`, `date`, `time`, `Decimal`,
`dict`/`list`/`tuple`, `bytes`) sont normalisés en texte stable via
`_format_value()`.

### 4.4 Point d'entrée public — `app.data_sources.database`

```python
from app.data_sources.database import load_database

document = load_database(
    driver="mysql",
    host="localhost", database="gmao", user="root", password="secret",
    table="interventions",       # ou query="SELECT ..."
    max_rows=5000,
)
```

`load_database()` résout la classe de loader via `DRIVER_LOADER_MAP`
(actuellement : `{"mysql": MySQLLoader}`), l'instancie, puis appelle
`.read()` — le cycle `validate → connect → load → close` est donc
garanti, y compris la fermeture de la connexion SQLAlchemy en cas
d'erreur.

`get_loader_class(driver)` lève `UnsupportedSourceError` si le driver
est vide, non-`str`, ou inconnu de `DRIVER_LOADER_MAP`.

---

## 5. `app.data_sources.orchestrator` — point d'entrée unique

`DataSourceOrchestrator` est la façade recommandée pour le reste de
l'application : elle ne connaît aucun détail des loaders concrets, elle
se contente de résoudre le **type** de source puis déléguer.

```python
from app.data_sources import DataSourceOrchestrator

orchestrator = DataSourceOrchestrator()

# Fichier — résolution automatique
doc = orchestrator.load("reports/maintenance.pdf")

# Base de données — dictionnaire de configuration complet
doc = orchestrator.load({
    "driver": "mysql", "host": "localhost", "database": "gmao",
    "user": "root", "password": "secret", "table": "interventions",
})

# Base de données — kind explicite + kwargs
doc = orchestrator.load(
    "mysql", kind="database",
    host="localhost", database="gmao", user="root", password="secret",
    table="interventions",
)
```

### 5.1 Résolution du type de source

| Entrée | `DataSourceKind` résolu |
|---|---|
| `kind=...` fourni explicitement | celui-ci, prioritaire sur tout |
| `Mapping` contenant `"driver"` | `DATABASE` |
| `Mapping` sans `"driver"` | erreur `UnsupportedSourceError` |
| `str` / `Path` | `FILE` |
| autre type | erreur `UnsupportedSourceError` |

### 5.2 État du support par type de source

| Kind | Support | Détail |
|---|---|---|
| `file` | ✅ Entièrement supporté | txt, md, csv, json, html, docx, pdf, xlsx |
| `database` | ✅ Entièrement supporté | driver `mysql` uniquement |
| `api` | ❌ Non implémenté | `app.data_sources.api` existe mais est vide ; lève `UnsupportedSourceError` (`status: not_implemented`) explicitement plutôt que d'échouer silencieusement |

`orchestrator.supports(kind)` permet de tester la disponibilité d'un
type de source sans déclencher de chargement.

---

## 6. Table de correspondance avec `app.exceptions`

Toutes les exceptions levées par `app.data_sources` proviennent de la
hiérarchie documentée dans `EXCEPTIONS.md`. Rappel des points d'entrée
génériques les plus utiles pour capturer au bon niveau :

| Contexte | Exception à catcher |
|---|---|
| N'importe quelle erreur de ce package | `GMAOError` |
| N'importe quelle erreur de source de données (fichier ou DB) | `DataSourceError` |
| N'importe quelle erreur fichier (validation ET chargement) | `FileError` |
| N'importe quelle erreur base de données | `DatabaseError` |
| Connexion impossible (fichier verrouillé / DB injoignable) | `DataConnectionError` |
| Type de source ou driver non supporté | `UnsupportedSourceError` |

```python
from app.exceptions import FileError, DatabaseError, GMAOError
from app.data_sources import DataSourceOrchestrator

orchestrator = DataSourceOrchestrator()

try:
    doc = orchestrator.load("rapport.pdf")
except FileError as e:
    logger.error("Erreur fichier: %s", e.to_dict())
except DatabaseError as e:
    logger.error("Erreur base de données: %s", e.to_dict())
except GMAOError as e:
    logger.error("Erreur data source non catégorisée: %s", e.to_dict())
```

---

## 7. Pièges connus / règles à ne jamais enfreindre

Ces règles proviennent de l'audit du module (voir Changelog) — à
respecter pour toute contribution future, humaine ou générée par IA.

1. **Toujours consommer une source via `.read()`**, jamais `.load()`
   directement (sauf implémentation interne d'un nouveau loader). Les
   fonctions publiques (`load_file`, `load_database`,
   `DataSourceOrchestrator.load`) le font déjà pour vous.

2. **Ne jamais redéfinir `connect()` / `close()` / `ensure_connected()`**
   dans une sous-classe de `BaseSource` sans passer par
   `_connect_with_state()` / `_close_with_state()` — c'est ce qui
   garantit la cohérence de `SourceState` et la sécurité multi-thread
   (verrous dédiés).

3. **Toute détection d'encodage texte doit passer par**
   `app.data_sources.file.utils.detect_text_encoding()`. Ne pas
   réimplémenter la boucle `try/except UnicodeDecodeError` dans un
   nouveau loader.

4. **Toute validation réutilisable (taille, format ZIP, profondeur
   d'imbrication, contenu vide) doit passer par**
   `app.data_sources.file.validators.py`. Si une règle de validation
   concerne plus d'un loader, elle a sa place ici, pas dupliquée dans
   chaque `load()`.

5. **Les identifiants SQL (noms de table/colonne) ne sont jamais
   interpolés directement** dans une requête sans passer par
   `MySQLSource.validate_identifier()`. Seules les *valeurs* utilisent
   les paramètres liés SQLAlchemy (`:param`).

6. **`table` et `query` sont mutuellement exclusifs** dans
   `MySQLLoader` — ne jamais fournir les deux, ni aucun des deux.

7. **Toute source fichier doit valider son extension** via
   `self.ensure_extension(*self.SUPPORTED_EXTENSIONS)` en tout début
   de `load()`, avant toute lecture.

8. **Import des exceptions depuis le package `app.exceptions`**,
   jamais depuis un sous-module (`app.exceptions.data_source`,
   `app.exceptions.file`...), sauf besoin très spécifique — voir
   `EXCEPTIONS.md` §7 règle 6.

9. **Ne jamais nommer une variable ou un alias local comme un builtin
   Python** (`ConnectionError`, `FileNotFoundError`...) lors de
   l'import d'exceptions métier — voir `EXCEPTIONS.md` §7 règle 1. Les
   noms corrects du projet sont `DataConnectionError` et
   `MissingFileError`.

---

## 8. Comment ajouter un nouveau loader fichier

Checklist pour une IA/un développeur qui doit ajouter le support d'un
nouveau format de fichier :

1. Créer `app/data_sources/file/<format>_loader.py`, classe
   `<Format>Loader(FileSource)`.
2. Définir `SUPPORTED_EXTENSIONS: Final[tuple[str, ...]]`.
3. Implémenter `load()` :
   - `self.validate()` puis `self.ensure_extension(*self.SUPPORTED_EXTENSIONS)` ;
   - si texte : utiliser `detect_text_encoding()` (§3.5), ou hériter
     de `TXTLoader`/`_load_as_text()` si le format est un texte simple
     proche de `.txt`/`.md` ;
   - si binaire tiers (zip-based, etc.) : utiliser les validateurs
     pertinents de `validators.py` (§3.6) avant d'appeler la lib
     tierce ;
   - construire les métadonnées via `dict(self.metadata())` puis
     `.update(...)` avec les champs spécifiques au format ;
   - retourner un `SourceDocument`.
4. Ajouter le mapping extension → classe dans
   `file/__init__.py::_EXTENSION_LOADER_MAP`, et exporter la classe
   dans `__all__`.
5. Documenter le nouveau loader dans la table §3.3 de ce document.
6. Vérifier qu'aucune logique (encodage, validation) n'est dupliquée
   avec un loader existant — factoriser dans `utils.py`/`validators.py`
   si c'est le cas.

---

## Changelog — historique des corrections

| Version | Changement |
|---|---|
| v1 (état initial) | Le package ne s'importait pas (`ConnectionError`/`FileNotFoundError` importés depuis `app.exceptions` sous des noms n'existant plus dans la v2 de ce module) ; `mysql_loader.py` tronqué (syntaxiquement invalide) ; `json_loader.py` contenait un bloc de code mort dupliqué provoquant un `NameError` au chargement ; `MySQLSource` contournait la machine à états de `BaseSource` ; `load_file()`/`load_database()` appelaient `.load()` au lieu de `.read()` ; `MarkdownLoader` ne réutilisait pas réellement la détection d'encodage de `TXTLoader` ; classeur `openpyxl` jamais fermé ; `utils.py`/`validators.py` écrits pour mutualiser du code mais jamais branchés aux loaders (duplication effective malgré leur existence). |
| **v2 (actuelle)** | Tous les points ci-dessus corrigés et vérifiés fonctionnellement : import complet du package, chargement réel de chaque format (txt, md, csv, json, html, docx, pdf, xlsx), gestion correcte de tous les cas d'erreur testés (fichier manquant, extension non supportée, DOCX corrompu, JSON trop imbriqué, fichier vide), cycle de vie `BaseSource` respecté de bout en bout pour MySQL (y compris en cas d'échec de connexion), détection d'encodage et validations réellement mutualisées entre loaders. |

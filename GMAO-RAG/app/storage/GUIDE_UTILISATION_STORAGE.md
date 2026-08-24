# Guide d'utilisation — `app.storage`

Guide pratique d'intégration. Pour la référence complète du contrat,
voir `docs/STORAGE.md`.

---

## 1. Prérequis

### Dépendances
```bash
pip install sqlalchemy pymysql python-dotenv qdrant-client
```

### Variables d'environnement

Deux façons de configurer MySQL — une seule suffit :

```bash
# Option A — DSN direct (priorité la plus haute)
MYSQL_DSN=mysql+pymysql://user:password@host:3306/gmao_db

# Option B — composants séparés (utilisés si MYSQL_DSN absent)
GMAO_DB_HOST=localhost
GMAO_DB_USER=gmao
GMAO_DB_PASSWORD=secret
GMAO_DB_NAME=gmao_db
GMAO_DB_PORT=3306   # optionnel, défaut 3306
```

```bash
# Qdrant — tout est optionnel, défauts raisonnables en local
QDRANT_HOST=localhost           # défaut
QDRANT_PORT=6333                 # défaut
QDRANT_COLLECTION_NAME=gmao_chunks   # défaut
```

Ces variables ne sont lues **qu'à l'instanciation** d'une stratégie
(premier `save()`/`delete()`), jamais à l'import du module ni à
`build_default_registry()` — vous pouvez importer `app.storage`
librement même sans base configurée (utile en test).

---

## 2. Usage basique

```python
from app.storage import build_default_orchestrator

orchestrator = build_default_orchestrator()
report = orchestrator.save(chunks, embeddings)
```

`chunks` et `embeddings` doivent être **alignés** (même longueur, même
ordre) — c'est ce que produisent `app.chunker` et `app.embedding` en
temps normal. `save()` :

1. vérifie l'alignement ;
2. écrit dans MySQL (génère `id_chunk`, met à jour `chunk.metadata`) ;
3. écrit dans Qdrant en utilisant cet `id_chunk` ;
4. si Qdrant réussit, marque les lignes MySQL correspondantes comme
   indexées ;
5. lève `PartialStorageError` si une étape a échoué (comportement par
   défaut — voir §4).

---

## 3. Intégration dans le pipeline complet

```python
from app.data_sources import build_default_orchestrator as build_source_orchestrator
from app.parser import build_default_orchestrator as build_parser_orchestrator
from app.chunker import build_default_orchestrator as build_chunker_orchestrator
from app.embedding import build_default_orchestrator as build_embedding_orchestrator
from app.storage import build_default_orchestrator as build_storage_orchestrator
from app.exceptions import GMAOError, PartialStorageError

def index_document(source_config: dict) -> None:
    source_orchestrator = build_source_orchestrator()
    parser_orchestrator = build_parser_orchestrator()
    chunker_orchestrator = build_chunker_orchestrator(chunk_size=500, chunk_overlap=50)
    embedding_orchestrator = build_embedding_orchestrator()
    storage_orchestrator = build_storage_orchestrator()

    try:
        source_document = source_orchestrator.load(source_config)
        parsed_document = parser_orchestrator.parse(source_document)
        chunks = chunker_orchestrator.chunk(parsed_document)
        embeddings = embedding_orchestrator.embed(chunks)
        report = storage_orchestrator.save(chunks, embeddings)
    except PartialStorageError as exc:
        # Certaines stratégies ont échoué, d'autres non.
        logger.error("Stockage partiel: %s", exc.details["failures"])
        raise
    except GMAOError as exc:
        # Toute autre erreur métier du pipeline (parsing, chunking, etc.)
        logger.error("Échec du pipeline: %s", exc.to_dict())
        raise
    else:
        logger.info(
            "Document indexé (%d chunks, backends: %s)",
            len(chunks),
            [o.strategy_name for o in report.outcomes],
        )
```

**Point bloquant avant que ça fonctionne réellement** : `chunks` doit
porter `id_document` (ou `id_panne`) dans `chunk.metadata` avant
d'atteindre `storage`. Ni `parser` ni `chunker` ne l'injectent
aujourd'hui — voir STORAGE.md §7. Tant que ce n'est pas fait côté
`app.data_sources`, `storage_orchestrator.save()` échouera
systématiquement avec `StorageValidationError`. C'est le prérequis
n°1 à lever avant tout test en conditions réelles.

---

## 4. Gérer les échecs partiels

Par défaut, un échec partiel (une stratégie sur deux, par exemple) lève
`PartialStorageError`. Deux façons de le traiter selon le contexte :

### Job batch (indexation en masse) — laisser lever

```python
try:
    report = orchestrator.save(chunks, embeddings)
except PartialStorageError as exc:
    for failure in exc.details["failures"]:
        logger.error("%s: %s", failure["error_code"], failure["message"])
    # décider : retry, alerte, ou skip selon le contexte métier
```

### Route API — ne pas lever, renvoyer un statut 207

```python
orchestrator = build_default_orchestrator(raise_on_partial_failure=False)

@app.post("/documents/{id}/index")
def index_endpoint(id: str):
    report = orchestrator.save(chunks, embeddings)
    if report.has_failures:
        return JSONResponse(status_code=207, content={"failures": report.failures})
    return JSONResponse(status_code=200, content={"saved": True})
```

### Job critique — échouer immédiatement à la première erreur

```python
orchestrator = build_default_orchestrator(stop_on_failure=True)
# la première StorageError interrompt tout et se propage telle quelle,
# aucun report partiel n'est construit
```

---

## 5. Supprimer des chunks

```python
chunk_ids = [42, 43, 44]  # les id_chunk MySQL, pas les Chunk.chunk_id string
report = orchestrator.delete(chunk_ids)
```

Supprime dans MySQL (`chunk_rag` + tables filles) et dans Qdrant. Même
politique `stop_on_failure`/`raise_on_partial_failure` que `save()`.

---

## 6. Gérer les erreurs spécifiquement

```python
from app.exceptions import (
    StorageValidationError,   # métadonnées manquantes (id_document/id_panne), config invalide
    StorageAlignmentError,    # chunks/embeddings désalignés — bug amont, à ne jamais catcher silencieusement
    StorageConnectionError,   # host injoignable, auth refusée — souvent retryable
    StorageWriteError,        # écriture/suppression échouée sur connexion déjà ouverte
    PartialStorageError,      # succès partiel entre stratégies
)

try:
    report = orchestrator.save(chunks, embeddings)
except StorageAlignmentError:
    # Ne devrait jamais arriver si chunks/embeddings viennent du même
    # pipeline dans le bon ordre. Si ça arrive, c'est un bug amont —
    # ne pas masquer, remonter tel quel.
    raise
except StorageConnectionError:
    # Candidat naturel à un retry avec backoff.
    raise
except PartialStorageError as exc:
    # Voir §4.
    ...
```

---

## 7. Cas d'usage courants

| Besoin | Configuration |
|---|---|
| Indexation batch tolérante aux pannes partielles | défauts (`raise_on_partial_failure=True`, catcher `PartialStorageError`) |
| API synchrone, ne jamais planter sur un échec Qdrant | `raise_on_partial_failure=False`, inspecter `report.has_failures` |
| Job critique, tout ou rien | `stop_on_failure=True` |
| Seulement MySQL (pas de recherche vectorielle pour ce batch) | `strategy_sequence=("mysql",)` |
| Tests sans DB/Qdrant réels | utiliser des stratégies factices enregistrées dans un `StorageRegistry` neuf (voir `manual_test_storage.py`) |

---

## 8. Checklist avant mise en production

- [ ] `MYSQL_DSN` (ou les 3 variables `GMAO_DB_*`) configuré
- [ ] `QDRANT_HOST`/`QDRANT_PORT` accessibles depuis l'environnement de déploiement
- [ ] `id_document`/`id_panne` injectés en amont dans `chunk.metadata` (voir §3 — bloquant)
- [ ] Correctif `error.report` appliqué dans `orchestrator.py` (voir échange précédent)
- [ ] Politique `stop_on_failure`/`raise_on_partial_failure` choisie explicitement selon le contexte d'appel (batch vs API), pas laissée aux défauts sans réflexion
- [ ] Confirmation DBA : `ON DELETE CASCADE` sur `document_chunk`/`panne_chunk` → `chunk_rag` (sinon la suppression explicite déjà en place dans `MySQLStorage.delete()` reste nécessaire, rien à faire de plus)

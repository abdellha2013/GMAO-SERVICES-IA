# Référence — API REST FastAPI (`app.api`)

> **Objectif de ce document** : fournir une référence autonome de la couche
> API REST du projet **GMAO-RAG**, pour les développeurs
> et les assistants IA qui doivent l'utiliser ou l'étendre sans relire
> l'ensemble du code source.
>
> L'API expose le pipeline RAG complet (retrieval, reranking, LLM,
> ingestion, gestion des documents) sous forme de endpoints HTTP
> consommés par le backend Laravel. C'est une couche d'adaptation
> fine — elle ne contient aucune logique métier, elle délègue tout
> aux orchestrateurs existants.
>
> Document complémentaire à `RETRIEVAL.md`, `RERANKER.md`, `LLM.md`,
> `STORAGE.md`, `EXCEPTIONS.md`.

---

## 1. Vue d'ensemble

L'API est le neuvième et dernier étage du pipeline RAG — elle expose
tout le pipeline en HTTP :

```text
        Client (Laravel / curl / notebook)
                     |
        HTTP + Authorization: Bearer <token>
                     |
        +-----------------------------------------+
        |  FastAPI (app.api.main)                 |
        |  +-----------------------------------+  |
        |  | Auth (Bearer token)               |  |
        |  | CORS (allow all)                  |  |
        |  | Timing middleware (ms)            |  |
        |  | GMAOError handler (JSON)          |  |
        |  +-----------------------------------+  |
        +------------------+----------------------+
                           |
        +-----------------------------------------+
        |  Routers v1                            |
        |  /rag ------> RetrievalOrchestrator    |
        |          ---> RerankerOrchestrator     |
        |          ---> LLMOrchestrator          |
        |  /ingest ---> DataSourceOrch           |
        |               ParserOrch               |
        |               ChunkerOrch              |
        |               EmbeddingOrch            |
        |               StorageOrch              |
        |  /documents -> MySQL (requetes directes)|
        |  /health ---> ping Qdrant + MySQL      |
        |  /strategies -> registres              |
        |  /stats ----> compteurs MySQL + Qdrant |
        +-----------------------------------------+
```

### Composition du package

| Fichier | Role |
|---|---|
| `app/api/__init__.py` | Docstring du package — intent de design |
| `app/api/main.py` | App FastAPI, lifespan (startup/shutdown), CORS, middleware timing, handler `GMAOError` |
| `app/api/auth.py` | Verification du Bearer token (`RAG_API_KEY`), mode dev si non configure |
| `app/api/deps.py` | Container singleton de 8 orchestrateurs + fonctions DI `get_*_orchestrator()` |
| `app/api/schemas.py` | Les 22 modeles Pydantic (requests, responses, sub-schemas) |
| `app/api/v1/__init__.py` | Package du router v1 |
| `app/api/v1/rag.py` | Endpoints RAG : `/search`, `/retrieve`, `/rerank` |
| `app/api/v1/ingest.py` | Endpoints ingestion : `/file`, `/database`, `/files` |
| `app/api/v1/documents.py` | Endpoints documents : list, detail, delete |
| `app/api/v1/health.py` | Endpoints systeme : health, strategies, stats |

### Schema de la base de donnees (endpoints documents)

```text
+------------------+     +------------------+     +------------------+
|    document       |     |  document_chunk   |     |    chunk_rag      |
|------------------|     |------------------|     |------------------|
| id_document (PK) |<----| id_document (FK)  |     | id_chunk (PK)    |
| titre            |     | id_chunk (FK)     |---->| contenu           |
| nom_fichier      |     +------------------+     | ordre_chunk      |
| type_fichier     |                              | nombre_tokens    |
| chemin_fichier   |     +------------------+     | type_source      |
| taille           |     |   panne_chunk     |     | statut_embedding |
| version          |     |------------------|     | date_indexation  |
| date_importation |     | id_chunk (FK)     |---->+                  |
| statut_indexation|     | id_panne (FK)     |     +------------------+
| description      |     +------------------+
| id_equipement    |              |
+------------------+     +-------+----------+
                          |     panne         |
                          |------------------|
                          | id_panne (PK)    |
                          | titre            |
                          | description      |
                          | gravite          |
                          | date_detection   |
                          | cause            |
                          | solution         |
                          | symptomes        |
                          | statut_indexation|
                          | id_equipement    |
                          | id_ot            |
                          +------------------+
```

> **Piege connu** : `chunk_rag` n'a PAS de colonnes `id_document`,
> `id_panne`, `score`, `rank_position`, `source_name` ni
> `retrieval_strategy`. L'association chunk<->document se fait via la
> table de jonction `document_chunk` (ou `panne_chunk` pour les pannes).

---

## 2. Demarrage

### Lancer le serveur

```bash
cd /home/abdellah-daif/GMAO-RAG
PYTHONPATH=. .venv/bin/python -m uvicorn app.api.main:app \
    --host 0.0.0.0 --port 8000 --reload
```

### Points d'acces

| URL | Description |
|---|---|
| `http://localhost:8000/docs` | Swagger UI (interface interactive) |
| `http://localhost:8000/redoc` | ReDoc (documentation Readme-style) |
| `http://localhost:8000/openapi.json` | OpenAPI JSON brut |
| `http://localhost:8000/api/v1/health` | Health check (pas d'auth) |

### Variables d'environnement

| Variable | Requis | Defaut | Description |
|---|---|---|---|
| `RAG_API_KEY` | Non | *(aucun)* | Cle API pour l'auth. Si non definie, l'auth est **desactivee** (mode dev) |
| `MYSQL_DSN` | Non | construit depuis `GMAO_DB_*` | DSN SQLAlchemy complet |
| `GMAO_DB_HOST` | Non | `localhost` | Host MySQL |
| `GMAO_DB_PORT` | Non | `3306` | Port MySQL |
| `GMAO_DB_USER` | Non | `root` | Utilisateur MySQL |
| `GMAO_DB_PASSWORD` | Non | `""` | Mot de passe MySQL |
| `GMAO_DB_NAME` | Non | `gmao` | Nom de la base MySQL |
| `QDRANT_HOST` | Non | `localhost` | Host Qdrant |
| `QDRANT_PORT` | Non | `6333` | Port Qdrant |
| `QDRANT_COLLECTION_NAME` | Non | `gmao_chunks` | Nom de la collection Qdrant |

---

## 3. Authentification

L'authentification utilise un **Bearer token** dans le header
`Authorization` :

```text
Authorization: Bearer <RAG_API_KEY>
```

### Comportement selon la configuration

| Etat de `RAG_API_KEY` | Comportement |
|---|---|
| **Non definie** (mode dev) | Toute requete avec header `Authorization` est acceptee. La valeur du token est ignoree, retourne `"dev-mode"` |
| **Definie** (mode prod) | Le token doit correspondre exactement a la valeur de `RAG_API_KEY` |

### Reponses d'authentification

| Cas | Code | Body |
|---|---|---|
| Token valide ou mode dev | `200` | Reponse de l'endpoint |
| Token invalide (mauvaise cle) | `401` | `{"detail": "Invalid API key."}` |
| Header malforme (pas de "Bearer ") | `401` | `{"detail": "Missing or malformed Authorization header..."}` |
| Header `Authorization` manquant | `422` | Erreur de validation FastAPI (champ requis) |

> **Note** : L'endpoint `/api/v1/health` ne necessite **aucune**
> authentification — concu pour les load balancers et le monitoring.

---

## 4. Endpoints RAG

### 4.1 POST `/api/v1/rag/retrieve` — Retrieval seul

Recherche de chunks pertinents sans reranking ni generation LLM.

**Auth** : requise

#### Body (JSON)

| Champ | Type | Requis | Contrainte | Description |
|---|---|---|---|---|
| `query` | string | Oui | `min_length=1` | Requete utilisateur (texte libre) |
| `filters` | object | Non | — | Filtres optionnels (voir S8 `FilterParams`) |
| `top_k` | int | Non | `ge=1, le=50` | Nombre de resultats (defaut: 5) |

#### Reponse `200`

```json
{
  "query": "pompe vibration",
  "results": [
    {
      "chunk_id": "112",
      "content": "Vibration anormale sur pompe centrifuge...",
      "score": 0.879,
      "rank": 1,
      "source_name": "panne:7",
      "source_type": "panne",
      "id_document": null,
      "id_panne": 7,
      "id_equipement": 224,
      "retrieval_strategy": "qdrant"
    }
  ],
  "total_candidates": 52,
  "strategy_name": "qdrant"
}
```

#### Exemple curl

```bash
curl -s http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "pompe vibration", "top_k": 5}'
```

#### Erreurs

| Code | Cause |
|---|---|
| `400` | Query vide, top_k invalide |
| `401` | Token invalide |
| `422` | Body manquant ou champs obligatoires absents |
| `503` | Qdrant inaccessible (`RETRIEVAL_CONNECTION_ERROR`) |

---

### 4.2 POST `/api/v1/rag/rerank` — Reranking seul

Re-classement des chunks via un Cross-Encoder. Les candidats doivent
etre fournis dans le body (resultats de `/retrieve`).

**Auth** : requise

#### Body (JSON)

| Champ | Type | Requis | Contrainte | Description |
|---|---|---|---|---|
| `query` | string | Oui | `min_length=1` | Requete originale |
| `candidates` | list | Oui | `min_length=1` | Liste de `RetrievedChunkSchema` (issus de `/retrieve`) |
| `top_k` | int | Non | `ge=1, le=50` | Nombre de resultats apres reranking |

#### Reponse `200`

```json
{
  "query": "pompe vibration",
  "results": [
    {
      "chunk_id": "112",
      "content": "Vibration anormale...",
      "source_name": "panne:7",
      "source_type": "panne",
      "retrieval_score": 0.879,
      "rerank_score": 0.952,
      "rank": 1,
      "id_document": null,
      "id_panne": 7,
      "id_equipement": 224,
      "retrieval_strategy": "qdrant",
      "reranker_strategy": "cross-encoder"
    }
  ]
}
```

#### Exemple curl

```bash
# D'abord recuperer des chunks
CHUNKS=$(curl -s http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "pompe vibration", "top_k": 5}')

# Puis les reranker
curl -s http://localhost:8000/api/v1/rag/rerank \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"pompe vibration\", \"candidates\": $CHUNKS, \"top_k\": 3}"
```

#### Erreurs

| Code | Cause |
|---|---|
| `400` | Query vide, candidats vides |
| `401` | Token invalide |
| `422` | Champs requis manquants dans les candidats |

---

### 4.3 POST `/api/v1/rag/search` — Pipeline complet

Pipeline complet : retrieve -> rerank (optionnel) -> generate (optionnel).
C'est l'endpoint principal pour une requete RAG complete.

**Auth** : requise

#### Body (JSON)

| Champ | Type | Requis | Contrainte | Description |
|---|---|---|---|---|
| `query` | string | Oui | `min_length=1` | Requete utilisateur |
| `filters` | object | Non | — | Filtres optionnels |
| `top_k` | int | Non | `ge=1, le=50` | Nombre de resultats (defaut: 5) |
| `rerank` | bool | Non | — | Activer le reranking (defaut: `true`) |
| `generate` | bool | Non | — | Activer la generation LLM (defaut: `true`) |
| `llm_strategy` | string | Non | — | Strategie LLM (ex: `"gemini"`, `"openai"`) |

#### Configurations possibles

| `rerank` | `generate` | Comportement |
|---|---|---|
| `true` | `true` | Pipeline complet : retrieve -> rerank -> LLM |
| `false` | `true` | Rapide : retrieve -> LLM (sans reranking) |
| `true` | `false` | Reranking seul : retrieve -> rerank, pas de reponse textuelle |
| `false` | `false` | Retrieval seul : chunks bruts sans reranking ni LLM |

#### Reponse `200`

```json
{
  "answer": "Les vibrations sur les pompes centrifuges sont souvent causees par...",
  "query": "pompe vibration",
  "citations": [
    {
      "chunk_id": "112",
      "source_name": "panne:7",
      "source_type": "panne",
      "rerank_score": 0.952
    }
  ],
  "results": [
    {
      "chunk_id": "112",
      "content": "Vibration anormale...",
      "source_name": "panne:7",
      "source_type": "panne",
      "retrieval_score": 0.879,
      "rerank_score": 0.952,
      "rank": 1,
      "id_document": null,
      "id_panne": 7,
      "id_equipement": 224,
      "retrieval_strategy": "qdrant",
      "reranker_strategy": "cross-encoder"
    }
  ],
  "strategy_info": {
    "retrieval": "qdrant",
    "reranker": "cross-encoder",
    "llm": "openai"
  },
  "duration_ms": 2345.67
}
```

> Quand `generate=false` ou `rerank=false`, les champs correspondants
> sont vides : `answer=""`, `citations=[]`, `reranker_strategy="none"`.

#### Exemple curl

```bash
# Pipeline complet
curl -s http://localhost:8000/api/v1/rag/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quelles sont les causes frequentes de panne sur les pompes ?",
    "top_k": 5,
    "rerank": true,
    "generate": true
  }'

# Sans LLM (plus rapide, pas besoin de credits OpenAI/Gemini)
curl -s http://localhost:8000/api/v1/rag/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "vibration moteur",
    "rerank": false,
    "generate": false
  }'
```

#### Erreurs

| Code | Cause |
|---|---|
| `400` | Query vide |
| `401` | Token invalide |
| `422` | Body manquant |
| `429` | Credits OpenAI/Gemini epuises (`LLM_RATE_LIMIT_ERROR`) |
| `500` | Erreur LLM interne |
| `503` | Qdrant inaccessible |

---

## 5. Endpoints Ingestion

### 5.1 POST `/api/v1/ingest/file` — Upload fichier

Upload d'un fichier via `multipart/form-data`. Le fichier est traite
par le pipeline complet : load -> parse -> chunk -> embed -> stocker.

**Auth** : requise
**Content-Type** : `multipart/form-data`

#### Champs du formulaire

| Champ | Type | Requis | Defaut | Description |
|---|---|---|---|---|
| `file` | file | Oui | — | Fichier a ingérer (PDF, DOCX, TXT, HTML, CSV, JSON, XLSX, MD) |
| `id_equipement` | int | Non | `null` | ID equipement parent |
| `chunk_size` | int | Non | `500` | Taille max des chunks (100-5000) |
| `chunk_overlap` | int | Non | `50` | Chevauchement entre chunks (0-500) |

#### Reponse `200`

```json
{
  "status": "ok",
  "results": [
    {
      "status": "ok",
      "document_name": "mon_fichier.txt",
      "chunks_count": 12,
      "duration_ms": 1523.45,
      "error": null
    }
  ],
  "total_files": 1,
  "success_count": 1,
  "error_count": 0
}
```

#### Exemple curl

```bash
curl -s http://localhost:8000/api/v1/ingest/file \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -F "file=@mon_fichier.txt" \
  -F "id_equipement=42" \
  -F "chunk_size=300"
```

#### Erreurs

| Code | Cause |
|---|---|
| `401` | Token invalide |
| `422` | Fichier manquant dans le body |
| `500` | Erreur pipeline (format non supporte, etc.) |

> Le fichier est automatiquement supprime du disque apres ingestion
> (via `tempfile.NamedTemporaryFile`).

---

### 5.2 POST `/api/v1/ingest/database` — Ingestion MySQL

Ingestion depuis une table MySQL ou une requete SQL custom.

**Auth** : requise

#### Body (JSON)

| Champ | Type | Requis | Contrainte | Description |
|---|---|---|---|---|
| `driver` | string | Non | — | Pilote (defaut: `"mysql"`) |
| `host` | string | Oui | `min_length=1` | Host MySQL |
| `port` | int | Non | `gt=0` | Port (defaut: 3306) |
| `database` | string | Oui | `min_length=1` | Nom de la base |
| `user` | string | Oui | `min_length=1` | Utilisateur |
| `password` | string | Oui | `min_length=0` | Mot de passe |
| `table` | string | Oui | `min_length=1` | Table source |
| `query` | string | Non | — | SQL custom (remplace `table` si fourni) |
| `id_equipement` | int | Non | `gt=0` | ID equipement parent |
| `chunk_size` | int | Non | `ge=100, le=5000` | Taille max chunks (defaut: 500) |
| `chunk_overlap` | int | Non | `ge=0, le=500` | Chevauchement (defaut: 50) |

#### Exemple curl

```bash
# Depuis une table
curl -s http://localhost:8000/api/v1/ingest/database \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "127.0.0.1",
    "database": "gmao",
    "user": "root",
    "password": "",
    "table": "pannes",
    "id_equipement": 1
  }'

# Avec requete SQL custom
curl -s http://localhost:8000/api/v1/ingest/database \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "127.0.0.1",
    "database": "gmao",
    "user": "root",
    "password": "",
    "table": "pannes",
    "query": "SELECT * FROM pannes LIMIT 10",
    "id_equipement": 1
  }'
```

---

### 5.3 POST `/api/v1/ingest/files` — Batch ingestion

Ingestion de plusieurs fichiers deja presents sur le serveur
(par chemin absolu). Chaque fichier est traite independamment —
une erreur sur un fichier n'empeche pas les autres.

**Auth** : requise

#### Body (JSON)

| Champ | Type | Requis | Contrainte | Description |
|---|---|---|---|---|
| `paths` | list[str] | Oui | `min_length=1` | Chemins absolus des fichiers sur le serveur |
| `id_equipement` | int | Non | `gt=0` | ID equipement parent |
| `chunk_size` | int | Non | `ge=100, le=5000` | Taille max chunks |
| `chunk_overlap` | int | Non | `ge=0, le=500` | Chevauchement |

#### Reponse `200`

```json
{
  "status": "partial",
  "results": [
    {
      "status": "ok",
      "document_name": "/chemin/fichier1.txt",
      "chunks_count": 5,
      "duration_ms": 800.12,
      "error": null
    },
    {
      "status": "error",
      "document_name": "/chemin/inexistant.txt",
      "chunks_count": 0,
      "duration_ms": 23.45,
      "error": "FileNotFoundError: ..."
    }
  ],
  "total_files": 2,
  "success_count": 1,
  "error_count": 1
}
```

Les valeurs possibles de `status` (racine) :
- `"ok"` : tous les fichiers ont reussi
- `"partial"` : certains ont reussi, d'autres non
- `"error"` : aucun n'a reussi

#### Exemple curl

```bash
curl -s http://localhost:8000/api/v1/ingest/files \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "paths": ["/home/user/doc1.txt", "/home/user/doc2.pdf"],
    "id_equipement": 42
  }'
```

---

## 6. Endpoints Documents

Ces endpoints interrogent **directement MySQL** (pas les orchestrateurs).
Ils fournissent la gestion des documents indexes.

### 6.1 GET `/api/v1/documents/` — Liste des documents

Retourne tous les documents avec leur nombre de chunks.
Le champ `indexed` est derive de `statut_indexation = 'Indexe'`.

**Auth** : requise

#### Reponse `200`

```json
{
  "documents": [
    {
      "id": 1,
      "name": "sample-5pages.docx",
      "source_type": "DOCX",
      "chunks_count": 19,
      "indexed": false
    }
  ],
  "total": 1
}
```

#### Exemple curl

```bash
curl -s http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer $RAG_API_KEY"
```

---

### 6.2 GET `/api/v1/documents/{document_id}` — Detail document

Retourne les metadonnees du document et tous ses chunks
(via la table de jonction `document_chunk`).

**Auth** : requise

#### Reponse `200`

```json
{
  "document": {
    "id": 1,
    "name": "sample-5pages.docx",
    "source_type": "DOCX",
    "chunks_count": 19,
    "indexed": false
  },
  "chunks": [
    {
      "chunk_id": "69",
      "content": "Introduction to Digital Documents...",
      "score": 0.0,
      "rank": 0,
      "source_name": "sample-5pages.docx",
      "source_type": "Document",
      "id_document": 1,
      "id_panne": null,
      "id_equipement": null,
      "retrieval_strategy": ""
    }
  ]
}
```

#### Erreurs

| Code | Cause |
|---|---|
| `404` | Document non trouve |
| `422` | ID invalide (non entier) |

---

### 6.3 DELETE `/api/v1/documents/{document_id}` — Supprimer document

Supprime un document et toutes ses donnees associees :
- Lignes dans `document_chunk` (jonction)
- Chunks dans `chunk_rag`
- Enregistrement dans `document`

**Auth** : requise

#### Reponse `200`

```json
{
  "status": "ok",
  "deleted_chunks": 19
}
```

#### Exemple curl

```bash
curl -s -X DELETE http://localhost:8000/api/v1/documents/1 \
  -H "Authorization: Bearer $RAG_API_KEY"
```

#### Erreurs

| Code | Cause |
|---|---|
| `404` | Document non trouve |

> **Attention** : Cette operation est **irreversible**. Les chunks
> et l'enregistrement document sont supprimes de MySQL.

---

## 7. Endpoints Systeme

### 7.1 GET `/api/v1/health` — Health check

Verifie la connectivite a Qdrant et MySQL. **Aucune authentification requise**
(concu pour les load balancers et le monitoring).

#### Reponse `200`

```json
{
  "status": "healthy",
  "qdrant": "ok",
  "mysql": "ok",
  "version": "0.1.0"
}
```

Valeurs de `status` :
- `"healthy"` : Qdrant et MySQL joignables
- `"degraded"` : un seul backend joignable
- `"unhealthy"` : aucun backend joignable

#### Exemple curl

```bash
curl -s http://localhost:8000/api/v1/health
```

---

### 7.2 GET `/api/v1/strategies` — Strategies disponibles

Retourne les noms des strategies enregistrees dans chaque registre du pipeline.

**Auth** : requise

#### Reponse `200`

```json
{
  "retrieval": ["qdrant", "hybrid"],
  "reranker": ["cross-encoder"],
  "llm": ["openai", "gemini"],
  "embedding": ["e5-small-v2"]
}
```

---

### 7.3 GET `/api/v1/stats` — Statistiques

Retourne les compteurs de la base et de Qdrant.

**Auth** : requise

#### Reponse `200`

```json
{
  "documents_count": 1,
  "chunks_count": 52,
  "qdrant_points": 52
}
```

> `qdrant_points` est `null` si Qdrant est injoignable.

---

## 8. Schemas Pydantic

### Naming convention

| Prefixe | Role | Exemple |
|---|---|---|
| `*Request` | Body d'un POST (entree) | `SearchRequest` |
| `*Response` | Corps retourne (sortie) | `SearchResponse` |
| `*Schema` | Sous-objet reutilisable | `RetrievedChunkSchema` |

### Sub-schemas partages

#### `FilterParams`

Filtres optionnels appliques aux chunks recuperes. Tous les champs
sont optionnels. Lorsque plusieurs sont fournis, ils sont combines
avec une logique AND.

| Champ | Type | Contrainte | Description |
|---|---|---|---|
| `id_document` | int \| None | `gt=0` | Filtrer les chunks d'un document |
| `id_panne` | int \| None | `gt=0` | Filtrer les chunks d'une panne |
| `id_equipement` | int \| None | `gt=0` | Filtrer les chunks d'un equipement |
| `source_type` | string \| None | — | Type de source (`"document"`, `"panne"`) |
| `min_score` | float \| None | — | Score minimum de pertinence |

#### `StrategyInfo`

| Champ | Type | Description |
|---|---|---|
| `retrieval` | string \| None | Nom de la strategie de retrieval |
| `reranker` | string \| None | Nom de la strategie de reranking |
| `llm` | string \| None | Nom de la strategie LLM |

### Modeles de chunks

#### `RetrievedChunkSchema`

| Champ | Type | Description |
|---|---|---|
| `chunk_id` | string | Identifiant unique du chunk |
| `content` | string | Contenu textuel |
| `score` | float | Score de pertinence (retrieval) |
| `rank` | int | Rang final (1-indexe) |
| `source_name` | string | Nom de la source |
| `source_type` | string | Type (`"document"`, `"panne"`) |
| `id_document` | int \| None | ID document parent |
| `id_panne` | int \| None | ID panne parent |
| `id_equipement` | int \| None | ID equipement lie |
| `retrieval_strategy` | string | Strategie de retrieval utilisee |

#### `RankedChunkSchema`

| Champ | Type | Description |
|---|---|---|
| `chunk_id` | string | Identifiant unique |
| `content` | string | Contenu textuel |
| `source_name` | string | Nom de la source |
| `source_type` | string | Type de source |
| `retrieval_score` | float | Score retrieval original |
| `rerank_score` | float | Score de reranking |
| `rank` | int | Rang apres reranking |
| `id_document` | int \| None | ID document parent |
| `id_panne` | int \| None | ID panne parent |
| `id_equipement` | int \| None | ID equipement lie |
| `retrieval_strategy` | string | Strategie de retrieval |
| `reranker_strategy` | string | Strategie de reranking |

#### `CitationSchema`

| Champ | Type | Description |
|---|---|---|
| `chunk_id` | string | ID du chunk cite |
| `source_name` | string | Nom de la source citee |
| `source_type` | string | Type de la source citee |
| `rerank_score` | float | Score de reranking du chunk cite |

### Modeles d'ingestion

#### `IngestResult`

| Champ | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"partial"` ou `"error"` |
| `document_name` | string | Nom du fichier |
| `chunks_count` | int | Nombre de chunks crees |
| `duration_ms` | float | Duree d'ingestion (ms) |
| `error` | string \| None | Message d'erreur si echec |

#### `IngestResponse`

| Champ | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"partial"` ou `"error"` |
| `results` | list[IngestResult] | Resultats par fichier |
| `total_files` | int | Fichiers traites |
| `success_count` | int | Fichiers reussis |
| `error_count` | int | Fichiers echoues |

### Modeles Documents

#### `DocumentSummary`

| Champ | Type | Description |
|---|---|---|
| `id` | int | ID du document |
| `name` | string | Nom du fichier |
| `source_type` | string | Type de fichier |
| `chunks_count` | int | Nombre de chunks |
| `indexed` | bool | `statut_indexation == 'Indexe'` |

---

## 9. Codes d'erreur

### Mapping GMAOError -> HTTP

| Exception | HTTP | `error_code` |
|---|---|---|
| `EmptyQueryError` | 400 | `RETRIEVAL_EMPTY_QUERY` |
| `RetrievalValidationError` | 400 | `RETRIEVAL_*` |
| `RerankerValidationError` | 400 | `RERANKER_*` |
| `LLMValidationError` | 400 | `LLM_*` |
| `RetrievalConnectionError` | 503 | `RETRIEVAL_CONNECTION_ERROR` |
| `LLMRateLimitError` | 429 | `LLM_RATE_LIMIT_ERROR` |
| `LLMConnectionError` | 502 | `LLM_CONNECTION_ERROR` |
| Autre `GMAOError` | `exc.http_status` ou 500 | Variable |

### Format de reponse d'erreur

```json
{
  "type": "LLMRateLimitError",
  "message": "OpenAI rate limit or quota exceeded.",
  "error_code": "LLM_RATE_LIMIT_ERROR",
  "http_status": 429,
  "details": {
    "model_name": "gpt-4o-mini"
  }
}
```

Les erreurs non-GMAOError (exceptions Python non anticipees) retournent :

```json
{
  "detail": "Internal server error"
}
```

### En-tetes de reponse

| En-tete | Description |
|---|---|
| `X-Process-Time` | Duree totale de la requete en secondes (ajoute par le middleware) |

---

## 10. Pieges connus

### 10.1 Trailing slash (307 Redirect)

FastAPI redirige automatiquement `/api/v1/documents` vers
`/api/v1/documents/` (307 Temporary Redirect). Les clients `curl`
ne suivent pas les redirects par defaut — utilisez `-L` ou ajoutez
le `/` final :

```bash
# FAUX — retourne 307
curl http://localhost:8000/api/v1/documents

# CORRECT
curl -L http://localhost:8000/api/v1/documents
curl http://localhost:8000/api/v1/documents/    # avec /
```

### 10.2 chunk_rag n'a pas de colonnes liees aux parents

La table `chunk_rag` ne contient que :
`id_chunk`, `contenu`, `ordre_chunk`, `nombre_tokens`, `type_source`,
`statut_embedding`, `date_indexation`.

Elle n'a **pas** `id_document`, `id_panne`, `score`, `rank_position`,
`source_name` ni `retrieval_strategy`.

L'association se fait via les tables de jonction :
- `document_chunk(id_chunk, id_document)` pour les documents
- `panne_chunk(id_chunk, id_panne)` pour les pannes

### 10.3 statut_indexation vs indexed

La colonne MySQL est `statut_indexation` (enum : `En_attente`,
`Indexe`, `Echec`). L'API la convertit en booleen `indexed` dans
les reponses (`true` si `statut_indexation == 'Indexe'`).

### 10.4 Mode dev (pas de RAG_API_KEY)

Si `RAG_API_KEY` n'est pas defini dans l'environnement, l'authentification
est entierement desactivee. Le header `Authorization` reste requis par
FastAPI (champ `Header(..., alias="Authorization")`), mais n'importe
quelle valeur est acceptee.

### 10.5 Credits OpenAI/Gemini epuises

Quand `generate=true` dans `/search`, l'endpoint appele le LLM.
Si les credits sont epuises, il retourne une erreur `429` au lieu
d'une reponse `200`. Pour eviter cela, utilisez `generate=false`.

---

## 11. Changelog

| Version | Date | Modifications |
|---|---|---|
| v1 | 2026-08-21 | Creation initiale — 12 endpoints, 22 schemas, auth, erreurs, pieges |

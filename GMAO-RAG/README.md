# GMAO-RAG

Système **RAG** (Retrieval-Augmented Generation) pour la **GMAO** (Gestion de Maintenance Assistée par Ordinateur).

> Indexe des documents techniques et des données de pannes, puis répond
> aux questions des maintenanceiens via une API REST.

---

## Vue d'ensemble

```
Backend Laravel (port 80/443)
        │  HTTP + Bearer token
        ▼
   FastAPI (port 8000)
        │
        ├── Ingestion : fichier / MySQL → chunks → embeddings → Qdrant + MySQL
        │
        └── Recherche : query → retrieval → reranking → LLM → réponse JSON
```

### Technologies

| Composant | Technologie |
|-----------|-------------|
| Langage | Python 3.13+ |
| API | FastAPI + Uvicorn |
| Base vectorielle | Qdrant (port 6333) |
| Base relationnelle | MySQL 8+ (port 3306) |
| Embeddings | sentence-transformers (`multilingual-e5-small`, 384 dim) |
| Reranking | Cross-Encoder (`ms-marco-MiniLM`) |
| LLM | OpenAI (`gpt-4o-mini`) / Gemini (`gemini-2.5-flash`) |
| ORM | SQLAlchemy |
| Dépendances | uv |

---

## Pipeline RAG

Le pipeline se compose de **9 couches**, chacune suivant le même patron :
`Interface (ABC)` → `Stratégies` → `Registre` → `Orchestrateur`.

```
INGESTION (écriture) :
  1. DataSource    Fichier/DB brut        → Document
  2. Parser        Extraction texte       → ParsedDocument
  3. Chunker       Découpage              → [Chunk]
  4. Embedding     Vecteurs sémantiques   → [Embedding]
  5. Storage       MySQL + Qdrant         → persisté

RECHERCHE (lecture) :
  6. Retrieval     Recherche vectorielle  → [RetrievedChunk]
  7. Reranker      Re-classement          → [RankedChunk]
  8. LLM           Génération             → LLMResponse

API :
  9. FastAPI       12 endpoints REST      → JSON pour Laravel
```

---

## Démarrage rapide avec Docker (recommandé)

La méthode la plus simple pour lancer le projet sur une nouvelle machine :

```bash
# 1. Cloner le projet
git clone https://github.com/abdellha2013/GMAO-RAG.git
cd GMAO-RAG

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés API (OPENAI_API_KEY, etc.)

# 3. Tout lancer (MySQL + Qdrant + API)
docker compose up --build

# 4. Vérifier
curl http://localhost:8000/api/v1/health
```

**Ce que lance Docker Compose :**

| Service | Port | Description |
|---------|------|-------------|
| `gmao-api` | 8000 | API FastAPI (application principale) |
| `gmao-mysql` | 3306 | MySQL 8.0 (base relationnelle) |
| `gmao-qdrant` | 6333 | Qdrant (base vectorielle) |

**Commandes utiles :**

```bash
docker compose up --build          # Tout lancer (avec rebuild)
docker compose up -d               # En arrière-plan
docker compose logs -f app         # Voir les logs de l'API
docker compose down                # Tout arrêter
docker compose down -v             # Arrêter + supprimer les données
```

> L'entrypoint attend automatiquement que MySQL et Qdrant soient prêts,
> crée la collection Qdrant, puis lance l'API.

---

## Prérequis (installation manuelle)

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (gestionnaire de dépendances)
- MySQL 8.0+ (port 3306)
- [Qdrant](https://qdrant.tech/) (port 6333)
- Git

---

## Installation (sans Docker)

### 1. Cloner le projet

```bash
git clone https://github.com/abdellha2013/GMAO-RAG.git
cd GMAO-RAG
```

### 2. Installer uv (si pas encore installé)

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Créer l'environnement virtuel

```bash
# Créer le venv
uv venv --python 3.13

# Activer le venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Installer les dépendances
uv pip install -e .
```

### 4. Lancer MySQL et créer la base

```bash
# Démarrer MySQL
sudo systemctl start mysql       # Linux (systemd)
# brew services start mysql      # macOS (Homebrew)

# Créer la base et les tables
mysql -u root -p < db/mysql/creation_bdd_rag_gmao.sql

# Vérifier
mysql -u root -p -e "SHOW DATABASES;" | grep gmao_rag
```

### 5. Lancer Qdrant et créer la collection

```bash
# Démarrer Qdrant (Docker)
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# Créer la collection vectorielle
PYTHONPATH=. python db/qdrant/creation_qdrant_rag_gmao.py

# Vérifier
curl http://localhost:6333/collections
```

### 6. Configurer .env

```bash
# Le fichier .env doit contenir (adapter à votre config) :
```

```env
PYTHONPATH=/chemin/vers/GMAO-RAG

# MySQL
MYSQL_DSN=mysql+pymysql://root:VOTRE_MDP@127.0.0.1:3306/gmao_rag

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=gmao_chunks

# Embeddings
EMBEDDING_SMALL_MODEL_NAME=intfloat/multilingual-e5-small
EMBEDDING_DEVICE=auto

# LLM OpenAI
OPENAI_API_KEY=sk-proj-VOTRE_CLE
LLM_MODEL_NAME=gpt-4o-mini

# LLM Gemini (optionnel)
GEMINI_MODEL_NAME=gemini-2.5-flash
GOOGLE_API_KEY=VOTRE_CLE

# Auth API
RAG_API_KEY=VOTRE_TOKEN_SECU
```

---

## Lancement

### Serveur de développement

```bash
PYTHONPATH=. uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Vérifier que ça marche

```bash
# Health check (pas d'auth requise)
curl http://localhost:8000/api/v1/health
# → {"status":"healthy","qdrant":"ok","mysql":"ok","version":"0.1.0"}

# Swagger UI (navigateur)
open http://localhost:8000/docs
```

### Production

```bash
PYTHONPATH=. uvicorn app.api.main:app \
  --host 0.0.0.0 --port 8000 --workers 4 --log-level info
```

---

## Endpoints API

Tous les endpoints sont préfixés par `/api/v1`.
L'auth utilise un Bearer token : `Authorization: Bearer <RAG_API_KEY>`.

### RAG

| Méthode | Endpoint | Auth | Description |
|---------|----------|------|-------------|
| POST | `/rag/search` | Oui | Pipeline complet (retrieve → rerank → LLM) |
| POST | `/rag/retrieve` | Oui | Retrieval seul |
| POST | `/rag/rerank` | Oui | Reranking seul |

### Ingestion

| Méthode | Endpoint | Auth | Description |
|---------|----------|------|-------------|
| POST | `/ingest/file` | Oui | Upload fichier (multipart/form-data) |
| POST | `/ingest/database` | Oui | Ingestion depuis MySQL |
| POST | `/ingest/files` | Oui | Batch ingestion (chemins serveur) |

### Documents

| Méthode | Endpoint | Auth | Description |
|---------|----------|------|-------------|
| GET | `/documents/` | Oui | Liste des documents |
| GET | `/documents/{id}` | Oui | Détail document |
| DELETE | `/documents/{id}` | Oui | Supprimer document |

### Système

| Méthode | Endpoint | Auth | Description |
|---------|----------|------|-------------|
| GET | `/health` | Non | Health check (Qdrant + MySQL) |
| GET | `/strategies` | Oui | Stratégies disponibles |
| GET | `/stats` | Oui | Statistiques pipeline |

---

## Exemples d'utilisation

### Health check

```bash
curl http://localhost:8000/api/v1/health
```

### Recherche RAG

```bash
curl -s http://localhost:8000/api/v1/rag/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quelles sont les causes de panne sur les pompes ?",
    "top_k": 5,
    "rerank": true,
    "generate": true
  }'
```

### Retrieval seul (rapide, sans LLM)

```bash
curl -s http://localhost:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "vibration moteur", "top_k": 5}'
```

### Upload de fichier

```bash
curl -s http://localhost:8000/api/v1/ingest/file \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -F "file=@mon_document.pdf" \
  -F "id_equipement=42"
```

### Ingestion depuis MySQL

```bash
curl -s http://localhost:8000/api/v1/ingest/database \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "127.0.0.1",
    "database": "gmao_rag",
    "user": "root",
    "password": "VOTRE_MDP",
    "table": "panne",
    "id_equipement": 1
  }'
```

### Lister les documents

```bash
# ⚠️ Le trailing slash est obligatoire !
curl -s http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer $RAG_API_KEY"
```

---

## Tests

### Tests automatisés (332 tests)

```bash
# Tous les tests
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/ -v

# Tests par couche
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/retrieval/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/reranker/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/llm/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/api/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/chunker/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/parser/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/embedding/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/storage/ -v
PYTHONPATH=. .venv/bin/python -m pytest tests/unit/data_sources/ -v
```

### Tests manuels (API live)

```bash
# Vérifier que le serveur tourne sur http://localhost:8000
PYTHONPATH=. .venv/bin/python tests/manual/all_api.py
# → 51 tests, PASS/FAIL pour chaque endpoint
```

---

## Variables d'environnement

| Variable | Requis | Défaut | Description |
|----------|--------|--------|-------------|
| `MYSQL_DSN` | Non | composé | DSN SQLAlchemy complet |
| `GMAO_DB_HOST` | Non | `localhost` | Host MySQL |
| `GMAO_DB_PORT` | Non | `3306` | Port MySQL |
| `GMAO_DB_USER` | Non | `root` | Utilisateur MySQL |
| `GMAO_DB_PASSWORD` | Non | `(vide)` | Mot de passe MySQL |
| `GMAO_DB_NAME` | Non | `gmao` | Nom de la base |
| `QDRANT_HOST` | Non | `localhost` | Host Qdrant |
| `QDRANT_PORT` | Non | `6333` | Port Qdrant |
| `QDRANT_COLLECTION_NAME` | Non | `gmao_chunks` | Nom de la collection |
| `EMBEDDING_SMALL_MODEL_NAME` | Non | `intfloat/multilingual-e5-small` | Modèle embeddings |
| `OPENAI_API_KEY` | Oui | — | Clé API OpenAI |
| `LLM_MODEL_NAME` | Non | `gpt-4o-mini` | Modèle OpenAI |
| `GEMINI_MODEL_NAME` | Non | `gemini-2.5-flash` | Modèle Gemini |
| `GOOGLE_API_KEY` | Non | — | Clé API Google |
| `RAG_API_KEY` | Non | *(aucun)* | Token auth API |

---

## Schéma MySQL

```
document                chunk_rag
├── id_document (PK)    ├── id_chunk (PK)
├── titre               ├── contenu
├── nom_fichier         ├── ordre_chunk
├── type_fichier        ├── nombre_tokens
├── statut_indexation   ├── type_source (Document/Panne)
└── id_equipement       └── statut_embedding
        │                        │
        └──── document_chunk ─────┘
              (id_document, id_chunk)

panne                   panne_chunk
├── id_panne (PK)       ├── id_chunk (FK)
├── titre               └── id_panne (FK)
├── description
├── gravite
└── id_equipement
```

---

## Architecture du code

Chaque couche suit le patron `Base Strategy / Registry / Orchestrator` :

```
app/
├── <couche>/
│   ├── base.py            # ABC (interface abstraite)
│   ├── strategies/        # Implémentations concrètes
│   ├── registry.py        # Registre (factories)
│   └── orchestrator.py    # Orchestrateur (façade)
├── models/                # Dataclasses du domaine
├── exceptions/            # Hiérarchie GMAOError
├── api/                   # FastAPI (endpoints, auth, schemas)
└── main.py                # Point d'entrée uvicorn
```

---

## Pièges connus

1. **Trailing slash obligatoire** sur `/documents/` — sinon redirect 307
2. **`chunk_rag` n'a pas** de colonnes `id_document`/`id_panne` — l'association se fait via `document_chunk`/`panne_chunk`
3. **Crédits OpenAI épuisés** — le endpoint `/search` retourne 200 avec `llm_error` non-null (dégradation gracieuse)
4. **`.env` ne doit pas être commité** — contient des clés API et mots de passe
5. **L'ingestion crée automatiquement** le document MySQL — pas besoin de le créer séparément

---

## Documentation détaillée

| Fichier | Contenu |
|---------|---------|
| `docs/API.md` | Référence complète de l'API REST (12 endpoints) |
| `docs/RETRIEVAL.md` | Couche de recherche vectorielle |
| `docs/RERANKER.md` | Couche de re-classement |
| `docs/LLM.md` | Couche de génération |
| `docs/EMBEDDING.md` | Couche d'embeddings |
| `docs/PARSER.md` | Couche d'extraction de texte |
| `docs/CHUNKER.md` | Couche de découpage |
| `docs/DATA_SOURCES.md` | Couche de chargement |
| `docs/STORAGE.md` | Couche de persistance |
| `docs/EXCEPTIONS.md` | Hiérarchie des exceptions |

---

## Licence

Projet privé — GMAO-RAG © 2026

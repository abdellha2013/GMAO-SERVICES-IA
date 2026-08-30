# GMAO-RAG — Documentation Complète des Endpoints

> **Base URL** : `http://127.0.0.1:8000`
> **Version** : v1 (préfixe `/api/v1`)
> **Format** : JSON (`application/json`) — upload via `multipart/form-data`
> **Authentification** : Bearer `Authorization: Bearer <RAG_API_KEY>` — requise sur tous les endpoints **sauf** `/api/v1/health`
> **Rôle** : assistant **RAG maintenance** (retrieval vectoriel Qdrant + reranking cross-encoder + génération LLM Gemini/OpenAI), ingestion de documents (fichiers, MySQL), gestion des documents indexés.

---

## Table des matières

1. [GET /api/v1/health — Santé du service](#1-get-apiv1health--santé-du-service)
2. [POST /api/v1/rag/retrieve — Retrieval seul](#2-post-apiv1ragretrieve--retrieval-seul)
3. [POST /api/v1/rag/rerank — Reranking seul](#3-post-apiv1ragrerank--reranking-seul)
4. [POST /api/v1/rag/search — Pipeline complet](#4-post-apiv1ragsearch--pipeline-complet)
5. [POST /api/v1/ingest/file — Upload fichier](#5-post-apiv1ingestfile--upload-fichier)
6. [POST /api/v1/ingest/database — Ingestion MySQL](#6-post-apiv1ingestdatabase--ingestion-mysql)
7. [POST /api/v1/ingest/files — Batch ingestion](#7-post-apiv1ingestfiles--batch-ingestion)
8. [GET /api/v1/documents/ — Liste des documents](#8-get-apiv1documents--liste-des-documents)
9. [GET /api/v1/documents/{id} — Détail document](#9-get-apiv1documentsid--détail-document)
10. [DELETE /api/v1/documents/{id} — Supprimer document](#10-delete-apiv1documentsid--supprimer-document)
11. [GET /api/v1/strategies — Stratégies disponibles](#11-get-apiv1strategies--stratégies-disponibles)
12. [GET /api/v1/stats — Statistiques](#12-get-apiv1stats--statistiques)
13. [Exemples d'intégration Laravel](#13-exemples-dintégration-laravel)
14. [Codes d'erreur](#14-codes-derreur)
15. [Configuration (.env)](#15-configuration-env)

---

## 1. GET /api/v1/health — Santé du service

Vérifie la connectivité à **Qdrant** et **MySQL** et indique l'état du
**warmup** des modèles ML (modèles préchargés en mémoire). **Aucune auth requise.**

### Requête

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### Réponse `200 OK`

```json
{
  "status": "healthy",
  "qdrant": "ok",
  "mysql": "ok",
  "version": "0.1.0",
  "models": {
    "retrieval": "ready",
    "reranker": "ready",
    "llm": "ready",
    "embedding": "ready"
  },
  "warmup_ms": {
    "retrieval": 8420.4,
    "reranker": 6103.7,
    "llm": 301.2,
    "embedding": 8341.1
  }
}
```

| Champ | Type | Description |
|---|---|---|
| `status` | string | `"healthy"` (Qdrant + MySQL OK), `"degraded"` (un seul backend OK), `"unhealthy"` (aucun) |
| `qdrant` | string | `"ok"` ou message d'erreur |
| `mysql` | string | `"ok"` ou message d'erreur |
| `version` | string | Version du code |
| `models` | dict | État du warmup par couche : `"ready"`, `"disabled"` (`RAG_WARMUP_MODELS=0`), `"skipped"`, `"error: <msg>"` |
| `warmup_ms` | dict | Durée de préchargement par couche (ms, au démarrage) |

### Utilisation Laravel

```php
$response = Http::get('http://127.0.0.1:8000/api/v1/health');

if ($response->json('status') !== 'healthy') {
    Log::warning('Qdrant ou MySQL indisponible pour le service RAG');
}
```

---

## 2. POST /api/v1/rag/retrieve — Retrieval seul

Recherche des chunks pertinents dans Qdrant, **sans reranking ni génération LLM**.

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "vibration pompe centrifuge", "top_k": 5}'
```

### Corps de la requête

| Champ | Type | Obligatoire | Contrainte | Description |
|---|---|---|---|---|
| `query` | string | Oui | `min_length=1` | Requête utilisateur (texte libre) |
| `filters` | object | Non | — | Filtres optionnels (voir `FilterParams` ci-dessous) |
| `top_k` | int | Non | `ge=1, le=50` | Nombre de résultats (défaut: 5) |

**`filters` (logique AND entre champs)** :

| Champ | Type | Description |
|---|---|---|
| `id_document` | int \| null | Filtrer les chunks d'un document |
| `id_panne` | int \| null | Filtrer les chunks d'une panne |
| `id_equipement` | int \| null | Filtrer les chunks d'un équipement |
| `source_type` | string \| null | Type de source (`"document"`, `"panne"`) |
| `min_score` | float \| null | Score minimum de pertinence |

### Réponse `200 OK`

```json
{
  "query": "vibration pompe centrifuge",
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

### Erreurs

| Code | Cause |
|---|---|
| `400` | Query vide, `top_k` invalide |
| `401` | Token invalide |
| `422` | Body manquant ou champ obligatoire absent |
| `503` | Qdrant inaccessible (`RETRIEVAL_CONNECTION_ERROR`) |

---

## 3. POST /api/v1/rag/rerank — Reranking seul

Re-classe les chunks via un **Cross-Encoder**. Les candidats doivent être
fournis dans le body (champ `results` d'une réponse de `/retrieve`).

### Requête

```bash
# 1) Récupérer des chunks
CHUNKS=$(curl -s http://127.0.0.1:8000/api/v1/rag/retrieve \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "vibration pompe centrifuge", "top_k": 5}')

# 2) Le endpoint attend la liste des candidats (champ "results" uniquement)
CANDIDATES=$(echo "$CHUNKS" | jq -c '.results')

# 3) Reranker
curl -s http://127.0.0.1:8000/api/v1/rag/rerank \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"vibration pompe centrifuge\", \"candidates\": $CANDIDATES, \"top_k\": 3}"
```

### Corps de la requête

| Champ | Type | Obligatoire | Contrainte | Description |
|---|---|---|---|---|
| `query` | string | Oui | `min_length=1` | Requête originale |
| `candidates` | list | Oui | `min_length=1` | Liste de chunks (issus de `/retrieve`) |
| `top_k` | int | Non | `ge=1, le=50` | Nombre de résultats après reranking |

### Réponse `200 OK`

```json
{
  "query": "vibration pompe centrifuge",
  "results": [
    {
      "chunk_id": "112",
      "content": "Vibration anormale sur pompe centrifuge...",
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

### Erreurs

| Code | Cause |
|---|---|
| `400` | Query vide, candidats vides |
| `401` | Token invalide |
| `422` | Champs requis manquants dans les candidats |

---

## 4. POST /api/v1/rag/search — Pipeline complet

Pipeline **retrieve → rerank → generate**. C'est l'endpoint principal
pour une requête RAG complète.

### Requête

```bash
# Pipeline complet (retrieve + rerank + LLM)
curl -s http://127.0.0.1:8000/api/v1/rag/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quelles sont les causes frequentes de panne sur les pompes ?",
    "top_k": 5,
    "rerank": true,
    "generate": true
  }'

# Sans LLM (rapide, aucun crédit OpenAI/Gemini consommé)
curl -s http://127.0.0.1:8000/api/v1/rag/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "vibration moteur", "rerank": false, "generate": false}'
```

### Corps de la requête

| Champ | Type | Obligatoire | Contrainte | Description |
|---|---|---|---|---|
| `query` | string | Oui | `min_length=1` | Requête utilisateur |
| `filters` | object | Non | — | Filtres optionnels (voir section 2) |
| `top_k` | int | Non | `ge=1, le=50` | Nombre de résultats (défaut: 5) |
| `rerank` | bool | Non | — | Activer le reranking (défaut: `true`) |
| `generate` | bool | Non | — | Activer la génération LLM (défaut: `true`) |
| `llm_strategy` | string | Non | — | Stratégie LLM (ex: `"gemini"`, `"openai"`) |

### Configurations possibles

| `rerank` | `generate` | Comportement |
|---|---|---|
| `true` | `true` | Pipeline complet : retrieve → rerank → LLM |
| `false` | `true` | Rapide : retrieve → LLM (sans reranking) |
| `true` | `false` | Reranking seul : retrieve → rerank, pas de réponse textuelle |
| `false` | `false` | Retrieval seul : chunks bruts sans reranking ni LLM |

### Réponse `200 OK`

```json
{
  "answer": "Les vibrations sur les pompes centrifuges sont souvent causees par...",
  "query": "vibration pompe centrifuge",
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
      "content": "Vibration anormale sur pompe centrifuge...",
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

> Quand `generate=false` ou `rerank=false`, les champs correspondants sont
> vides : `answer=""`, `citations=[]`, `reranker_strategy="none"`.

### Erreurs

| Code | Cause |
|---|---|
| `400` | Query vide |
| `401` | Token invalide |
| `422` | Body manquant |
| `429` | Crédits OpenAI/Gemini épuisés (`LLM_RATE_LIMIT_ERROR`) |
| `500` | Erreur LLM interne |
| `502` | LLM injoignable (`LLM_CONNECTION_ERROR`) |
| `503` | Qdrant inaccessible |

---

## 5. POST /api/v1/ingest/file — Upload fichier

Upload d'un fichier via `multipart/form-data`, traité par le pipeline
complet : **load → parse → chunk → embed → stocker** (MySQL + Qdrant).

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/ingest/file \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -F "file=@manuel_pompe.txt" \
  -F "titre=Manuel pompe PC-12" \
  -F "source_type=TXT" \
  -F "version=2.1" \
  -F "description=Manuel de maintenance de la pompe centrifuge PC-12." \
  -F "id_equipement=42" \
  -F "chunk_size=3000" \
  -F "chunk_overlap=0"
```

### Champs du formulaire (`multipart/form-data`)

| Champ | Type | Requis | Défaut | Description |
|---|---|---|---|---|
| `file` | file | Oui | — | Fichier à ingérer (PDF, DOCX, TXT, HTML, CSV, JSON, XLSX, MD) |
| `titre` | string | Non | nom du fichier sans extension | Colonne `documents.titre` (max 255) |
| `source_type` | string | Non | détecté via l'extension | Colonne `documents.type_fichier`, ex. `"PDF"`, `"TXT"` |
| `version` | string | Non | `"1.0"` | Colonne `documents.version` (max 255) |
| `description` | string | Non | `null` | Colonne `documents.description` |
| `id_equipement` | int | Non | `null` | Colonne `documents.id_equipement` (FK, `>0`) |
| `chunk_size` | int | Non | `3000` (CSV/JSON/XLSX), `500` sinon | Taille max des chunks (100-5000) |
| `chunk_overlap` | int | Non | `0` (CSV/JSON/XLSX), `50` sinon | Chevauchement entre chunks (0-500) |

> **Performances** : sur une machine sans GPU, un grand tableau (XLSX/CSV de
> milliers de lignes) génère beaucoup de chunks — l'embedding CPU devient le
> goulot. Le default `chunk_size=3000` pour les formats structurés réduit
> fortement le nombre de chunks (ex. 2202 → 274 sur un fichier de 3072 lignes).
> Un `id_equipement` inconnu renvoie une erreur claire
> `[DATABASE_FOREIGN_KEY] ... n'existe pas` (levée avant l'ingestion).

### Réponse `200 OK`

```json
{
  "status": "ok",
  "results": [
    {
      "status": "ok",
      "document_name": "manuel_pompe.txt",
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

### Erreurs

| Code | Cause |
|---|---|
| `401` | Token invalide |
| `422` | Fichier manquant, `id_equipement` invalide, `chunk_size` hors bornes |
| `500` | Erreur pipeline (format non supporté, etc.) |

---

## 6. POST /api/v1/ingest/database — Ingestion MySQL

Ingestion depuis une **table MySQL** ou une **requête SQL custom**. Le
document n'est jamais lié à un équipement unique : `documents.id_equipement`
reste `NULL` (le champ `id_equipement` n'est pas accepté ici).

### Requête

```bash
# Depuis une table
curl -s http://127.0.0.1:8000/api/v1/ingest/database \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "127.0.0.1",
    "database": "gmao",
    "user": "root",
    "password": "",
    "table": "pannes"
  }'

# Avec requête SQL custom (remplace "table")
curl -s http://127.0.0.1:8000/api/v1/ingest/database \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "127.0.0.1",
    "database": "gmao",
    "user": "root",
    "password": "",
    "table": "pannes",
    "query": "SELECT * FROM pannes LIMIT 10"
  }'
```

### Corps de la requête (JSON)

| Champ | Type | Obligatoire | Contrainte | Description |
|---|---|---|---|---|
| `driver` | string | Non | — | Pilote (défaut: `"mysql"`) |
| `host` | string | Oui | `min_length=1` | Host MySQL |
| `port` | int | Non | `gt=0` | Port (défaut: 3306) |
| `database` | string | Oui | `min_length=1` | Nom de la base |
| `user` | string | Oui | `min_length=1` | Utilisateur |
| `password` | string | Oui | — | Mot de passe |
| `table` | string | Oui | `min_length=1` | Table source |
| `query` | string | Non | — | SQL custom (remplace `table` si fourni) |
| `titre` | string | Non | `database.table` | Colonne `documents.titre` (max 255) |
| `source_type` | string | Non | `null` | Colonne `documents.type_fichier` (ex. `"MYSQL"`) |
| `version` | string | Non | `"1.0"` | Colonne `documents.version` |
| `description` | string | Non | `null` | Colonne `documents.description` |
| `chunk_size` | int | Non | `500` (source non-structurée) | Taille max chunks (100-5000) |
| `chunk_overlap` | int | Non | `50` | Chevauchement (0-500) |

> **Re-ingestion (upsert)** : l'identité du document est `database.table`
> (stockée dans `documents.chemin_fichier`). Si un document avec cette
> identité existe déjà, il est **supprimé** (chunks MySQL + points Qdrant)
> avant la nouvelle ingestion et `documents.version` est **incrémenté**
> (`1.0` → `2.0`).

### Réponse `200 OK`

```json
{
  "status": "ok",
  "results": [
    {
      "status": "ok",
      "document_name": "gmao.pannes",
      "chunks_count": 34,
      "duration_ms": 8900.12,
      "error": null
    }
  ],
  "total_files": 1,
  "success_count": 1,
  "error_count": 0
}
```

---

## 7. POST /api/v1/ingest/files — Batch ingestion

Ingestion de plusieurs fichiers **déjà présents sur le serveur** (chemins
absolus). Chaque fichier est traité indépendamment — une erreur sur un
fichier n'empêche pas les autres.

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/ingest/files \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "paths": ["/var/data/doc1.txt", "/var/data/doc2.pdf"],
    "titre": "Rapport équipement",
    "id_equipement": 42
  }'
```

### Corps de la requête (JSON)

| Champ | Type | Obligatoire | Contrainte | Description |
|---|---|---|---|---|
| `paths` | list[string] | Oui | `min_length=1` | Chemins absolus des fichiers sur le serveur |
| `titre` | string | Non | nom du fichier | Colonne `documents.titre` (max 255) |
| `source_type` | string | Non | détecté via l'extension | Colonne `documents.type_fichier` |
| `version` | string | Non | `"1.0"` | Colonne `documents.version` |
| `description` | string | Non | `null` | Colonne `documents.description` |
| `id_equipement` | int | Non | `null` | ID équipement **partagé** par tous les fichiers |
| `chunk_size` | int | Non | `3000` (CSV/JSON/XLSX), `500` sinon | Taille max chunks |
| `chunk_overlap` | int | Non | `0` (CSV/JSON/XLSX), `50` sinon | Chevauchement |

### Réponse `200 OK`

```json
{
  "status": "partial",
  "results": [
    {
      "status": "ok",
      "document_name": "/var/data/doc1.txt",
      "chunks_count": 5,
      "duration_ms": 800.12,
      "error": null
    },
    {
      "status": "error",
      "document_name": "/var/data/doc2.pdf",
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

Valeurs possibles de `status` (racine) : `"ok"` (tous réussis), `"partial"`
(au moins un échec), `"error"` (aucun réussi).

---

## 8. GET /api/v1/documents/ — Liste des documents

Retourne tous les documents avec leur nombre de chunks. `indexed` est
**dérivé** de la présence des points dans Qdrant (`point.id == id_chunk`) —
aucune colonne `statut_indexation` en base.

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/documents/ \
  -H "Authorization: Bearer $RAG_API_KEY"
```

> **Trailing slash** : `/api/v1/documents` (sans `/`) renvoie un
> **307 Redirect** que curl ne suit pas par défaut — utiliser `-L` ou le `/` final.

### Réponse `200 OK`

```json
{
  "documents": [
    {
      "id": 1,
      "name": "sample-5pages.docx",
      "source_type": "DOCX",
      "id_equipement": 42,
      "chunks_count": 19,
      "indexed": false
    },
    {
      "id": 29,
      "name": "gmao.pannes",
      "source_type": "document",
      "id_equipement": null,
      "chunks_count": 34,
      "indexed": true
    }
  ],
  "total": 2
}
```

---

## 9. GET /api/v1/documents/{id} — Détail document

Retourne les métadonnées du document et **tous ses chunks** (contenu lu
directement dans `document_chunks`).

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/documents/1 \
  -H "Authorization: Bearer $RAG_API_KEY"
```

### Réponse `200 OK`

```json
{
  "document": {
    "id": 1,
    "name": "sample-5pages.docx",
    "source_type": "DOCX",
    "id_equipement": 42,
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
      "id_equipement": 42,
      "retrieval_strategy": ""
    }
  ]
}
```

### Erreurs

| Code | Cause |
|---|---|
| `404` | Document non trouvé |
| `422` | ID invalide (non entier) |

---

## 10. DELETE /api/v1/documents/{id} — Supprimer document

Supprime un document et **toutes ses données associées** : lignes
`document_chunks` (MySQL), points Qdrant correspondants et enregistrement
`documents`. Opération **irréversible**.

### Requête

```bash
curl -s -X DELETE http://127.0.0.1:8000/api/v1/documents/1 \
  -H "Authorization: Bearer $RAG_API_KEY"
```

### Réponse `200 OK`

```json
{
  "status": "ok",
  "deleted_chunks": 19
}
```

> Le même helper est utilisé en interne par `/ingest/database` pour la
> ré-ingestion (upsert) : l'ancien document est vidé avant la ré-insertion.

### Erreurs

| Code | Cause |
|---|---|
| `404` | Document non trouvé |

---

## 11. GET /api/v1/strategies — Stratégies disponibles

Retourne les noms des stratégies enregistrées dans chaque registre du pipeline.

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/strategies \
  -H "Authorization: Bearer $RAG_API_KEY"
```

### Réponse `200 OK`

```json
{
  "retrieval": ["qdrant", "hybrid"],
  "reranker": ["cross-encoder"],
  "llm": ["openai", "gemini"],
  "embedding": ["e5-small-v2"]
}
```

---

## 12. GET /api/v1/stats — Statistiques

Retourne les compteurs de la base MySQL et de Qdrant.

### Requête

```bash
curl -s http://127.0.0.1:8000/api/v1/stats \
  -H "Authorization: Bearer $RAG_API_KEY"
```

### Réponse `200 OK`

```json
{
  "documents_count": 1,
  "chunks_count": 52,
  "qdrant_points": 52
}
```

> `qdrant_points` est `null` si Qdrant est injoignable.

---

## 13. Exemples d'intégration Laravel

### Recherche RAG complète

```php
$response = Http::withToken(env('RAG_API_KEY'))
    ->timeout(60)   // la génération LLM peut prendre plusieurs secondes
    ->post('http://127.0.0.1:8000/api/v1/rag/search', [
        'query'    => 'Quelles sont les causes de vibration sur le compresseur ?',
        'top_k'    => 5,
        'rerank'   => true,
        'generate' => true,
    ]);

$body = $response->json();

if (isset($body['answer'])) {
    $reponse = $body['answer'];
    $sources = collect($body['citations'])->pluck('source_name');
    // afficher la réponse + ses sources
} else {
    Log::warning('RAG indisponible : '.($body['message'] ?? 'inconnu'));
}
```

### Ingestion d'un fichier depuis Laravel (multipart)

```php
$response = Http::withToken(env('RAG_API_KEY'))
    ->attach('file', file_get_contents($path), 'manuel_pompe.txt')
    ->post('http://127.0.0.1:8000/api/v1/ingest/file', [
        'titre'          => 'Manuel pompe PC-12',
        'source_type'    => 'TXT',
        'id_equipement'  => 2,
        'chunk_size'     => 3000,
        'chunk_overlap'  => 0,
    ]);

$body = $response->json();

if (($body['success_count'] ?? 0) === ($body['total_files'] ?? 0)) {
    $chunks = $body['results'][0]['chunks_count'] ?? 0; // chunks indexés
} else {
    Log::error('Ingestion RAG échouée : '.($body['results'][0]['error'] ?? 'inconnu'));
}
```

### Suppression d'un document (ex. équipement supprimé)

```php
$response = Http::withToken(env('RAG_API_KEY'))
    ->delete('http://127.0.0.1:8000/api/v1/documents/'.$documentId);

if ($response->json('status') === 'ok') {
    Log::info('Document RAG supprimé (chunks relâchés : '.$response->json('deleted_chunks').')');
}
```

---

## 14. Codes d'erreur

### Mapping erreur GMAO → HTTP

| Exception | HTTP | `error_code` |
|---|---|---|
| `EmptyQueryError` | 400 | `RETRIEVAL_EMPTY_QUERY` |
| `RetrievalValidationError` | 400 | `RETRIEVAL_*` |
| `RerankerValidationError` | 400 | `RERANKER_*` |
| `LLMValidationError` | 400 | `LLM_*` |
| `RetrievalConnectionError` | 503 | `RETRIEVAL_CONNECTION_ERROR` |
| `LLMRateLimitError` | 429 | `LLM_RATE_LIMIT_ERROR` |
| `LLMConnectionError` | 502 | `LLM_CONNECTION_ERROR` |
| `ForeignKeyError` | 409 | `DATABASE_FOREIGN_KEY` |
| Autre `GMAOError` | `exc.http_status` ou 500 | Variable |

### Format de réponse d'erreur

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

Les exceptions Python non anticipées renvoient :

```json
{
  "detail": "Internal server error"
}
```

> **Ingestion** : les erreurs pipelines (format non supporté, `id_equipement`
> inconnu, …) sont **capturées par les endpoints `/ingest/*`** et retournées
> dans `results[].error` avec `status="error"` (HTTP `200`) — pas levées en
> HTTP 4xx/5xx. Le message d'un équipement inconnu commence par
> `[DATABASE_FOREIGN_KEY]`.

> En-tête `X-Process-Time` : durée totale de la requête en secondes (middleware).

---

## 15. Configuration (.env)

| Variable | Requis | Défaut | Description |
|---|---|---|---|
| `RAG_API_KEY` | Non | *(aucun)* | Clé API pour l'auth Bearer. Non définie = **mode dev** (toute valeur acceptée) |
| `MYSQL_DSN` | Non | construit depuis `GMAO_DB_*` | DSN SQLAlchemy complet (ex. `mysql+pymysql://user:pass@host:3306/gmao`) |
| `GMAO_DB_HOST` | Non | `localhost` | Host MySQL |
| `GMAO_DB_PORT` | Non | `3306` | Port MySQL |
| `GMAO_DB_USER` | Non | `root` | Utilisateur MySQL |
| `GMAO_DB_PASSWORD` | Non | `""` | Mot de passe MySQL |
| `GMAO_DB_NAME` | Non | `gmao` | Nom de la base MySQL |
| `QDRANT_HOST` | Non | `localhost` | Host Qdrant |
| `QDRANT_PORT` | Non | `6333` | Port Qdrant |
| `QDRANT_COLLECTION_NAME` | Non | `gmao_chunks` | Nom de la collection Qdrant |
| `RAG_WARMUP_MODELS` | Non | `1` | Précharge les modèles ML au démarrage (`0` = chargement paresseux au 1er appel) |
| `GEMINI_API_KEY` | Selon LLM | *(aucun)* | Clé Google Gemini (stratégie `"gemini"`) |
| `OPENAI_API_KEY` | Selon LLM | *(aucun)* | Clé OpenAI (stratégie `"openai"`) |

### Démarrage local

```bash
cd /home/abdellah-daif/GMAO-RAG
PYTHONPATH=. uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

- Swagger interactif : `http://127.0.0.1:8000/docs`
- Health check (sans auth) : `http://127.0.0.1:8000/api/v1/health`
- Interface web de test : `http://127.0.0.1:8000/`
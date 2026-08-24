# GMAO-SERVICES-IA

Le repo présente les différents fonctionnalités à intégrer dans une application GMAO.

## Sous-projets

| Dossier | Rôle |
|---|---|
| [`GMAO-RAG/`](GMAO-RAG/) | Assistant RAG maintenance (FastAPI, Qdrant, LLM Gemini/OpenAI, interface web) |
| [`GMAO-ML/`](GMAO-ML/) | ML prédictif de panne machine (AI4I 2020, pipeline sklearn + API FastAPI) |
| [`GMAO-API/`](GMAO-API/) | Passerelle capteurs → modèle ML → demandes d'intervention Laravel (+ dashboard temps réel) |

## Démarrage rapide (workspace uv)

```bash
uv sync   # un seul .venv partagé par les trois services

# 1. Modèle ML (:8100)
uv run --env-file GMAO-ML/.env uvicorn gmao_ml.api.main:app --port 8100
# 2. Passerelle IA (:8200) — dashboard sur http://127.0.0.1:8200/
uv run --env-file GMAO-API/.env uvicorn gmao_api.api.main:app --port 8200
```

Chaque sous-projet possède son propre `README.md` avec le détail
(architecture, endpoints, tests, configuration `.env`).

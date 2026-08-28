# GMAO-SERVICES-IA

Le repo présente les différents fonctionnalités à intégrer dans une application GMAO.

## Sous-projets

| Dossier | Rôle |
|---|---|
| [`GMAO-RAG/`](GMAO-RAG/) | Assistant RAG maintenance (FastAPI, Qdrant, LLM Gemini/OpenAI, interface web) |
| [`GMAO-ML/`](GMAO-ML/) | ML prédictif de panne machine (AI4I 2020, pipeline sklearn + API FastAPI) |
| [`GMAO-API/`](GMAO-API/) | Passerelle capteurs → modèle ML → demandes d'intervention Laravel (+ dashboard temps réel) |
| [`GMAO-ANALYTICS/`](GMAO-ANALYTICS/) | Analytics maintenance : MTBF/MTTR/disponibilité + rapports (FastAPI, pandas, enrichi GMAO-ML) |
| [`GMAO-OCR/`](GMAO-OCR/) | Lecture de QR codes équipements par photo (vision OCR, OpenCV/pyzbar, validation anti-phishing) |

## Démarrage rapide (workspace uv)

```bash
uv sync   # un seul .venv partagé par les services

# 1. Modèle ML (:8100)
uv run --env-file GMAO-ML/.env uvicorn gmao_ml.api.main:app --port 8100
# 2. Passerelle IA (:8200) — dashboard sur http://127.0.0.1:8200/
uv run --env-file GMAO-API/.env uvicorn gmao_api.api.main:app --port 8200
# 3. Analytique maintenance (:8300) — dashboard sur http://127.0.0.1:8300/ (Swagger sur /docs)
uv run --env-file GMAO-ANALYTICS/.env uvicorn gmao_analytics.api.main:app --port 8300
# 4. Vision OCR équipements (:8400) — Swagger sur http://127.0.0.1:8400/docs
uv run --env-file GMAO-OCR/.env uvicorn gmao_ocr.api.main:app --port 8400
```

> **GMAO-ANALYTICS** : préalablement peupler les tables de maintenance MySQL
> (`pannes`, `ordre_travails`), par ex. :
> `uv run python GMAO-ANALYTICS/scripts/seed_maintenance.py --db "mysql+pymysql://root:PASS@127.0.0.1:3306/gmao_rag" --reset`

> **GMAO-OCR** : le décodage préfère `pyzbar` (nécessite la lib système `libzbar0`)
> et retombe sur OpenCV (`opencv-python`) si la lib n'est pas installable.

Chaque sous-projet possède son propre `README.md` avec le détail
(architecture, endpoints, tests, configuration `.env`). Le référentiel des
endpoints de chaque service est centralisé dans [`doc_api/`](doc_api/).

# GMAO-ML — ML prédictif de l'état des machines

Sous-projet du monorepo `Gmao-Services-IA`. Prédit l'état des équipements
GMAO à partir de données capteurs, via un pipeline d'entraînement
comparant plusieurs classifieurs et une **API REST de prédiction**
(FastAPI, style `GMAO-RAG`).

## Installation

Le sous-projet est intégré au workspace uv racine (un seul `.venv`
partagé pour tous les services — voir conventions du repo) :

```bash
uv sync   # depuis la racine du monorepo
cp GMAO-ML/.env.example GMAO-ML/.env   # puis ajuster ML_API_KEY
```

## Données d'entraînement

Deux sources possibles (CSV avec colonne cible) :

```bash
# 1) Dataset public AI4I 2020 (10 000 obs., capteurs + labels défaillance)
uv run python GMAO-ML/scripts/load_ai4i_dataset.py

# 2) Fallback synthétique (smoke test du pipeline)
uv run python GMAO-ML/scripts/generate_sample_csv.py
```

## Entraînement

```bash
uv run python GMAO-ML/scripts/train.py --data GMAO-ML/data/ai4i_2020.csv

# Variantes :
#   --target failure_type            # cible multi-classes
#   --strategies random_forest       # sous-ensemble de stratégies
#   --no-tracking                    # désactive MLflow
```

Le pipeline compare `logistic_regression`, `random_forest` et
`hist_gradient_boosting` (CV stratifiée 5-fold + holdout), journalise
chaque run dans **MLflow** (`mlruns/`, UI : `uv run mlflow ui --backend-store-uri file:GMAO-ML/mlruns`)
et publie le meilleur modèle dans `GMAO-ML/artifacts/<model_name>/`.

> **Flux de référence actuel** : le notebook
> `notebooks/02_training_evaluation_ai4i.ipynb`, qui optimise *conjointement*
> l'augmentation « jitter » des pannes, le seuil de décision et le coût métier
> (FN = 10 × FP), puis publie l'artefact final.

## Modèle publié (état actuel)

| | |
|---|---|
| Artefact courant | `artifacts/gmao_state_classifier/20260824_150222.joblib` |
| Stratégie | `hist_gradient_boosting` + augmentation `ai4i_rule_bootstrap` (σ = 20 % écart-type) |
| Seuil de décision | **0.75** — stocké dans les métadonnées (`decision_threshold`), appliqué automatiquement à l'inférence |
| Métriques test | f1_macro **0.9553** · AUC **0.9743** · accuracy 0.9945 |
| Panne (classe 1) | rappel **85.3 %** · précision **98.3 %** (FN = 10, FP = 1) |

## API de prédiction

```bash
uv run --env-file GMAO-ML/.env uvicorn gmao_ml.api.main:app --host 127.0.0.1 --port 8100
```

| Endpoint                  | Auth Bearer | Description                          |
|---------------------------|-------------|--------------------------------------|
| `GET  /api/v1/healthz`    | non         | État du service + modèle chargé      |
| `POST /api/v1/predict`    | oui         | Prédiction unitaire                  |
| `POST /api/v1/predict/batch` | oui      | Prédiction par lot (≤ 1000)          |
| `GET  /api/v1/model/info` | oui         | Métadonnées du modèle chargé         |

Exemple :

```bash
curl -X POST http://127.0.0.1:8100/api/v1/predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ML_API_KEY" \
   -d '{"features": {"Type": "M", "Air temperature [K]": 299.5,
        "Process temperature [K]": 309.1, "Rotational speed [rpm]": 1420,
        "Torque [Nm]": 52.3, "Tool wear [min]": 180}}'
```

La prédiction binaire est dérivée des probabilités via le seuil enregistré
dans les métadonnées (`decision_threshold`, défaut 0.5 si absent) — aucune
divergence entraînement/inférence possible. Référence complète des endpoints
et exemples de réponses : [`docs/endpoints.md`](docs/endpoints.md).

## Structure

```
gmao_ml/
├── config.py        # settings env (résolus relativement à GMAO-ML/)
├── exceptions/      # MLError + hiérarchies data/model/training/tracking
├── models/schemas.py# requêtes/réponses Pydantic
├── data/            # loader CSV validé + preprocessing sklearn sérialisé
├── training/        # registry + strategies + orchestrator (CV, MLflow)
├── inference/       # Predictor (artefact joblib auto-contenu)
├── tracking/        # wrapper MLflow léger (best effort)
└── api/             # FastAPI (auth Bearer, lifespan, /api/v1/*)
```

## Tests

```bash
uv run pytest GMAO-ML/tests/unit -q   # 52 tests
```

## Notes

- `data/` et `mlruns/` sont **gitignorés** ; en revanche `artifacts/` est
  volontairement **tracké** dans le repo (le modèle courant est versionné,
  ~300 Ko par réentraînement — penser à purger les anciennes versions).
- Le prétraitement est embarqué dans le pipeline sérialisé : aucune
  divergence train/inférence possible.
- Le tracking MLflow est *best effort* : si le backend est indisponible,
  l'entraînement continue sans suivi (warning).

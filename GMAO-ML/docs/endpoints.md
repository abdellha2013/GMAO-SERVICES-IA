# GMAO-ML — Référence des endpoints API

Tous les endpoints sont préfixés par **`/api/v1`**.
Documentation interactive (Swagger) : **`http://127.0.0.1:8100/docs`** · OpenAPI : `/openapi.json`.

## Authentification

| | |
|---|---|
| En-tête requis | `Authorization: Bearer <API_KEY>` |
| Clé configurée dans | `GMAO-ML/.env` → variable `ML_API_KEY` (défaut dev : `gmao-ml-dev-key`) |
| Endpoints protégés | `/predict`, `/predict/batch`, `/model/info` |
| Sans authentification | `/healthz` uniquement |

Clé invalide → `401 Unauthorized` · En-tête `Authorization` absent → `422`.

## Vue d'ensemble

| Méthode | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/healthz` | non | État du service + modèle chargé |
| POST | `/api/v1/predict` | oui | Prédiction unitaire |
| POST | `/api/v1/predict/batch` | oui | Prédiction par lot (1 à 1000 échantillons) |
| GET | `/api/v1/model/info` | oui | Métadonnées du modèle actif |

---

## 1. `GET /api/v1/healthz`

Sonde de disponibilité (utilisable pour Docker/K8s). Aucune authentification.

```bash
curl http://127.0.0.1:8100/api/v1/healthz
```

```json
{
  "status": "ok",
  "service": "gmao-ml",
  "model_loaded": true,
  "model_name": "gmao_state_classifier",
  "model_version": "20260824_150222"
}
```

---

## 2. `POST /api/v1/predict`

Prédit l'état d'**une machine** à partir de ses relevés capteurs.

**Corps** — `features` : dict des colonnes brutes attendues par le modèle
(colonnes manquantes imputées, colonnes superflues ignorées ; le feature engineering
`delta_temp`, `power_w`, `torque_x_wear` est recalculé côté serveur).

```bash
curl -X POST http://127.0.0.1:8100/api/v1/predict \
  -H "Authorization: Bearer gmao-ml-dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "features": {
      "Type": "L",
      "Air temperature [K]": 298.9,
      "Process temperature [K]": 309.1,
      "Rotational speed [rpm]": 2861,
      "Torque [Nm]": 4.6,
      "Tool wear [min]": 143
    }
  }'
```

```json
{
  "prediction": 1,
  "probabilities": { "0": 0.0005, "1": 0.9995 },
  "model_version": "20260824_150222"
}
```

> Classes : `0` = saine, `1` = panne. Le seuil de décision publié dans les
> métadonnées du modèle (`decision_threshold`) est appliqué automatiquement ;
> sinon le 0.5 par défaut s'applique.

---

## 3. `POST /api/v1/predict/batch`

Même logique que `/predict` pour **1 à 1000 machines** (`samples`).

```bash
curl -X POST http://127.0.0.1:8100/api/v1/predict/batch \
  -H "Authorization: Bearer gmao-ml-dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "samples": [
      { "Type": "M", "Air temperature [K]": 298.1, "Process temperature [K]": 308.6,
        "Rotational speed [rpm]": 1551, "Torque [Nm]": 42.8, "Tool wear [min]": 0 },
      { "Type": "L", "Air temperature [K]": 298.9, "Process temperature [K]": 309.1,
        "Rotational speed [rpm]": 2861, "Torque [Nm]": 4.6, "Tool wear [min]": 143 }
    ]
  }'
```

```json
{
  "predictions": [
    { "prediction": 0, "probabilities": { "0": 0.9996, "1": 0.0004 }, "model_version": "20260824_150222" },
    { "prediction": 1, "probabilities": { "0": 0.0005, "1": 0.9995 }, "model_version": "20260824_150222" }
  ],
  "count": 2,
  "model_version": "20260824_150222"
}
```

Erreurs spécifiques : liste vide ou > 1000 éléments → `422 Unprocessable Entity`.

---

## 4. `GET /api/v1/model/info`

Informations sur le modèle actuellement chargé (version pointée par `latest.json`).

```bash
curl http://127.0.0.1:8100/api/v1/model/info \
  -H "Authorization: Bearer gmao-ml-dev-key"
```

```json
{
  "name": "gmao_state_classifier",
  "version": "20260824_150222",
  "strategy": "hist_gradient_boosting",
  "target_column": "machine_failure",
  "classes": ["0", "1"],
  "features": {
    "numeric": ["Type", "Air temperature [K]", "Process temperature [K]",
                 "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"],
    "categorical": []
  },
  "metrics": { "accuracy": 0.9945, "f1_macro": 0.9553, "roc_auc": 0.9743 },
  "trained_at": "2026-08-24T15:02:22",
  "n_training_samples": 10305,
  "sklearn_version": "1.9.0"
}
```

---

## Codes d'erreur communs

| Statut | Cause |
|---|---|
| `401` | Clé API invalide (`Authorization: Bearer …` présent mais erroné) |
| `422` | Corps JSON invalide **ou en-tête `Authorization` absent** (validation Pydantic : champ manquant, batch vide ou trop grand…) |
| `503` | Aucun modèle disponible (`NO_MODEL_AVAILABLE` : artefact/`latest.json` introuvable) |
| `500` | Erreur d'inférence (`INFERENCE_FAILED`) ou erreur serveur |

Le corps d'erreur suit le format : `{ "message", "error_code", "details" }`.

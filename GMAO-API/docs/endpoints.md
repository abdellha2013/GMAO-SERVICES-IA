# GMAO-API — Référence des endpoints API

Tous les endpoints sont préfixés par **`/api/v1`** (port par défaut **8200**).
Documentation interactive : `http://127.0.0.1:8200/docs`.
**Dashboard de test** (page web tout-en-un) : `http://127.0.0.1:8200/`.

## Dashboard

`GET /` sert une page unique (sans build, HTML/CSS/JS vanilla). **Un clic sur
« ▶ Démarrer la surveillance »** lance le flux temps réel : **une machine
tirée au hasard toutes les ~10 s (intervalle aléatoire 6–14 s)**, relevé
soumis au modèle ML et affiché **un par un** dans le tableau. Comportement
réaliste : **panne rare (≈ 5 % des relevés)** ; alerte Laravel + notification
uniquement quand une panne est prédite. Second clic = pause. La clé API se
saisit dans l'en-tête de la page (mémorisée en `localStorage`).

## Authentification

| | |
|---|---|
| En-tête requis | `Authorization: Bearer <GMAO_API_KEY>` |
| Clé configurée dans | `GMAO-API/.env` → variable `GMAO_API_KEY` |
| Sans authentification | `/healthz` uniquement |

Clé invalide → `401` · en-tête absent → `422`.

## Vue d'ensemble

| Méthode | Route | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/healthz` | non | état du service + joignabilité GMAO-ML + mode Laravel |
| POST | `/api/v1/predictions` | oui | relevés capteurs réels → ML → alertes si panne |
| POST | `/api/v1/simulate` | oui | relevés artificiels → même chaîne (IDs depuis MySQL si configuré) |
| GET | `/api/v1/alerts` | oui | journal des demandes d'intervention émises |
| GET | `/api/v1/laravel/interventions` | oui | proxy lecture : demandes présentes côté Laravel/mock |
| GET | `/` | non | dashboard web de test (page HTML) |

---

## 1. `GET /api/v1/healthz`

```json
{
  "status": "ok",
  "service": "gmao-api",
  "version": "0.1.0",
  "ml_api_reachable": true,
  "laravel_mode": "simulated"
}
```

`status` = `ok` si GMAO-ML répond et a un modèle chargé, sinon `degraded`.

---

## 2. `POST /api/v1/predictions`

Reçoit de 1 à 100 relevés. Chaque relevé porte un `equipement_id`
**existant dans la table `equipements`** côté Laravel (IDs de test : 1–12).
Les clés capteurs acceptent le nom exact AI4I ou le nom pythonique.

```bash
curl -X POST http://127.0.0.1:8200/api/v1/predictions \
  -H "Authorization: Bearer gmao-api-dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [
      {
        "equipement_id": 5,
        "Type": "L",
        "Air temperature [K]": 298.9,
        "Process temperature [K]": 308.4,
        "Rotational speed [rpm]": 1450,
        "Torque [Nm]": 97.0,
        "Tool wear [min]": 120
      }
    ]
  }'
```

```json
{
  "results": [
    {
      "equipement_id": 5,
      "equipement_nom": "Tour CNC (#5)",
      "prediction": 1,
      "probability_failure": 0.9993,
      "alert_sent": true,
      "alert_delivery": "simulated",
      "demande_intervention": {
        "titre": "[IA] Risque de panne détecté — Tour CNC (#5)",
        "description": "Demande générée automatiquement par GMAO-API : …",
        "priorite": "critique",
        "statut": "en_attente",
        "id_equipement": 5,
        "id_utilisateur": 1
      },
      "laravel_response": { "created": true, "data": { "…": "…" } }
    }
  ],
  "alerts_count": 1,
  "model_version": "20260824_150222"
}
```

> Le payload envoyé à Laravel (`demande_intervention`, hors `_meta`) respecte
> exactement la table `demande_interventions` : `priorite` = `critique` si
> `P(panne) ≥ CRITICAL_PROBABILITY` (défaut 0.90), sinon `elevee` ;
> `statut` toujours `en_attente` ; `id_utilisateur` = utilisateur IA (= 1).

---

## 3. `POST /api/v1/simulate`

Génère des relevés artificiels puis exécute la même chaîne.
L'`equipement_id` de chaque relevé est tiré dans la **table `equipements`**
si `EQUIPEMENTS_DB_URL` est configuré, sinon dans le catalogue Python de dev.

```bash
curl -X POST http://127.0.0.1:8200/api/v1/simulate \
  -H "Authorization: Bearer gmao-api-dev-key" \
  -H "Content-Type: application/json" \
  -d '{ "count": 20, "failure_rate": 0.3, "random_state": 42 }'
```

Réponse : identique à `/predictions`. Modes de panne injectés (règles AI4I) :
`pwf` (puissance hors [3500, 9000] W), `hdf` (ΔT < 8.6 K & RPM < 1380),
`osf` (couple × usure > seuil selon type).

---

## 4. `GET /api/v1/alerts`

```json
{
  "count": 2,
  "alerts": [
    {
      "timestamp": "2026-08-24T17:30:00",
      "equipement_id": 5,
      "equipement_nom": "Tour CNC (#5)",
      "probability_failure": 0.9993,
      "delivery": "simulated",
      "demande_intervention": { "…": "…" },
      "laravel_response": null,
      "model_version": "20260824_150222"
    }
  ]
}
```

Journal volatile (mémoire) — remis à zéro au redémarrage du service.

---

## 5. `GET /api/v1/laravel/interventions`

Proxy de lecture vers le backend (utile au dashboard). Interroge
`LARAVEL_API_URL + LARAVEL_ALERTS_PATH` en GET (avec le token si configuré)
et ne lève jamais.

```json
{ "mode": "real", "reachable": true, "status": 200,
  "body": { "data": [ { "id_demande": 7, "priorite": "critique", "…": "…" } ] } }
```

Backend injoignable → `{ "mode": "simulated", "reachable": false, "error": "…" }`.

---

## Codes d'erreur

| Statut | Cause |
|---|---|
| `401` | Clé invalide (`Bearer` erroné) |
| `422` | Corps invalide ou en-tête `Authorization` absent (validation) |
| `502` | `LARAVEL_DELIVERY_FAILED` (non bloquant : résultat tracé en `failed`) |
| `503` | `ML_UNREACHABLE` — GMAO-ML injoignable après retries |

Format : `{ "message", "error_code", "details" }`.

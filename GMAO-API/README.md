# GMAO-API — passerelle IA ↔ Laravel

API externe du workspace `Gmao-Services-IA` : elle reçoit des **relevés capteurs**
(réels ou artificiels), les transmet au **modèle prédictif GMAO-ML**, puis
**pousse une demande d'intervention vers le backend Laravel** lorsque la panne
est prédite (`prediction == 1`).

```
[capteurs / simulateur]
        │  POST /api/v1/predictions | /api/v1/simulate   (Bearer GMAO_API_KEY)
        ▼
GMAO-API (:8200, FastAPI)
        │  POST {ML_API_URL}/api/v1/predict              (Bearer ML_API_KEY)
        ▼
GMAO-ML (:8100) ── prediction + probabilités
        │  si prediction == 1
        ▼
POST {LARAVEL_API_URL}/api/intervention-requests       ← payload = table demande_interventions
    (mode simulé : scripts/mock_laravel.py sur :9000)
```

## Démarrage

```bash
# 1. GMAO-ML (modèle)          — terminal 1
uv run --env-file GMAO-ML/.env uvicorn gmao_ml.api.main:app --port 8100

# 2. Mock Laravel (simulation) — terminal 2
uv run uvicorn scripts.mock_laravel:app --app-dir GMAO-API --port 9000

# 3. GMAO-API                  — terminal 3
uv run --env-file GMAO-API/.env uvicorn gmao_api.api.main:app --port 8200
```

Configuration via `GMAO-API/.env` (voir `.env.example`) :
`SIMULATE_LARAVEL=true` active le mode simulation (aucun appel HTTP, alertes loggées).

## Endpoints

Voir [`docs/endpoints.md`](docs/endpoints.md). Résumé :

| Méthode | Route | Auth | Rôle |
|---|---|---|---|
| GET | `/` | non | **dashboard web de test** (santé, simulation, relevés, alertes) |
| GET | `/api/v1/healthz` | non | état + joignabilité GMAO-ML |
| POST | `/api/v1/predictions` | oui | relevés réels → ML → alertes |
| POST | `/api/v1/simulate` | oui | relevés artificiels → même chaîne |
| GET | `/api/v1/alerts` | oui | journal des demandes émises |
| GET | `/api/v1/laravel/interventions` | oui | proxy lecture des demandes côté backend |

Ouvrir `http://127.0.0.1:8200/` une fois le service lancé : **« ▶ Démarrer »**
lance la surveillance temps réel — **une machine aléatoire relevée toutes les
~10 s** (intervalle aléatoire), affichée un par un, panne rare (≈ 5 %).
Second clic = pause. Aucune saisie requise (clé API dans l'en-tête).

## Contraintes métier

* chaque relevé porte un `equipement_id` existant dans la table `equipements`
  (catalogue local des 12 équipements de test copié depuis le SQL de référence) ;
* les alertes respectent la structure de la table `demande_interventions`
  (`titre`, `description`, `priorite`, `statut=en_attente`, `id_equipement`,
  `id_utilisateur=1` — utilisateur **IA**) ;
* priorité selon la probabilité : `P(panne) ≥ CRITICAL_PROBABILITY (0.90)` →
  `critique`, sinon `elevee`.

## Structure & tests

```
GMAO-API/
├── gmao_api/
│   ├── api/            # main.py (factory, dashboard, erreurs), auth Bearer, v1/routes.py
│   ├── models/         # schémas Pydantic (relevés AI4I, résultats, alertes)
│   └── services/       # ml_client · laravel_client · orchestrator ·
│                       # simulator (règles PWF/HDF/OSF) · equipment_catalog · journal
├── static/index.html   # dashboard temps réel (1 relevé/cycle, panne rare ≈ 5 %)
├── scripts/mock_laravel.py   # faux backend Laravel sur :9000 (validation ENUM)
├── docs/endpoints.md   # référence détaillée des endpoints
└── tests/unit/         # 25 tests pytest
```

```bash
uv run pytest GMAO-API/tests -q   # 25 tests
```

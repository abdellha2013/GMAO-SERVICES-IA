# GMAO-ANALYTICS — Référence des endpoints API

Tous les endpoints sont préfixés par **`/api/v1`** (port par défaut **8300**).
Documentation interactive (Swagger/OpenAPI) : `http://127.0.0.1:8300/docs`.

Service d'**analytique de maintenance** : calcule les indicateurs **MTBF /
MTTR / disponibilité** à partir des données MySQL (tables `pannes`,
`ordre_travails`, `equipements`) et produit des **rapports** enrichis des
sorties du modèle prédictif **GMAO-ML** (enrichissement **tolérant** : si
GMAO-ML est indisponible, le rapport reste complet, `risk` est simplement
vide).

## Sources de données

| Donnée | Table MySQL | Utilisation |
|---|---|---|
| Pannes | `pannes.date_detection` (+ `id_equipement`) | MTBF |
| Ordonnances de travail | `ordre_travails` (`temps_reel`, `date_debut`, `date_fin`, `statut='termine'`) | MTTR |
| Parc | `equipements` | ventilation + identité |

Si `MAINTENANCE_DB_URL` n'est pas configuré, le service bascule sur un
référentiel de repli (catalogue Python, sans données de maintenance →
indicateurs `null`). Voir `scripts/seed_maintenance.py` pour peupler les
tables de maintenance de test.

## Vue d'ensemble

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | **Dashboard de visualisation** (HTML/CSS/JS statique, hors OpenAPI) |
| GET | `/api/v1/healthz` | état du service + joignabilité GMAO-ML + taille du parc |
| GET | `/api/v1/metrics` | indicateurs globaux + ventilation par équipement |
| GET | `/api/v1/metrics/equipements` | alias lisible de `/metrics` |
| GET | `/api/v1/metrics/equipement/{id}` | indicateurs filtrés sur un équipement (404 si inconnu) |
| GET | `/api/v1/report` | rapport complet (JSON) |
| GET | `/api/v1/report?format=markdown` | export Markdown lisible |
| GET | `/api/v1/report?format=csv` | export CSV (table plate par équipement) |

## Formules

| Indicateur | Calcul | Unité |
|---|---|---|
| **MTBF** | moyenne des écarts entre `date_detection` de pannes consécutives (uptime courant inclus) | h |
| **MTTR** | moyenne de `temps_reel` (min → h), sinon `date_fin − date_debut`, pour les OT `termine` | h |
| **Disponibilité** | `MTBF / (MTBF + MTTR)` | % |

Calculés par équipement (NumPy/Pandas), puis agrégés au niveau du parc.

---

## 1. `GET /api/v1/healthz`

```json
{
  "status": "ok",
  "service": "gmao-analytics",
  "version": "0.1.0",
  "ml_api_reachable": false,
  "equipements_count": 12
}
```

## 2. `GET /api/v1/metrics`

```json
{
  "global": {
    "mtbf_hours": 1862.67,
    "mttr_hours": 23.13,
    "availability_pct": 98.77,
    "nb_pannes": 52,
    "nb_interventions": 52
  },
  "per_equipement": [
    {
      "mtbf_hours": 2004.41,
      "mttr_hours": 18.27,
      "availability_pct": 99.1,
      "nb_pannes": 4,
      "nb_interventions": 4,
      "id_equipement": 1,
      "nom_equipement": "Compresseur industriel",
      "localisation": "Atelier A - Zone 1",
      "criticite": "elevee",
      "marque": "Atlas Copco",
      "modele": "GA 75"
    }
  ],
  "generated_at": "2026-08-28T12:31:08"
}
```

> NB : le JSON expose `global` (le champ Python interne est `global_`).
> Indicateurs absents → `null` (données insuffisantes).

## 3. `GET /api/v1/metrics/equipement/{id}`

Même structure que `/metrics` mais `per_equipement` ne contient que
l'équipement demandé. `404` si l'ID est introuvable dans le parc.

## 4. `GET /api/v1/report` (JSON)

Structure complète :

```json
{
  "generated_at": "2026-08-28T12:31:33",
  "global_metrics": { "mtbf_hours": 1862.68, "...": "..." },
  "per_equipement": [ "..." ],
  "risk": [
    {
      "equipement_id": 1,
      "equipement_nom": "Compresseur industriel",
      "predicted_risk": "moyen",
      "probability_failure": 0.42,
      "mtbf_hours": 2004.41,
      "nb_pannes": 4,
      "comment": "Fiabilité moyenne : surveillance préventive conseillée."
    }
  ],
  "text": "# Rapport de maintenance (GMAO Analytics)\\n... (markdown)",
  "content_type": "json"
}
```

`risk` est peuplé si GMAO-ML est joignable ; sinon `[]` (enrichissement
dégradé, rapport intact). Les niveaux : `faible | moyen | eleve | critique | inconnu`.

## 5. `GET /api/v1/report?format=markdown`

Réponse `text/markdown` avec `Content-Disposition: attachment`.

## 6. `GET /api/v1/report?format=csv`

Réponse `text/csv` (table plate par équipement, en-têtes pandas).

---

## Démarrage

```bash
# (option) peupler les tables de maintenance
uv run python GMAO-ANALYTICS/scripts/seed_maintenance.py \
    --db "mysql+pymysql://root:PASS@127.0.0.1:3306/gmao_rag" --months 12 --seed 7 --reset

# lancer le service
uv run --env-file GMAO-ANALYTICS/.env uvicorn gmao_analytics.api.main:app \
    --host 127.0.0.1 --port 8300
```

Configuration : `GMAO-ANALYTICS/.env` (voir `.env.example`) —
`MAINTENANCE_DB_URL`, `ML_API_URL`, `ML_TIMEOUT_S`, `ML_RETRIES`.

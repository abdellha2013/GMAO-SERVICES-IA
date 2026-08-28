# GMAO-ANALYTICS — Indicateurs de maintenance & rapports

Sous-projet du monorepo `Gmao-Services-IA`. Nouveau microservice FastAPI
(port `:8300`) qui calcule les **indicateurs de maintenance** à partir des
données MySQL (tables `pannes`, `ordre_travails`, `equipements`) et génère
des **rapports**, enrichis des sorties du modèle prédictif **GMAO-ML**.

## Indicateurs

| Indicateur | Définition | Unité |
|---|---|---|
| **MTBF** | Temps moyen entre deux pannes (moyenne des écarts entre pannes consécutives, uptime courant inclus) | heures |
| **MTTR** | Temps moyen de réparation (`temps_reel` en minutes, sinon `date_fin − date_debut`) des OT terminés | heures |
| **Disponibilité** | `MTBF / (MTBF + MTTR)` | % |

Calculés par équipement via `NumPy`/`Pandas`, puis agrégés au niveau du parc.

## Démarrage

```bash
# 1. (recommendé) peupler les tables de maintenance vides
uv run python GMAO-ANALYTICS/scripts/seed_maintenance.py \
    --db "mysql+pymysql://root:PASS@127.0.0.1:3306/gmao_rag" --months 12 --seed 7 --reset

# 2. Lancer le service
uv run --env-file GMAO-ANALYTICS/.env uvicorn gmao_analytics.api.main:app \
    --host 127.0.0.1 --port 8300
```

Ouvrir `http://127.0.0.1:8300/docs` pour la documentation Swagger.

## Dashboard de visualisation

Une page HTML/CSS/JS statique (sans build ni dépendance front) est servie
sur la racine **`http://127.0.0.1:8300/`**. Elle interroge directement
`/api/v1/metrics` et affiche :

- des **cartes KPI** globales (MTBF, MTTR, disponibilité, pannes, interventions) ;
- un **tableau par équipement** (criticité colorée, MTBF/MTTR/dispo, pannes) ;
- des **barres de disponibilité** par équipement (couleur selon le seuil) ;
- des boutons d'**export** du rapport (Markdown / CSV) et d'actualisation.

Fichier : `static/index.html` (servi par la route `/` via `FileResponse`,
hors schéma OpenAPI — non présent dans `/docs`).

## Enrichissement ML (tolérant)

Le rapport croise le MTBF avec un niveau de risque prédictif. GMAO-ANALYTICS
interroge `GMAO-ML` (`GET /api/v1/model/info`) ; si celui-ci est indisponible,
l'enrichissement est **dégradé mais non bloquant** (`risk` vide, rapport intact).

## Structure

```
gmao_analytics/
├── config.py        # settings env (résolus relativement à GMAO-ANALYTICS/)
├── db.py            # source MySQL (pannes/ordre_travails/equipements) + fallback
├── metrics/engine.py# calcul pur MTBF/MTTR/disponibilité (pandas, testable)
├── models/schemas.py# requêtes/réponses Pydantic
├── services/        # analytics (orchestration) + ml_client (enrichissement)
└── api/             # FastAPI, routes /api/v1/*
scripts/seed_maintenance.py  # peuple les tables de maintenance (test)
```

## Tests

```bash
uv run pytest GMAO-ANALYTICS -q
```

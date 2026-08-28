# GMAO-ANALYTICS — Documentation Complète des Endpoints

> **Base URL** : `http://127.0.0.1:8300`
> **Version** : v1 (préfixe `/api/v1`)
> **Format** : JSON (`Content-Type: application/json`)
> **Authentification** : Aucune — tous les services communiquent librement
> **Rôle** : calcul des indicateurs de maintenance **MTBF / MTTR / disponibilité** + génération de **rapports** enrichis du risque prédictif (GMAO-ML)

---

## Table des matières

1. [GET /api/v1/healthz — Santé du service](#1-get-apiv1healthz--santé-du-service)
2. [GET /api/v1/metrics — Indicateurs globaux + par équipement](#2-get-apiv1metrics--indicateurs-globaux--par-équipement)
3. [GET /api/v1/metrics/equipement/{id} — Indicateurs d'un équipement](#3-get-apiv1metricsequipementid--indicateurs-dun-équipement)
4. [GET /api/v1/report — Rapport de maintenance (JSON/CSV/Markdown)](#4-get-apiv1report--rapport-de-maintenance-jsoncsvmarkdown)
5. [GET / — Dashboard de visualisation](#5-get----dashboard-de-visualisation)
6. [Schéma des indicateurs — MetricSummary](#6-schéma-des-indicateurs--metricsummary)
7. [Croisement risque prédictif — RiskCrossover](#7-croisement-risque-prédictif--riskcrossover)
8. [Interpréter les résultats](#8-interpréter-les-résultats)
9. [Exemples d'intégration Laravel](#9-exemples-dintégration-laravel)
10. [Codes d'erreur](#10-codes-derreur)

---

## 1. GET /api/v1/healthz — Santé du service

Vérifie que GMAO-ANALYTICS est joignable et indique si l'enrichissement GMAO-ML est disponible. **Aucune auth requise.**

### Requête

```bash
curl http://127.0.0.1:8300/api/v1/healthz
```

### Réponse `200 OK`

```json
{
  "status": "ok",
  "service": "gmao-analytics",
  "version": "0.1.0",
  "ml_api_reachable": false,
  "equipements_count": 12
}
```

| Champ | Type | Description |
|---|---|---|
| `status` | string | `"ok"` ou `"degraded"` |
| `service` | string | Nom du service (`"gmao-analytics"`) |
| `version` | string | Version du code |
| `ml_api_reachable` | bool | `true` si GMAO-ML (:8100) répond — sinon `false` (l'analytique reste fonctionnelle) |
| `equipements_count` | int | Nombre d'équipements du parc lus depuis la base MySQL |

### Utilisation Laravel

```php
$response = Http::get('http://127.0.0.1:8300/api/v1/healthz');

if ($response->json('ml_api_reachable') === false) {
    Log::warning('Enrichissement GMAO-ML indisponible — rapports non enrichis');
}
```

---

## 2. GET /api/v1/metrics — Indicateurs globaux + par équipement

Calcule les trois indicateurs du parc **et** leur ventilation par équipement. **Aucune auth requise.**

### Requête

```bash
curl http://127.0.0.1:8300/api/v1/metrics
```

### Réponse `200 OK`

```json
{
  "global": {
    "mtbf_hours": 1862.83,
    "mttr_hours": 23.13,
    "availability_pct": 98.77,
    "nb_pannes": 52,
    "nb_interventions": 52
  },
  "per_equipement": [
    {
      "mtbf_hours": 2004.56,
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
  "generated_at": "2026-08-28T13:06:56"
}
```

### Structure

| Champ | Type | Description |
|---|---|---|
| `global` | object [MetricSummary](#6-schéma-des-indicateurs--metricsummary) | Indicateurs agrégés de tout le parc |
| `per_equipement` | array [EquipementMetrics] | Un objet par équipement (identité + indicateurs) |
| `generated_at` | string | Horodatage ISO-8601 du calcul |

### Particularité importante (`global` vs `per_equipement`)

- **`global.mtbf_hours`** : moyenne pondérée des MTBF sur les équipements disposant d'un historique de pannes.
- **`global.availability_pct`** = `MTBF / (MTBF + MTTR)` calculé sur les **totaux agrégés**, pas la moyenne des disponibilités individuelles.
- Chaque élément de `per_equipement` contient **l'identité complète** (id, nom, localisation, criticité, marque, modèle) **et** ses indicateurs.

### Alias lisible

`GET /api/v1/metrics/equipements` renvoie **strictement la même réponse** que `/metrics`. Fourni pour la lisibilité sémantique (utile si l'on préfère un chemin « RESTful »).

---

## 3. GET /api/v1/metrics/equipement/{id} — Indicateurs d'un équipement

Retourne les indicateurs filtrés sur un **seul** équipement. **Aucune auth requise.**

### Requête

```bash
curl http://127.0.0.1:8300/api/v1/metrics/equipement/5
```

### Réponse `200 OK`

```json
{
  "global": {
    "mtbf_hours": 1862.83,
    "mttr_hours": 23.13,
    "availability_pct": 98.77,
    "nb_pannes": 52,
    "nb_interventions": 52
  },
  "per_equipement": [
    {
      "mtbf_hours": 1274.91,
      "mttr_hours": 22.93,
      "availability_pct": 98.23,
      "nb_pannes": 6,
      "nb_interventions": 6,
      "id_equipement": 5,
      "nom_equipement": "Tour CNC",
      "localisation": "Atelier d'usinage",
      "criticite": "critique",
      "marque": "Mazak",
      "modele": "QT-200"
    }
  ],
  "generated_at": "2026-08-28T13:06:56"
}
```

> **À noter pour la liaison Laravel** : `global` conserve les valeurs **du parc entier** (non recalculé sur le seul équipement). Pour obtenir les indicateurs du seul équipement filtré, lire **`per_equipement[0]`** et **ignorer** `global`.

### Erreur `404 Not Found`

Si l'ID n'existe pas dans le référentiel :

```json
{
  "detail": "Équipement 999 introuvable."
}
```

---

## 4. GET /api/v1/report — Rapport de maintenance (JSON/CSV/Markdown)

Génère un rapport complet : indicateurs, ventilation par équipement, **risque prédictif croisé (GMAO-ML)** et texte lisible. **Aucune auth requise.**

### Paramètre de requête

| Paramètre | Valeurs | Défaut | Description |
|---|---|---|---|
| `format` | `json` \| `csv` \| `markdown` | `json` | Format de sortie du rapport |

### 4.1 Format JSON (défaut) — `GET /api/v1/report`

```bash
curl -H "Accept: application/json" http://127.0.0.1:8300/api/v1/report
```

#### Réponse `200 OK`

```json
{
  "generated_at": "2026-08-28T13:08:57",
  "global_metrics": {
    "mtbf_hours": 1862.84,
    "mttr_hours": 23.13,
    "availability_pct": 98.77,
    "nb_pannes": 52,
    "nb_interventions": 52
  },
  "per_equipement": [
    {
      "mtbf_hours": 2004.57,
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
  "risk": [
    {
      "equipement_id": 5,
      "equipement_nom": "Tour CNC",
      "predicted_risk": "critique",
      "probability_failure": 0.363,
      "mtbf_hours": 1274.91,
      "nb_pannes": 6,
      "comment": "Risque élevé : intervention préventive prioritaire recommandée."
    }
  ],
  "text": "# Rapport de maintenance (GMAO Analytics)\n\n_Généré le : 2026-08-28T13:08:57_\n\n## Indicateurs globaux\n\n| Indicateur | Valeur |\n|---|---|\n...",
  "content_type": "json"
}
```

### 4.2 Format Markdown — `GET /api/v1/report?format=markdown`

```bash
curl "http://127.0.0.1:8300/api/v1/report?format=markdown"
```

Retourne le corps texte en `text/markdown` avec l'en-tête `Content-Disposition: attachment; filename=rapport_maintenance.md`. Contenu lisible en console/rédaction :

```markdown
# Rapport de maintenance (GMAO Analytics)

_Généré le : 2026-08-28T13:08:57_

## Indicateurs globaux

| Indicateur | Valeur |
|---|---|
| MTBF | 1862.84 h |
| MTTR | 23.13 h |
| Disponibilité | 98.77 % |
| Pannes recensées | 52 |
| Interventions terminées | 52 |

## Détail par équipement

| Équipement | MTBF (h) | MTTR (h) | Dispo (%) | Pannes |
|---|---|---|---|---|
| Compresseur industriel (#1) | 2004.57 | 18.27 | 99.1 | 4 |
| Pompe hydraulique (#2) | 875.09 | 17.29 | 98.06 | 5 |
```

La section « ## Croisement risque prédictif (GMAO-ML) » apparaît **seulement si** GMAO-ML est joignable.

### 4.3 Format CSV — `GET /api/v1/report?format=csv`

```bash
curl "http://127.0.0.1:8300/api/v1/report?format=csv"
```

Retourne une table plate en `text/csv` avec l'en-tête `Content-Disposition: attachment; filename=rapport_maintenance.csv`. **En-têtes de colonnes** :

```csv
mtbf_hours,mttr_hours,availability_pct,nb_pannes,nb_interventions,id_equipement,nom_equipement,localisation,criticite,marque,modele
2004.57,18.27,99.1,4,4,1,Compresseur industriel,Atelier A - Zone 1,elevee,Atlas Copco,GA 75
875.09,17.29,98.06,5,5,2,Pompe hydraulique,Atelier A - Zone 2,critique,Bosch Rexroth,A10VSO
```

### Comportement si GMAO-ML est indisponible (tolérance)

`risk` vaut alors `null` ou `[]` et `text` **n'inclut pas** la section croisement ML. **Le reste du rapport reste intact** — l'analytique ne dépend jamais de la prédiction.

---

## 5. GET / — Dashboard de visualisation

Une page HTML/CSS/JS statique (sans build ni dépendance front) est servie sur la racine.

```bash
curl http://127.0.0.1:8300/
```

- **Type** : `text/html`
- **Route hors schéma OpenAPI** (non visible dans `/docs`)
- **Contenu** : cartes KPI globales (MTBF/MTTR/dispo/pannes/interventions), tableau par équipement avec criticité colorée, barres de disponibilité, boutons d'export Markdown/CSV et d'actualisation.

> **Liaison Laravel** : inutile de l'appeler depuis le backend — elle est faite pour un navigateur. Pour récupérer les données, utiliser directement `/api/v1/metrics` et `/api/v1/report`.

---

## 6. Schéma des indicateurs — MetricSummary

Objet réutilisé pour `global` (/metrics) et `global_metrics` (/report), et comme base de chaque `per_equipement`.

| Champ | Type | Description |
|---|---|---|
| `mtbf_hours` | float/null | Temps moyen **entre** deux pannes (heures). `null` si aucun historique |
| `mttr_hours` | float/null | Temps moyen **de réparation** (heures). `null` si aucun OT « terminé » |
| `availability_pct` | float/null | Disponibilité = `MTBF / (MTBF + MTTR)` en % |
| `nb_pannes` | int | Nombre de pannes recensées dans l'historique |
| `nb_interventions` | int | Nombre d'ordres de travail « terminés » |

### Règles de calcul (pour l'interprétation)

- **MTBF** : moyenne des écarts entre pannes consécutives d'un équipement (uptime courant inclus) — plus il est **élevé**, mieux c'est.
- **MTTR** : dérivé de `temps_reel` (minutes) des OT terminés, sinon de la durée `date_fin − date_debut` — plus il est **bas**, mieux c'est.
- **Disponibilité** : 100% = toujours en état de marche. Sous ~95% : fiabilité préoccupante.

---

## 7. Croisement risque prédictif — RiskCrossover

Objet présent dans `report.risk` lorsque GMAO-ML est joignable.

| Champ | Type | Description |
|---|---|---|
| `equipement_id` | int | ID de l'équipement |
| `equipement_nom` | string | Nom lisible |
| `predicted_risk` | string | `faible` \| `moyen` \| `eleve` \| `critique` \| `inconnu` |
| `probability_failure` | float/null | Probabilité de panne (heuristique MTBF, 0.0 à 1.0) |
| `mtbf_hours` | float/null | MTBF de l'équipement (même valeur que dans `per_equipement`) |
| `nb_pannes` | int | Nombre de pannes |
| `comment` | string | Recommandation lisible en français |

### Commentaires associés

| `predicted_risk` | `comment` |
|---|---|
| `faible` | Historique de pannes sain, pas d'action préventive urgente. |
| `moyen` | Fiabilité moyenne : surveillance préventive conseillée. |
| `eleve` | Fiabilité dégradée : planifier une visite préventive. |
| `critique` | Risque élevé : intervention préventive prioritaire recommandée. |
| `inconnu` | Données insuffisantes pour évaluer le risque. |

---

## 8. Interpréter les résultats

### Tableau de bord des seuils (disponibilité)

| Disponibilité | Appréciation | Action suggérée |
|---|---|---|
| ≥ 98 % | Excellente fiabilité | Surveillance normale |
| 95 – 98 % | Fiabilité correcte | Surveillance renforcée |
| < 95 % | Fiabilité dégradée | Planifier maintenance préventive |

### Priorisation par criticité (référentiel `equipements`)

| `criticite` | Priorité d'intervention |
|---|---|
| `critique` | Intervention immédiate requise |
| `elevee` | Intervention dans les 24h |
| `moyenne` | Intervention planifiable |

### Croiser MTBF + risque prédit

Un équipement avec un **MTBF court** et un risque **`eleve`/`critique`** doit être traité en priorité par le planificateur de maintenance Laravel.

---

## 9. Exemples d'intégration Laravel

### 9.1 Récupérer les indicateurs globaux + par équipement

```php
use Illuminate\Support\Facades\Http;

function getAnalytics(): array
{
    $response = Http::timeout(10)->get('http://127.0.0.1:8300/api/v1/metrics');
    $response->throw();
    return $response->json();
}

// Utilisation :
$data = getAnalytics();
$availability = $data['global']['availability_pct'];       // 98.77
$mtbf = $data['global']['mtbf_hours'];                     // 1862.83
foreach ($data['per_equipement'] as $eq) {
    // $eq['nom_equipement'], $eq['criticite'], $eq['availability_pct'], ...
}
```

### 9.2 Indicateurs d'un équipement précis (attention : lire `per_equipement[0]`)

```php
use Illuminate\Support\Facades\Http;

function getEquipementAnalytics(int $id): ?array
{
    $response = Http::timeout(10)->get(
        "http://127.0.0.1:8300/api/v1/metrics/equipement/{$id}"
    );
    if ($response->failed()) return null; // 404 : équipement inconnu
    return $response->json('per_equipement.0'); // indicateurs du seul équipement
}
```

### 9.3 Générer le rapport et l'archiver

```php
use Illuminate\Support\Facades\Http;

// Rapport markdown (texte lisible pour archivage / email)
$md = Http::get('http://127.0.0.1:8300/api/v1/report?format=markdown')->body();

// Rapport CSV (table pour import Excel / DataTable)
$csv = Http::get('http://127.0.0.1:8300/api/v1/report?format=csv')->body();

// Données structurées + risque prédictif
$json = Http::get('http://127.0.0.1:8300/api/v1/report')->json();
foreach ($json['risk'] ?? [] as $risk) {
    if (in_array($risk['predicted_risk'], ['eleve', 'critique'], true)) {
        Log::alert('Équipement à risque', $risk);
    }
}
```

### 9.4 Alerter sur la disponibilité

```php
use Illuminate\Support\Facades\Http;

function getUserMailForEquipment() {} // ton mapping Laravel local

$data = Http::get('http://127.0.0.1:8300/api/v1/metrics')->json();
foreach ($data['per_equipement'] as $eq) {
    if (($eq['availability_pct'] ?? 100) < 95.0) {
        // déclenche une notification / email maintenance
        event(new MaintenanceAlert($eq['equipement_id'], $eq['availability_pct']));
    }
}
```

---

## 10. Codes d'erreur

| Code HTTP | Description |
|---|---|
| 200 | Succès (toutes les routes GET) |
| 404 | Équipement introuvable (`/metrics/equipement/{id}`) — corps `{"detail": "..."}` |
| 422 | Paramètre invalide (ex. `format` hors de `json/csv/markdown`) |
| 500 | Erreur interne inattendue |

### Format d'erreur FastAPI (défaut)

```json
{ "detail": "Description de l'erreur" }
```

> **Note** : contrairement à GMAO-API, ce service ne renvoie pas de code `ML_UNREACHABLE/503` : l'enrichissement GMAO-ML est **tolérant**, il ne bloque jamais le rapport (seul `report.risk` est vide).

---

## Annexe A : Ports et configuration

| Service | Port | URL |
|---|---|---|
| GMAO-ANALYTICS | 8300 | http://127.0.0.1:8300 |
| GMAO-ML | 8100 | http://127.0.0.1:8100 |
| GMAO-API | 8200 | http://127.0.0.1:8200 |
| MySQL | 3306 | 127.0.0.1:3306/gmao_rag |

## Annexe B : Catalogue des équipements (12)

| ID | Nom | Criticité |
|---|---|---|
| 1 | Compresseur industriel | elevee |
| 2 | Pompe hydraulique | critique |
| 3 | Moteur électrique | moyenne |
| 4 | Convoyeur industriel | elevee |
| 5 | Tour CNC | critique |
| 6 | Fraiseuse CNC | elevee |
| 7 | Chaudière industrielle | critique |
| 8 | Ventilateur industriel | moyenne |
| 9 | Groupe électrogène | critique |
| 10 | Robot industriel | critique |
| 11 | Machine de soudage | elevee |
| 12 | Presse hydraulique | critique |

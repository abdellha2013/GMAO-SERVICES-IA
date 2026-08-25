# GMAO-API — Documentation Complète des Endpoints

> **Base URL** : `http://127.0.0.1:8200`
> **Version** : v1 (préfixe `/api/v1`)
> **Format** : JSON (`Content-Type: application/json`)
> **Authentification** : Aucune — tous les services communiquent librement

---

## Table des matières

1. [GET /api/v1/healthz](#1-get-apiv1healthz--santé-du-service)
2. [POST /api/v1/predictions](#2-post-apiv1predictions--prédiction-depuis-des-relevés-réels)
3. [POST /api/v1/simulate](#3-post-apiv1simulate--génération--prédiction-en-un-seul-appel)
4. [Schéma SensorReading](#4-schéma-des-données--sensorreading)
5. [Catalogue des équipements](#5-catalogue-des-équipements)
6. [Interpréter les résultats](#6-interpréter-les-résultats)
7. [Exemples d'intégration Laravel](#7-exemples-dintégration-laravel)
8. [Codes d'erreur](#8-codes-derreur)

---

## 1. GET /api/v1/healthz — Santé du service

Vérifie que GMAO-API et GMAO-ML sont joignables. **Aucune auth requise.**

### Requête

```bash
curl http://127.0.0.1:8200/api/v1/healthz
```

### Réponse `200 OK`

```json
{
  "status": "ok",
  "service": "gmao-api",
  "version": "0.1.0",
  "ml_api_reachable": true
}
```

| Champ | Type | Description |
|---|---|---|
| `status` | string | `"ok"` ou `"degraded"` si GMAO-ML est injoignable |
| `service` | string | Nom du service |
| `version` | string | Version du code |
| `ml_api_reachable` | bool | `true` si GMAO-ML (:8100) répond |

### Utilisation Laravel

```php
$response = Http::get('http://127.0.0.1:8200/api/v1/healthz');

if ($response->json('ml_api_reachable') === false) {
    Log::warning('GMAO-ML indisponible');
}
```

---

## 2. POST /api/v1/predictions — Prédiction depuis des relevés réels

Envoie des relevés capteurs et reçoit les prédictions du modèle ML. **Aucune auth requise.**

### Requête

```bash
curl -X POST http://127.0.0.1:8200/api/v1/predictions \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [
      {
        "equipement_id": 5,
        "Type": "L",
        "Air temperature [K]": 298.9,
        "Process temperature [K]": 308.4,
        "Rotational speed [rpm]": 1450,
        "Torque [Nm]": 95,
        "Tool wear [min]": 120
      }
    ]
  }'
```

### Corps de la requête

| Champ | Type | Obligatoire | Contrainte | Description |
|---|---|---|---|---|
| `readings` | array | Oui | 1-100 éléments | Liste des relevés capteurs |

Chaque élément suit le schéma [SensorReading](#4-schéma-des-données--sensorreading).

### Réponse `200 OK`

```json
{
  "results": [
    {
      "equipement_id": 5,
      "equipement_nom": "Tour CNC (#5)",
      "prediction": 1,
      "probability_failure": 0.9532,
      "model_version": "20260824_150222"
    }
  ],
  "readings": null,
  "model_version": "20260824_150222"
}
```

> **Note** : `readings` est `null` ici (pas de génération côté API).

### Exemples curl

**Panne probable (torque élevé + usure élevée) :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/predictions \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [{
      "equipement_id": 5,
      "Type": "L",
      "Air temperature [K]": 298.9,
      "Process temperature [K]": 308.4,
      "Rotational speed [rpm]": 1450,
      "Torque [Nm]": 95,
      "Tool wear [min]": 120
    }]
  }'
```

**Machine saine (torque faible + usure faible) :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/predictions \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [{
      "equipement_id": 2,
      "Type": "M",
      "Air temperature [K]": 301.2,
      "Process temperature [K]": 310.8,
      "Rotational speed [rpm]": 2800,
      "Torque [Nm]": 35,
      "Tool wear [min]": 50
    }]
  }'
```

**Plusieurs relevés d'un coup :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/predictions \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [
      {
        "equipement_id": 1,
        "Type": "L",
        "Air temperature [K]": 295.0,
        "Process temperature [K]": 305.0,
        "Rotational speed [rpm]": 1500,
        "Torque [Nm]": 40,
        "Tool wear [min]": 10
      },
      {
        "equipement_id": 5,
        "Type": "H",
        "Air temperature [K]": 302.0,
        "Process temperature [K]": 312.0,
        "Rotational speed [rpm]": 2600,
        "Torque [Nm]": 110,
        "Tool wear [min]": 200
      },
      {
        "equipement_id": 9,
        "Type": "L",
        "Air temperature [K]": 298.0,
        "Process temperature [K]": 308.0,
        "Rotational speed [rpm]": 1400,
        "Torque [Nm]": 60,
        "Tool wear [min]": 80
      }
    ]
  }'
```

---

## 3. POST /api/v1/simulate — Génération + prédiction en un seul appel

Génère des relevés capteurs aléatoires **et** les envoie au modèle ML. La réponse contient les relevés générés **et** les prédictions. **Aucune auth requise.**

### Requête

```bash
curl -X POST http://127.0.0.1:8200/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"count": 3, "failure_rate": 0.5, "random_state": 42}'
```

### Corps de la requête

| Champ | Type | Obligatoire | Défaut | Contrainte | Description |
|---|---|---|---|---|---|
| `count` | int | Non | 10 | 1-100 | Nombre de relevés à générer |
| `failure_rate` | float | Non | 0.3 | 0.0-1.0 | Taux de pannes (0.0=tous sains, 1.0=tous en panne) |
| `random_state` | int/null | Non | null | - | Seed pour reproductibilité |

### Réponse `200 OK`

```json
{
  "results": [
    {
      "equipement_id": 1,
      "equipement_nom": "Compresseur industriel (#1)",
      "prediction": 1,
      "probability_failure": 0.9992,
      "model_version": "20260824_150222"
    },
    {
      "equipement_id": 7,
      "equipement_nom": "Chaudière industrielle (#7)",
      "prediction": 1,
      "probability_failure": 0.9995,
      "model_version": "20260824_150222"
    },
    {
      "equipement_id": 12,
      "equipement_nom": "Presse hydraulique (#12)",
      "prediction": 0,
      "probability_failure": 0.0045,
      "model_version": "20260824_150222"
    }
  ],
  "readings": [
    {
      "equipement_id": 1,
      "Type": "L",
      "Air temperature [K]": 298.7,
      "Process temperature [K]": 306.8,
      "Rotational speed [rpm]": 1326.0,
      "Torque [Nm]": 46.92,
      "Tool wear [min]": 17
    },
    {
      "equipement_id": 7,
      "Type": "L",
      "Air temperature [K]": 298.2,
      "Process temperature [K]": 308.0,
      "Rotational speed [rpm]": 2793.0,
      "Torque [Nm]": 3.7,
      "Tool wear [min]": 143
    },
    {
      "equipement_id": 12,
      "Type": "H",
      "Air temperature [K]": 298.9,
      "Process temperature [K]": 309.4,
      "Rotational speed [rpm]": 1440.0,
      "Torque [Nm]": 37.68,
      "Tool wear [min]": 182
    }
  ],
  "model_version": "20260824_150222"
}
```

### Différence avec /predictions

| | `POST /predictions` | `POST /simulate` |
|---|---|---|
| **Input** | Relevés réels (fournis par l'utilisateur) | Paramètres de génération (count, failure_rate) |
| **`readings` dans la réponse** | `null` | Liste des relevés générés |
| **Usage** | Production : données capteurs réelles | Développement / démo / test |

### Exemples curl

**10 relevés aléatoires (30% pannes) :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"count": 10, "failure_rate": 0.3}'
```

**Reproductible (seed fixe) :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"count": 5, "failure_rate": 0.5, "random_state": 42}'
```

**Tous sains :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"count": 20, "failure_rate": 0}'
```

**Tous en panne :**

```bash
curl -X POST http://127.0.0.1:8200/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"count": 12, "failure_rate": 1.0, "random_state": 7}'
```

---

## 4. Schéma des données — SensorReading

Chaque relevé capteur suit ce schéma. Les champs utilisent des alias (noms exacts avec espaces et unités) pour coller au dataset AI4I d'origine.

### Exemple JSON

```json
{
  "equipement_id": 5,
  "Type": "L",
  "Air temperature [K]": 298.9,
  "Process temperature [K]": 308.4,
  "Rotational speed [rpm]": 1450,
  "Torque [Nm]": 95,
  "Tool wear [min]": 120
}
```

### Tableau des champs

| Champ JSON | Type | Obligatoire | Défaut | Contrainte | Description |
|---|---|---|---|---|---|
| `equipement_id` | int | Oui | - | >= 1 | ID de la table `equipements` (voir catalogue) |
| `Type` | string | Non | `"L"` | `"L"`, `"M"`, `"H"` | Type de machine : Light, Medium, Heavy |
| `Air temperature [K]` | float | Oui | - | 250-350 | Température ambiante en Kelvin |
| `Process temperature [K]` | float | Oui | - | 250-400 | Température du processus en Kelvin |
| `Rotational speed [rpm]` | float | Oui | - | > 0 | Vitesse de rotation en tours/minute |
| `Torque [Nm]` | float | Oui | - | >= 0 | Couple en Newton-mètres |
| `Tool wear [min]` | float | Oui | - | >= 0 | Usure de l'outil en minutes |

### Règles métier

- `Process temperature [K]` doit être > `Air temperature [K]` (le processus chauffe)
- `Rotational speed` x `Torque` = puissance mécanique (plus c'est élevé, plus la machine travaille fort)
- `Tool wear` augmente avec le temps d'utilisation (usure normale)
- Plus **Torque** est élevé + **Tool wear** est élevé => plus le risque de panne est élevé
- Le modèle détecte surtout les pannes avec torque > 60 Nm ET tool wear > 100 min

### Types de machine (`Type`)

| Valeur | Signification | Exemples |
|---|---|---|
| `"L"` | Light — machines légères | Compresseur, ventilateur |
| `"M"` | Medium — machines moyennes | Pompe, moteur électrique |
| `"H"` | Heavy — machines lourdes | Presse hydraulique, robot industriel |

---

## 5. Catalogue des équipements

12 équipements dans MySQL (`gmao_rag` / table `equipements`) :

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

### Niveaux de criticité

| Criticité | Priorité d'intervention |
|---|---|
| `critique` | Intervention immédiate requise |
| `elevee` | Intervention dans les 24h |
| `moyenne` | Intervention planifiable |

---

## 6. Interpréter les résultats

### Structure d'un résultat

```json
{
  "equipement_id": 5,
  "equipement_nom": "Tour CNC (#5)",
  "prediction": 1,
  "probability_failure": 0.9532,
  "model_version": "20260824_150222"
}
```

| Champ | Type | Description |
|---|---|---|
| `equipement_id` | int | ID de l'équipement |
| `equipement_nom` | string | Nom lisible (depuis la BDD) |
| `prediction` | int | `1` = panne prédite, `0` = machine saine |
| `probability_failure` | float | Probabilité de panne (0.0 à 1.0) |
| `model_version` | string/null | Version du modèle ML utilisé |

### Règles de décision

| Probabilité | Interprétation | Action suggérée |
|---|---|---|
| 0.00 - 0.50 | Faible risque | Surveillance normale |
| 0.50 - 0.75 | Risque modéré | Surveillance renforcée |
| 0.75 - 0.90 | Risque élevé | Planifier maintenance préventive |
| 0.90 - 1.00 | Risque critique | Intervention urgente recommandée |

### Performance du modèle (v20260824_150222)

| Métrique | Valeur |
|---|---|
| F1-macro | 0.9553 |
| Recall (pannes détectées) | 85.3% |
| Précision | 98.3% |
| Modèle | HistGradientBoosting |
| Coût FN/FP | 10x (FN=10, FP=1) |

---

## 7. Exemples d'intégration Laravel

### 7.1 Vérifier la santé de GMAO-API

```php
use Illuminate\Support\Facades\Http;

function checkGmaoHealth(): bool
{
    $response = Http::timeout(5)->get('http://127.0.0.1:8200/api/v1/healthz');
    if ($response->failed()) return false;
    return $response->json('ml_api_reachable') === true;
}
```

### 7.2 Envoyer des relevés et obtenir des prédictions

```php
use Illuminate\Support\Facades\Http;

function predictFailure(array $readings): array
{
    $response = Http::timeout(15)->post('http://127.0.0.1:8200/api/v1/predictions', [
        'readings' => $readings,
    ]);

    if ($response->failed()) {
        throw new \RuntimeException('Erreur GMAO-API: ' . $response->body());
    }

    return $response->json();
}

// Utilisation :
$result = predictFailure([
    [
        'equipement_id' => 5,
        'Type' => 'L',
        'Air temperature [K]' => 298.9,
        'Process temperature [K]' => 308.4,
        'Rotational speed [rpm]' => 1450,
        'Torque [Nm]' => 95,
        'Tool wear [min]' => 120,
    ],
]);

// $result['results'][0]['prediction'] === 1  (panne)
// $result['results'][0]['probability_failure'] === 0.9532
```

### 7.3 Générer des données de test (simulate)

```php
function simulateReadings(int $count = 10, float $failureRate = 0.3): array
{
    $response = Http::post('http://127.0.0.1:8200/api/v1/simulate', [
        'count' => $count,
        'failure_rate' => $failureRate,
        'random_state' => (int) now()->timestamp,
    ]);

    return $response->json();
}

// Retourne :
// - 'results'   => prédictions ML
// - 'readings'  => relevés générés (réutilisables pour /predictions)
```

### 7.4 Boucle de surveillance continue

```php
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

function surveillanceLoop(): void
{
    while (true) {
        if (!checkGmaoHealth()) {
            Log::warning('GMAO-ML indisponible, attente 30s');
            sleep(30);
            continue;
        }

        $failureRate = (mt_rand(0, 100) < 5) ? 1.0 : 0.0;
        $response = Http::post('http://127.0.0.1:8200/api/v1/simulate', [
            'count' => 1,
            'failure_rate' => $failureRate,
        ]);

        $data = $response->json();
        $result = $data['results'][0];

        if ($result['prediction'] === 1) {
            Log::alert('PANNE prédite', [
                'equipement' => $result['equipement_nom'],
                'probabilite' => $result['probability_failure'],
            ]);
        }

        sleep(mt_rand(6, 14));
    }
}
```

### 7.5 Réutiliser les readings générés

```php
$simResponse = Http::post('http://127.0.0.1:8200/api/v1/simulate', [
    'count' => 3,
    'failure_rate' => 0.5,
]);

$generatedReadings = $simResponse->json('readings');

$predResponse = Http::post('http://127.0.0.1:8200/api/v1/predictions', [
    'readings' => $generatedReadings,
]);
```

---

## 8. Codes d'erreur

| Code HTTP | `error_code` | Description |
|---|---|---|
| 422 | `VALIDATION_ERROR` | Payload invalide (champs manquants, valeurs hors limites) |
| 503 | `ML_UNREACHABLE` | GMAO-ML injoignable ou timeout |
| 500 | `API_INTERNAL_ERROR` | Erreur interne inattendue |

### Format de réponse d'erreur

```json
{
  "message": "Description de l'erreur",
  "error_code": "CODE_ERREUR",
  "details": {}
}
```

---

## Annexe A : Ports et configuration

| Service | Port | URL |
|---|---|---|
| GMAO-API | 8200 | http://127.0.0.1:8200 |
| GMAO-ML | 8100 | http://127.0.0.1:8100 |
| MySQL | 3306 | 127.0.0.1:3306/gmao_rag |
| Dashboard | 8200 | http://127.0.0.1:8200/ |

## Annexe B : Variables d'environnement GMAO-API

| Variable | Défaut | Description |
|---|---|---|
| `API_PORT` | 8200 | Port de l'API |
| `ML_API_URL` | http://127.0.0.1:8100 | URL du service GMAO-ML |
| `ML_TIMEOUT_S` | 10 | Timeout vers GMAO-ML (secondes) |
| `ML_RETRIES` | 2 | Nombre de tentatives vers GMAO-ML |
| `EQUIPEMENTS_DB_URL` | (vide) | URL MySQL (vide = catalogue Python fallback) |
| `CRITICAL_PROBABILITY` | 0.90 | Seuil de criticité pour les alertes |

# GMAO-OCR — Documentation Complète des Endpoints

> **Base URL** : `http://127.0.0.1:8400`
> **Version** : v1 (préfixe `/api/v1`)
> **Format** : JSON (`application/json`) — upload via `multipart/form-data`
> **Authentification** : Aucune — tous les services communiquent librement
> **Rôle** : lecture des **QR codes d'équipements** à partir d'une simple **photo** (vision, OpenCV/pyzbar), validation anti-phishing de l'URL, extraction `id_equipement` et enrichissement optionnel via l'API Laravel.

---

## Table des matières

1. [GET /api/v1/healthz — Santé du service](#1-get-apiv1healthz--santé-du-service)
2. [POST /api/v1/qr/scan — Scanner un QR depuis une photo](#2-post-apiv1qrscan--scanner-un-qr-depuis-une-photo)
3. [Schéma de réponse — ScanResponse](#3-schéma-de-réponse--scanresponse)
4. [Moteurs de décodage — pyzbar / OpenCV](#4-moteurs-de-décodage--pyzbar--opencv)
5. [Exemples d'intégration Laravel](#5-exemples-dintégration-laravel)
6. [Codes d'erreur](#6-codes-derreur)
7. [Configuration (.env)](#7-configuration-env)

---

## 1. GET /api/v1/healthz — Santé du service

Vérifie que GMAO-OCR est joignable et indique le **moteur de décodage actif** ainsi que la disponibilité de l'API Laravel. **Aucune auth requise.**

### Requête

```bash
curl http://127.0.0.1:8400/api/v1/healthz
```

### Réponse `200 OK`

```json
{
  "status": "ok",
  "service": "gmao-ocr",
  "version": "0.1.0",
  "decoder": "opencv",
  "laravel_configured": false
}
```

| Champ | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `service` | string | Nom du service (`"gmao-ocr"`) |
| `version` | string | Version du code |
| `decoder` | string | Moteur effectif : `"pyzbar"` (si `libzbar0` présente), `"opencv"` (fallback), sinon `"none"` |
| `laravel_configured` | bool | `true` si une URL API Laravel est configurée (sinon pas d'enrichissement) |

### Utilisation Laravel

```php
$response = Http::get('http://127.0.0.1:8400/api/v1/healthz');

if ($response->json('decoder') === 'none') {
    Log::error('GMAO-OCR sans moteur de décodage QR');
}
```

---

## 2. POST /api/v1/qr/scan — Scanner un QR depuis une photo

Décode le QR code d'une image (**SVG, PNG, EPS ou JPEG**), **valide** que son
contenu est une URL de fiche équipement au format `/api/equipements/{id}`
(anti-phishing), en extrait l'`id_equipement` et, si l'API Laravel est
configurée, renvoie la fiche détaillée. **Aucune auth requise.**

### Requête

Champ `file` — image contenant le QR. Formats **SVG** (`image/svg+xml`),
**PNG** (`image/png`), **EPS** (`application/postscript`) ou **JPEG**
(`image/jpeg`), ≤ 10 Mo :

```bash
curl -X POST http://127.0.0.1:8400/api/v1/qr/scan \
  -F "file=@qr_equipement.svg;type=image/svg+xml" \
  -H "Content-Type: multipart/form-data"
```

> Les formats vectoriels sont **rasterisés avant décodage** : SVG via
> **CairoSVG**, EPS via **Pillow + Ghostscript**. La liste acceptée est
> configurable via `OCR_ACCEPTED_CONTENT_TYPES`.

### Réponse `200 OK` — enrichissement réussi (Laravel joignable)

```json
{
  "success": true,
  "id_equipement": 5,
  "lien_equipement": "https://mondomaine.com/api/equipements/5",
  "equipement": {
    "id": 5,
    "nom": "Pompe Centrifuge P-101",
    "site": "Sfax"
  },
  "method": "opencv"
}
```

### Réponse `200 OK` — sans enrichissement (Laravel non configuré ou injoignable)

```json
{
  "success": true,
  "id_equipement": 5,
  "lien_equipement": "https://mondomaine.com/api/equipements/5",
  "equipement_details_indisponibles": true,
  "method": "opencv"
}
```

> Le scan reste un **succès** tant que le QR est reconnu ; seule la fiche manque
> (`equipement_details_indisponibles: true`) si Laravel est injoignable.

---

## 3. Schéma de réponse — ScanResponse

| Champ | Type | Description |
|---|---|---|
| `success` | bool | `true` = QR validé ; `false` = échec d'analyse |
| `id_equipement` | int? | ID extrait de l'URL (si succès) |
| `lien_equipement` | string? | URL brute décodée (si succès) |
| `equipement` | dict? | Fiche équipement renvoyée par Laravel (si disponibilité) |
| `equipement_details_indisponibles` | bool? | `true` si la fiche n'a pas pu être chargée (lien conservé) |
| `error` | string? | Message d'échec (format non reconnu, QR non détecté, équipement introuvable…) |
| `method` | string | Moteur ayant décodé : `"pyzbar"`, `"opencv"`, `"none"` |

---

## 4. Moteurs de décodage — pyzbar / OpenCV

Le décodeur tente les moteurs dans l'ordre, avec plusieurs **rotations** (0°/90°/180°/270°) et **mises à l'échelle** pour rattraper les photos floues ou mal cadrées (`OCR_DECODE_ATTEMPTS`, défaut `2`).

| Ordre | Moteur | Dépendance | Remarque |
|---|---|---|---|
| 1 | **pyzbar** | lib système `libzbar0` + `pyzbar` | Très tolérant sur les photos. Actif si la lib est présente. |
| 2 | **OpenCV** | `opencv-python` (dépendance du projet) | Fonctionne sans dépendance système. **Moteur effectif** si `libzbar0` absente. |

> `method` dans les réponses indique lequel des deux a réussi le décodage.

---

## 5. Exemples d'intégration Laravel

### Envoi d'une photo depuis un téléphone (formulaire Laravel)

```php
$response = Http::attach(
    'file',
    file_get_contents($request->file('photo')->getRealPath()),
    $request->file('photo')->getClientOriginalName()
)->post('http://127.0.0.1:8400/api/v1/qr/scan');

$body = $response->json();

if (($body['success'] ?? false) === true) {
    $id = $body['id_equipement'];               // à utiliser pour charger la fiche
} else {
    Log::warning('Scan QR échoué : '.($body['error'] ?? 'inconnu'));
}
```

---

## 6. Codes d'erreur

### Réponses métier (`success=false`, HTTP `200`)

| `error` | Description |
|---|---|
| `Aucun QR code détecté dans l'image` | La photo ne contient pas de QR lisible |
| `URL non reconnue` | Le QR encode autre chose qu'une URL `/api/equipements/{id}` (ou hôte non autorisé) — **anti-phishing** |
| `Équipement introuvable` | L'URL est valide mais Laravel renvoie **404** |
| `Fichier image invalide` | Le contenu n'est pas une image décodable |

### Codes protocole (HTTP ≠ 200)

| Code | Cause |
|---|---|
| `400` | Champ `file` manquant / fichier vide |
| `413` | Image trop volumineuse (> `OCR_MAX_IMAGE_BYTES`, 10 Mo) |
| `415` | Format non pris en charge (autre que JPEG/PNG/SVG/EPS) |

---

## 7. Configuration (.env)

| Variable | Défaut | Description |
|---|---|---|
| `OCR_HOST` / `OCR_PORT` | `127.0.0.1` / `8400` | Bind du service |
| `LARAVEL_API_URL` | *(vide)* | Base de l'API Laravel. Vide = pas d'enrichissement. |
| `LARAVEL_TIMEOUT_S` | `5` | Timeout de l'appel Laravel (s) |
| `QR_ALLOWED_HOSTS` | *(vide)* | Hôtes autorisés (virgule). Vide = tout hôte valide (chemin quand même exigé). |
| `OCR_MAX_IMAGE_BYTES` | `10485760` | Taille max de l'image (10 Mo) |
| `OCR_DECODE_ATTEMPTS` | `2` | Passes de mise à l'échelle du décodage |

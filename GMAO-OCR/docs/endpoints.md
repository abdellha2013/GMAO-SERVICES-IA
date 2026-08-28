# GMAO-OCR — Référence des endpoints API

Tous les endpoints sont préfixés par **`/api/v1`** (port par défaut **8400**).
Documentation interactive : `http://127.0.0.1:8400/docs`.
**Interface web de visualisation** (dashboard de test) : `http://127.0.0.1:8400/`.

## Interface web

`GET /` sert une page unique (sans build, HTML/CSS/JS vanilla). Elle permet de
**glisser-déposer une image** (SVG, PNG, EPS, JPEG), visualiser l'aperçu
original et le **PNG rasterisé** (travail de préprocessing des formats
vectoriels), puis **scanner le QR** en un clic via `/api/v1/qr/scan` et
afficher la réponse détaillée. Un bouton charge le QR SVG d'exemple du dépôt
racine.

## Formats pris en charge

| Format | Type MIME | Gestion |
|---|---|---|
| SVG | `image/svg+xml` | Rasterisé en PNG via **CairoSVG** avant décodage |
| PNG | `image/png` | Natif (Pillow/pyzbar/OpenCV) |
| EPS | `application/postscript` | Rasterisé via **Pillow + Ghostscript** |
| JPEG | `image/jpeg` | Natif |

EPS nécessite **Ghostscript** (`apt install ghostscript`) ; SVG nécessite
**CairoSVG** (dépendance du projet). La liste acceptée est configurable via
`OCR_ACCEPTED_CONTENT_TYPES`.

## Vue d'ensemble

| Méthode | Route | Description |
|---|---|---|
| POST | `/api/v1/qr/scan` | Décode un QR depuis une image (SVG/PNG/EPS/JPEG) → validation anti-phishing → id + fiche Laravel |
| GET | `/api/v1/healthz` | État du service + moteur de décodage actif + config Laravel |
| POST | `/api/v1/debug/raster` | Rasterise le fichier en PNG et renvoie l'aperçu (base64) + essai de décodage |
| GET | `/api/v1/debug/sample-svg` | QR SVG d'exemple du dépôt racine (test rapide) |
| GET | `/` | Interface web de visualisation (page HTML) |

---

## 1. `GET /api/v1/healthz`

```json
{
  "status": "ok",
  "service": "gmao-ocr",
  "version": "0.1.0",
  "decoder": "pyzbar",
  "laravel_configured": false
}
```

`decoder` = moteur effectif : `"pyzbar"` (si `libzbar0` présente), `"opencv"`
(fallback), sinon `"none"`.

---

## 2. `POST /api/v1/qr/scan`

Reçoit une image (multipart, champ `file`) de **SVG, PNG, EPS ou JPEG**
(≤ 10 Mo), décode le QR code, valide que son contenu est bien une URL de fiche
équipement au format `/api/equipements/{id}` (**anti-phishing**), en extrait
l'`id_equipement` et, si l'API Laravel est configurée, renvoie la fiche
détaillée.

```bash
curl -X POST http://127.0.0.1:8400/api/v1/qr/scan \
  -F "file=@qr_equipement.svg;type=image/svg+xml" \
  -H "Content-Type: multipart/form-data"
```

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
  "method": "pyzbar"
}
```

### Réponse `200 OK` — sans enrichissement (Laravel non configuré ou injoignable)

```json
{
  "success": true,
  "id_equipement": 5,
  "lien_equipement": "https://mondomaine.com/api/equipements/5",
  "equipement_details_indisponibles": true,
  "method": "pyzbar"
}
```

> Le scan reste un **succès** tant que le QR est reconnu ; seule la fiche
> manque (`equipement_details_indisponibles: true`) si Laravel est injoignable.
> Les **échecs d'analyse** sont des réponses métier **HTTP 200** avec
> `success=false` et un `error` explicite (voir « Codes d'erreur »).

### Schéma `ScanResponse`

| Champ | Type | Description |
|---|---|---|
| `success` | bool | `true` = QR validé ; `false` = échec d'analyse |
| `id_equipement` | int? | ID extrait de l'URL (si succès) |
| `lien_equipement` | string? | URL brute décodée (si succès) |
| `equipement` | dict? | Fiche équipement renvoyée par Laravel (si disponible) |
| `equipement_details_indisponibles` | bool? | `true` si la fiche n'a pas pu être chargée (lien conservé) |
| `error` | string? | Message d'échec (format non reconnu, QR non détecté, équipement introuvable…) |
| `method` | string | Moteur ayant décodé : `"pyzbar"`, `"opencv"`, `"none"` |

### Moteurs de décodage

| Ordre | Moteur | Dépendance | Remarque |
|---|---|---|---|
| 1 | **pyzbar** | lib système `libzbar0` + `pyzbar` | Très tolérant sur les photos ; fiable aussi sur le rendu des SVG rasterisés. |
| 2 | **OpenCV** | `opencv-python` (dépendance du projet) | Fallback sans dépendance système. |

Le décodeur réessaie sur plusieurs **rotations** (0°/90°/180°/270°) et
**mises à l'échelle** pour rattraper les photos floues ou mal cadrées
(`OCR_DECODE_ATTEMPTS`, défaut `2`).

---

## 3. `POST /api/v1/debug/raster`

Endpoint de **débogage/visualisation** : reçoit le même multipart que
`/qr/scan`, rasterise le fichier en PNG (notamment pour SVG/EPS) et renvoie
l'image en **base64** ainsi qu'un essai de décodage. Utilisé par l'interface
web.

```bash
curl -X POST http://127.0.0.1:8400/api/v1/debug/raster \
  -F "file=@qr_equipement.svg;type=image/svg+xml"
```

```json
{
  "source_format": "svg",
  "content_type": "image/svg+xml",
  "taille": { "largeur": 300, "hauteur": 300 },
  "png_base64": "iVBORw0KGgoAAAANSUhEUgA…",
  "decode_apercu": {
    "data": "http://localhost:8001/api/equipements/1",
    "method": "pyzbar",
    "attempts": 1
  },
  "decoders": { "pyzbar": true, "opencv": true }
}
```

| Champ | Type | Description |
|---|---|---|
| `source_format` | string | Format détecté : `svg`, `eps`, `png`, `jpg`, … |
| `content_type` | string | Type MIME effectif envoyé |
| `taille` | object | Largeur / hauteur du PNG produit |
| `png_base64` | string | Image PNG final encodée en base64 |
| `decode_apercu` | object | Essai de décodage direct (donnée, moteur, nb d'essais) |
| `decoders` | object | Disponibilité des moteurs pyzbar / OpenCV |

---

## 4. `GET /api/v1/debug/sample-svg`

Renvoie le QR SVG **d'exemple** situé à la racine du monorepo
(`qr_equipement.svg`) avec le type MIME `image/svg+xml` — permet de tester
rapidement le pipeline sans préparer de fichier.

```bash
curl http://127.0.0.1:8400/api/v1/debug/sample-svg
```

Réponse : le fichier SVG brut (en-tête `Content-Type: image/svg+xml`).
`404` si le fichier d'exemple n'existe pas.

---

## Codes d'erreur

### Réponses métier (`success=false`, HTTP `200`)

| `error` | Description |
|---|---|
| `Aucun QR code détecté dans l'image` | L'image ne contient pas de QR lisible |
| `URL non reconnue` | Le QR encode autre chose qu'une URL `/api/equipements/{id}` (ou hôte non autorisé) — **anti-phishing** |
| `Équipement introuvable` | URL valide mais Laravel renvoie **404** |
| `Fichier image invalide` | Contenu non décodable / format corrompu |
| `Format non pris en charge : …` | Type MIME hors liste acceptée |

### Codes protocole (HTTP ≠ 200)

| Code | Cause |
|---|---|
| `400` | Champ `file` manquant / fichier vide / image invalide |
| `413` | Image trop volumineuse (> `OCR_MAX_IMAGE_BYTES`, 10 Mo) |
| `415` | Format non pris en charge (hors JPEG/PNG/SVG/EPS) |
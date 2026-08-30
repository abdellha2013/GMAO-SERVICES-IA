# GMAO-OCR — Lecture de QR codes équipements par photo (vision OCR)

Sous-projet du monorepo `Gmao-Services-IA`. Nouveau microservice FastAPI
(port `:8400`) qui permet de **scanner un QR code à partir d'une photo**
(prise de vue simple avec un téléphone, sans scanner natif) pour retrouver
la fiche d'un équipement.

Le QR code collé sur chaque machine encode l'URL de sa fiche, ex.
`https://mondomaine.com/api/equipements/5`. Le service décode l'image,
**valide** le format de l'URL (anti-phishing : `/api/equipements/{id}`),
extrait l'`id_equipement` et, si l'API Laravel est joignable, renvoie la
fiche équipement détaillée.

## Formats pris en charge

| Format | Type MIME | Gestion |
|---|---|---|
| SVG | `image/svg+xml` | Rasterisé en PNG via **CairoSVG** avant décodage |
| PNG | `image/png` | Natif (Pillow/OpenCV/pyzbar) |
| EPS | `application/postscript` | Rasterisé via **Pillow + Ghostscript** |
| JPEG | `image/jpeg` | Natif |

La liste acceptée est configurable via `OCR_ACCEPTED_CONTENT_TYPES`.
EPS nécessite **Ghostscript** (`sudo apt-get install ghostscript`), SVG
nécessite **CairoSVG** (dépendance du projet).

## Interface web de visualisation

Une interface HTML/CSS/JS est servie par le service lui-même :
**`http://127.0.0.1:8400/`** (depuis la même machine) ou
**`http://<IP_LAN>:8400/`** (depuis une autre machine du réseau local). Elle
permet de :

- glisser-déposer / choisir un fichier SVG, PNG, EPS ou JPEG ;
- visualiser l'aperçu original et le **PNG rasterisé** (travail de
  préprocessing pour SVG/EPS) ;
- scanner le QR via `/api/v1/qr/scan` et afficher la réponse détaillée ;
- charger le QR SVG d'exemple du dépôt ;
- voir l'état du service (moteur de décodage actif, config Laravel).

## Endpoints

Voir [`docs/endpoints.md`](docs/endpoints.md). Résumé :

| Méthode | Route | Description |
|---|---|---|
| POST | `/api/v1/qr/scan` | Scanne un QR code depuis une image (multipart `file`) |
| GET | `/api/v1/healthz` | État du service + moteur de décodage actif |
| POST | `/api/v1/debug/raster` | Rasterise le fichier en PNG + aperçu de décodage (base64) |
| GET | `/api/v1/debug/sample-svg` | QR SVG d'exemple du dépôt racine |

Swagger interactif : `http://127.0.0.1:8400/docs`.

## Démarrage

```bash
# Installer le décodeur (voir ci-dessous pour les dépendances système)
uv sync

# Accès local (machine hôte uniquement)
uv run --env-file GMAO-OCR/.env uvicorn gmao_ocr.api.main:app --host 127.0.0.1 --port 8400

# Accès réseau local (accessible depuis les autres machines du réseau)
uv run --env-file GMAO-OCR/.env uvicorn gmao_ocr.api.main:app --host 0.0.0.0 --port 8400
```

Pour trouver l'IP locale de la machine : `hostname -I` (ex. `10.96.93.45`).
Les autres machines accèdent alors via `http://10.96.93.45:8400/`. Aucun
pare-feu à ouvrir si `ufw` est inactif.

Ensuite :

```bash
# Exemple d'appel
curl -X POST http://127.0.0.1:8400/api/v1/qr/scan \
  -F "file=@photo_qr.jpg" \
  -H "Content-Type: multipart/form-data"
```

## Décodage : pyzbar préféré, OpenCV en fallback

Deux moteurs de décodage sont supportés, essayés dans l'ordre :

1. **`pyzbar`** (préféré, très tolérant sur les photos) — nécessite la lib
   système **`libzbar0`** :
   ```bash
   sudo apt-get install -y libzbar0
   uv pip install "pyzbar>=0.1.9"     # ou uv pip install ".[pyzbar]"
   ```
2. **`OpenCV`** (`cv2.QRCodeDetector`) — fonctionne sans dépendance système
   (`opencv-python` est une dépendance du projet). C'est le moteur actif
   si `libzbar0`/`pyzbar` ne sont pas disponibles.

Le décodeur réessaie sur plusieurs **rotations** (0°/90°/180°/270°) et
**mises à l'échelle** pour rattraper les photos floues ou mal cadrées
(`OCR_DECODE_ATTEMPTS`, défaut `2`).

## Comportement

| Situation | Réponse |
|---|---|
| QR détecté, URL valide, Laravel dispo | `success=true` + `id_equipement`, `lien_equipement`, `equipement` |
| QR détecté mais Laravel injoignable/timeout | `success=true` + `equipement_details_indisponibles: true` (lien brut conservé) |
| Image sans QR / floue | `success=false`, `error: "Aucun QR code détecté dans l'image"` |
| URL non conforme au pattern | `success=false`, `error: "URL non reconnue"` (anti-phishing) |
| Équipement introuvable (404 Laravel) | `success=false`, `error: "Équipement introuvable"` |
| Format non pris en charge (hors JPEG/PNG/SVG/EPS) | HTTP `415` |
| Image trop volumineuse (>10 Mo) | HTTP `413` |

## Configuration (`.env`)

| Variable | Défaut | Description |
|---|---|---|
| `OCR_HOST` / `OCR_PORT` | `127.0.0.1` / `8400` | Bind du service |
| `LARAVEL_API_URL` | *(vide)* | Base de l'API Laravel, ex. `https://mondomaine.com`. Vide = pas d'enrichissement. |
| `LARAVEL_TIMEOUT_S` | `5` | Timeout de l'appel Laravel (s) |
| `QR_ALLOWED_HOSTS` | *(vide)* | Hôtes autorisés pour l'URL du QR (virgule). Vide = tout hôte avec le bon chemin. |
| `OCR_MAX_IMAGE_BYTES` | `10485760` (10 Mo) | Taille max du fichier image |
| `OCR_DECODE_ATTEMPTS` | `2` | Nombre de passes de mise à l'échelle |
| `OCR_ACCEPTED_CONTENT_TYPES` | `image/jpeg,image/png,image/svg+xml,application/postscript` | Types MIME acceptés (virgule) |

## Structure

```
gmao_ocr/
├── config.py              # settings env (.env du sous-projet)
├── qr/decoder.py          # décodage QR (pyzbar → OpenCV), préprocessing SVG/EPS→PNG
├── qr/validation.py       # validation anti-phishing de l'URL + extraction id
├── models/schemas.py      # schémas Pydantic (ScanResponse, HealthResponse)
├── services/
│   ├── ocr_service.py     # orchestration scan (décodage → validation → enrichissement)
│   └── equipement_client.py  # client HTTP tolérant vers l'API Laravel
└── api/                   # FastAPI (create_app) + routes /api/v1/*
static/                    # interface web de visualisation (HTML/CSS/JS)
docs/endpoints.md          # référence détaillée des endpoints
```

## Tests

```bash
uv run pytest GMAO-OCR -q
```

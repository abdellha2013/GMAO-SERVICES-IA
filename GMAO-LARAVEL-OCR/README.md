# GMAO-LARAVEL-OCR — intégration Laravel ⇄ GMAO-OCR

Code Laravel à copier dans votre backend pour brancher le service OCR.

Machine OCR : `http://10.96.93.45:8400` · Endpoint scan : `POST /api/v1/qr/scan` (multipart `file`)

## Copier vers votre app Laravel

| Fichier ici                    | Destination dans votre app      |
|--------------------------------|----------------------------------|
| `config/ocr.php`               | `config/ocr.php`                |
| `app/Services/OcrClient.php`   | `app/Services/OcrClient.php`    |
| `app/.../OcrController.php`    | `app/Http/Controllers/Api/OcrController.php` |
| `app/.../EquipementController.php` | `app/Http/Controllers/Api/EquipementController.php` |

## Ajouter au `.env` Laravel

```dotenv
OCR_BASE_URL=http://10.96.93.45:8400
OCR_SCAN_ENDPOINT=/api/v1/qr/scan
OCR_TIMEOUT_S=10
OCR_RETRIES=1
```

## Ajouter aux routes (`routes/api.php`)

```php
use App\Http\Controllers\Api\OcrController;
use App\Http\Controllers\Api\EquipementController;

// Front Laravel → OCR (photographie d'un QR)
Route::post('ocr/scan', [OcrController::class, 'scan']);

// OCR → Laravel (fiche équipement enrichie)
Route::get('equipements/{equipement}', [EquipementController::class, 'show']);
```

## Après copie

```bash
php artisan config:cache
php artisan route:list
```

## Rappel OCR (machine 10.96.93.45)

- `QR_ALLOWED_HOSTS=10.96.93.203` dans `GMAO-OCR/.env` : seuls les QRs
  pointant vers le backend Laravel sont acceptés.
- `LARAVEL_API_URL=http://10.96.93.203:8001` : URL que l'OCR appelle pour
  la fiche.
- Le scan complet : `curl -X POST http://10.96.93.45:8400/api/v1/qr/scan -F "file=@photo.jpg"`
  → `success=true` + `id_equipement` + `equipement` (fiche enrichie).

## Fiche réponse du scan (`success=true`)

```json
{
  "success": true,
  "id_equipement": 5,
  "lien_equipement": "/api/equipements/5",
  "equipement": { "... fiche JSON depuis le backend ..." }
}
```

Cas backend injoignable : `success` reste `true` avec
`equipement_details_indisponibles: true` et `lien_equipement` brut conservé.
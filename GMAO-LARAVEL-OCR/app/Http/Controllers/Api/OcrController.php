<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\OcrClient;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Validator;

class OcrController extends Controller
{
    public function __construct(private readonly OcrClient $ocr) {}

    /**
     * POST /api/ocr/scan — reçoit la photo, renvoie la fiche équipement.
     */
    public function scan(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            // Limite < 10 Mo (OCR_MAX_IMAGE_BYTES côté GMAO-OCR).
            'file' => ['required', 'file', 'mimes:jpeg,jpg,png,svg', 'max:10240'],
        ]);

        if ($validator->fails()) {
            return response()->json([
                'success' => false,
                'error'   => $validator->errors()->first('file'),
            ], 422);
        }

        try {
            $result = $this->ocr->scanUploadedFile($request->file('file'));

            return response()->json($result);
        } catch (\RuntimeException $e) {
            return response()->json([
                'success' => false,
                'error'   => $e->getMessage(),
            ], 503);
        }
    }
}
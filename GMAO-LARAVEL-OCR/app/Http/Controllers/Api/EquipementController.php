<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Equipement;
use Illuminate\Http\JsonResponse;

class EquipementController extends Controller
{
    /**
     * GET /api/equipements/{id} — fiche exposée à GMAO-OCR.
     *
     * C'est l'endpoint que GMAO-OCR appelle (variable LARAVEL_API_URL)
     * pour enrichir la réponse de scan avec la fiche équipement.
     *
     * @return JsonResponse JSON de l'équipement, ou 404 si introuvable.
     */
    public function show(int $id): JsonResponse
    {
        // ⚠️ Adapter la requête à VOTRE schéma de base GMAO.
        $equipement = Equipement::find($id);

        if (! $equipement) {
            return response()->json(['message' => 'Équipement introuvable.'], 404);
        }

        return response()->json($equipement);
    }
}
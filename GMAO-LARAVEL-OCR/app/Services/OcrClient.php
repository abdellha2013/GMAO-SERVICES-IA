<?php

namespace App\Services;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class OcrClient
{
    public function __construct(
        private readonly string $baseUrl,
        private readonly string $endpoint,
        private readonly int $timeout,
        private readonly int $retries,
    ) {}

    public static function fromConfig(): self
    {
        return new self(
            baseUrl: config('ocr.base_url', 'http://10.96.93.45:8400'),
            endpoint: config('ocr.scan_endpoint', '/api/v1/qr/scan'),
            timeout: (int) config('ocr.timeout', 10),
            retries: (int) config('ocr.retries', 1),
        );
    }

    /**
     * Décode un QR code équipement depuis le contenu binaire d'une photo.
     *
     * @param  mixed  $image      Contenu binaire de l'image (string ou resource).
     * @param  string $filename   Nom du fichier transmis à l'OCR (ex. "photo.jpg").
     * @return array{
     *     success: bool,
     *     id_equipement?: int,
     *     lien_equipement?: string,
     *     equipement?: array,
     *     equipement_details_indisponibles?: bool,
     *     error?: string,
     * }
     *
     * @throws \RuntimeException si l'OCR est injoignable après toutes les tentatives.
     */
    public function scan(mixed $image, string $filename): array
    {
        $attempts = max(1, $this->retries + 1);

        for ($i = 1; $i <= $attempts; $i++) {
            try {
                $response = Http::timeout($this->timeout)
                    ->attach('file', $image, $filename)
                    ->acceptJson()
                    ->post($this->baseUrl . $this->endpoint);

                if ($response->ok()) {
                    return $response->json();
                }

                Log::warning('GMAO-OCR : HTTP ' . $response->status() . ' sur ' . $this->endpoint, [
                    'body' => $response->body(),
                ]);
            } catch (ConnectionException $e) {
                Log::warning("GMAO-OCR injoignable (tentative {$i}/{$attempts}) : " . $e->getMessage());
            }
        }

        throw new \RuntimeException('Service OCR indisponible.');
    }

    /** Variante : scan depuis un UploadedFile Laravel. */
    public function scanUploadedFile(\Illuminate\Http\UploadedFile $file): array
    {
        return $this->scan($file->getContent(), $file->getClientOriginalName());
    }
}
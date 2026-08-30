<?php

return [

    'base_url' => rtrim(env('OCR_BASE_URL', 'http://10.96.93.45:8400'), '/'),

    'scan_endpoint' => env('OCR_SCAN_ENDPOINT', '/api/v1/qr/scan'),

    'timeout' => (int) env('OCR_TIMEOUT_S', 10),

    'retries' => (int) env('OCR_RETRIES', 1),

];
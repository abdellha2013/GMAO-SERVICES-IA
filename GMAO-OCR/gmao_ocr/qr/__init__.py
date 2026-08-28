"""Paquet de décodage QR par vision (pyzbar préféré, OpenCV en fallback)."""

from gmao_ocr.qr.decoder import QrDecodeResult, decode_qr_from_bytes

__all__ = ["QrDecodeResult", "decode_qr_from_bytes"]

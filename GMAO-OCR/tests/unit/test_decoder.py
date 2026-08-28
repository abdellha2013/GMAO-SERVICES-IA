"""Tests du décodeur QR (pyzbar si dispo, sinon OpenCV)."""

from __future__ import annotations

import pytest

from gmao_ocr.qr.decoder import HAVE_CV2, decode_qr_from_bytes

EXPECTED = "https://mondomaine.com/api/equipements/5"

# QR SVG réel du dépôt : encode ce contenu précis.
EXPECTED_SVG = "http://localhost:8001/api/equipements/1"


@pytest.mark.skipif(not HAVE_CV2, reason="OpenCV (moteur effectif) non disponible")
def test_decode_valid_png(qr_png: bytes):
    res = decode_qr_from_bytes(qr_png)
    assert res.data == EXPECTED
    assert res.method in ("opencv", "pyzbar")
    assert res.attempts >= 1


@pytest.mark.skipif(not HAVE_CV2, reason="OpenCV (moteur effectif) non disponible")
def test_decode_rotated_png(qr_rotated_png: bytes):
    res = decode_qr_from_bytes(qr_rotated_png)
    assert res.data == EXPECTED
    assert res.method in ("opencv", "pyzbar")


@pytest.mark.skipif(not HAVE_CV2, reason="OpenCV (moteur effectif) non disponible")
def test_decode_svg(qr_svg: bytes):
    res = decode_qr_from_bytes(qr_svg, content_type="image/svg+xml")
    assert res.data == EXPECTED_SVG
    assert res.method in ("opencv", "pyzbar")


@pytest.mark.skipif(not HAVE_CV2, reason="OpenCV (moteur effectif) non disponible")
def test_decode_svg_autodetected(qr_svg: bytes):
    res = decode_qr_from_bytes(qr_svg)
    assert res.data == EXPECTED_SVG
    assert res.method in ("opencv", "pyzbar")


@pytest.mark.skipif(not HAVE_CV2, reason="OpenCV (moteur effectif) non disponible")
def test_decode_eps(qr_eps: bytes):
    res = decode_qr_from_bytes(qr_eps, content_type="application/postscript")
    assert res.data == EXPECTED
    assert res.method in ("opencv", "pyzbar")


def test_render_to_png_svg(qr_svg: bytes):
    from gmao_ocr.qr.decoder import render_to_png_bytes

    png, source, size = render_to_png_bytes(qr_svg, "image/svg+xml")
    assert png.startswith(b"\x89PNG")
    assert source == "svg"
    assert size[0] > 0 and size[1] > 0


def test_render_to_png_eps(qr_eps: bytes):
    from gmao_ocr.qr.decoder import render_to_png_bytes

    png, source, size = render_to_png_bytes(qr_eps, "application/postscript")
    assert png.startswith(b"\x89PNG")
    assert source == "eps"
    assert size[0] > 0 and size[1] > 0


def test_decode_no_qr_returns_none():
    import numpy as np
    from PIL import Image
    import io

    img = Image.fromarray(np.zeros((200, 200, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    res = decode_qr_from_bytes(buf.getvalue())
    assert res.data is None


def test_decode_invalid_image_raises():
    with pytest.raises(ValueError):
        decode_qr_from_bytes(b"not-an-image-at-all")

"""Moteur de décodage QR par photographie.

Stratégie :
1. ``pyzbar`` (préféré) s'il est installé — nécessite la lib système
   ``libzbar0``. Depuis une photo, il est souvent plus tolérant.
2. ``OpenCV`` (`cv2.QRCodeDetector`) en fallback — fonctionne sans dépendance
   système.

Pour gérer les photos floues / mal cadrées / légèrement inclinées, le
décodeur réessaie sur plusieurs rotations et mises à l'échelle.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

try:
    import cairosvg

    _HAVE_CAIROSVG = True
except Exception:
    cairosvg = None
    _HAVE_CAIROSVG = False

logger = logging.getLogger("gmao_ocr.decoder")

try:  # pyzbar est optionnel (nécessite libzbar0 système)
    from pyzbar.pyzbar import decode as _pyzbar_decode

    _HAVE_PYZBAR = True
except Exception:  # pragma: no cover - dépend du système
    _pyzbar_decode = None
    _HAVE_PYZBAR = False

try:
    import cv2

    _HAVE_CV2 = True
except Exception:  # pragma: no cover
    cv2 = None
    _HAVE_CV2 = False

__all__ = ["QrDecodeResult", "decode_qr_from_bytes", "HAVE_PYZBAR", "HAVE_CV2"]

HAVE_PYZBAR = _HAVE_PYZBAR
HAVE_CV2 = _HAVE_CV2

def render_to_png_bytes(
    image_bytes: bytes,
    content_type: str | None = None,
) -> tuple[bytes, str, tuple[int, int]]:
    """Convertit n'importe quel format accepté en bytes PNG (aperçu/débogage).

    Returns
    -------
    (png_bytes, source_format, (largeur, hauteur))
        - ``png_bytes`` : image finale en PNG.
        - ``source_format`` : format d'entrée détecté ("svg", "eps", "png", ...).
        - dimensions de l'image PNG produite.
    """

    ct = (content_type or "").lower().strip()
    looks_svg = b"<svg" in image_bytes.lstrip()[:512]

    if ct in ("application/postscript", "image/x-eps", "image/eps"):
        source = "eps"
    elif ct == "image/svg+xml" or looks_svg:
        source = "svg"
    elif ct in ("image/jpeg", "image/jpg"):
        source = "jpg"
    elif ct == "image/png":
        source = "png"
    else:
        source = ct or "inconnu"

    try:
        preprocessed = _preprocess_image_bytes(image_bytes, content_type)
        img = Image.open(io.BytesIO(preprocessed))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        raise ValueError("Fichier image invalide") from exc

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), source, img.size


# Rotation étudiées (degrés) pour rattraper une photo inclinée.
_ROTATIONS = (0, 90, 180, 270)

# Mapping content-type → bytes préprocessés en PNG.
_CONTENT_TYPE_PREPROCESSORS: dict[str, str] = {
    "image/svg+xml": "svg",
    "application/postscript": "eps",
    "image/x-eps": "eps",
    "image/eps": "eps",
}


def _preprocess_image_bytes(
    image_bytes: bytes,
    content_type: str | None = None,
) -> bytes:
    """Convertit les formats non-natifs (SVG, EPS) en bytes PNG.

    Pour SVG : utilise cairosvg pour rasteriser en PNG.
    Pour EPS : utilise Pillow (via Ghostscript) pour convertir en PNG.
    Pour JPEG/PNG : retourne les bytes tels quels.
    """

    ct = (content_type or "").lower().strip()

    # Détection autonome d'un SVG (déclaration XML ou doctype possibles).
    looks_svg = b"<svg" in image_bytes.lstrip()[:512]

    # SVG → PNG via cairosvg
    if ct == "image/svg+xml" or (not ct and looks_svg):
        if not _HAVE_CAIROSVG:
            raise ValueError(
                "Traitement SVG impossible : cairosvg n'est pas installé"
            )
        try:
            png_bytes = cairosvg.svg2png(bytestring=image_bytes, dpi=300)
        except Exception as exc:
            raise ValueError(f"SVG invalide : {exc}") from exc
        logger.debug("SVG rasterisé en PNG (%d octets)", len(png_bytes))
        return png_bytes

    # EPS → PNG via Pillow + Ghostscript
    if ct in ("application/postscript", "image/x-eps", "image/eps"):
        try:
            eps_img = Image.open(io.BytesIO(image_bytes))
            eps_img = eps_img.convert("RGB")
            buf = io.BytesIO()
            eps_img.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            logger.debug("EPS rasterisé en PNG (%d octets)", len(png_bytes))
            return png_bytes
        except Exception as exc:
            raise ValueError(
                f"Traitement EPS impossible (Ghostscript requis) : {exc}"
            ) from exc

    # JPEG, PNG, etc. → pas de conversion
    return image_bytes


@dataclass(frozen=True)
class QrDecodeResult:
    """Résultat d'un décodage QR."""

    data: str | None
    method: str  # "pyzbar" | "opencv" | "none"
    attempts: int


def decode_qr_from_bytes(
    image_bytes: bytes,
    attempts: int = 2,
    content_type: str | None = None,
) -> QrDecodeResult:
    """Décode un QR à partir du contenu brut d'une image.

    Charge l'image avec Pillow (validation/sanitisation du format), puis
    tente le décodage via ``pyzbar`` puis ``OpenCV``, avec plusieurs
    rotations et mises à l'échelle.

    Parameters
    ----------
    image_bytes:
        Contenu brut du fichier image (JPEG/PNG/SVG/EPS).
    attempts:
        Nombre de passes de mise à l'échelle (1 = taille d'origine).
    content_type:
        Type MIME du fichier (optionnel, améliore la détection du format).

    Returns
    -------
    QrDecodeResult
        Donnée brute lue (``None`` si rien), moteur utilisé et nb d'essais.
    """

    if not HAVE_CV2 and not HAVE_PYZBAR:  # pragma: no cover
        raise RuntimeError("Aucun décodeur QR disponible (pyzbar ni OpenCV).")

    # Préprocessing : conversion SVG/EPS → PNG si nécessaire
    try:
        image_bytes = _preprocess_image_bytes(image_bytes, content_type)
    except ValueError:
        raise

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        logger.warning("Image illisible : %s", exc)
        raise ValueError("Fichier image invalide") from exc

    nb_attempts = 0

    # 1) pyzbar (décode directement sur l'image PIL, très tolérant)
    if HAVE_PYZBAR:
        for rotation in _ROTATIONS:
            candidate = img.rotate(rotation, expand=True)
            nb_attempts += 1
            data = _decode_pyzbar(candidate)
            if data is not None:
                return QrDecodeResult(data=data, method="pyzbar", attempts=nb_attempts)

    # 2) OpenCV en fallback
    if HAVE_CV2:
        base = np.array(img)  # RGB
        for scale in (1.0,) + tuple(0.5**i for i in range(1, attempts)):
            for rotation in _ROTATIONS:
                nb_attempts += 1
                work = _cv_rotated(base, rotation, scale)
                try:
                    data = _decode_opencv(work)
                except Exception as exc:  # pragma: no cover - dépend du build
                    logger.debug("Échec OpenCV (rot=%s, scale=%s) : %s", rotation, scale, exc)
                    continue
                if data is not None:
                    return QrDecodeResult(data=data, method="opencv", attempts=nb_attempts)

    return QrDecodeResult(data=None, method="none", attempts=nb_attempts)


def _decode_pyzbar(pil_image: Image.Image) -> str | None:
    """Décode un QR avec pyzbar depuis une image PIL."""

    try:
        results = _pyzbar_decode(pil_image)
    except Exception as exc:  # pragma: no cover
        logger.debug("pyzbar a échoué : %s", exc)
        return None
    for result in results:
        if result.type == "QRCODE":
            value = result.data
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            return str(value)
    return None


def _decode_opencv(numpy_bgr: np.ndarray) -> str | None:
    """Décode un QR avec OpenCV depuis une image BGR (numpy)."""

    detector = cv2.QRCodeDetector()
    data, _points, _straight = detector.detectAndDecode(numpy_bgr)
    data = (data or "").strip()
    return data or None


def _cv_rotated(rgb: np.ndarray, rotation: int, scale: float) -> np.ndarray:
    """Applique une rotation (et éventuellement une réduction) à une image.

    OpenCV travaille en BGR ; retourne donc l'image convertie.
    """

    image = rgb
    if scale != 1.0:
        h, w = image.shape[:2]
        image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))))

    if rotation and cv2 is not None:
        if rotation == 90:
            image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 180:
            image = cv2.rotate(image, cv2.ROTATE_180)
        elif rotation == 270:
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

    if cv2 is not None and image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


__all__ = ["QrDecodeResult", "decode_qr_from_bytes", "HAVE_PYZBAR", "HAVE_CV2"]

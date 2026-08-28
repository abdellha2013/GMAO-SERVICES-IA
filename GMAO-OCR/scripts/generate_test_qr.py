"""Génère des images QR de test pour valider GMAO-OCR.

Usage :
    uv run python GMAO-OCR/scripts/generate_test_qr.py [url] [-o sortie.png]

Défauts : génère un QR valide (https://mondomaine.com/api/equipements/5)
et un QR de contrôle incliné pour tester la robustesse.

Le ``box_size`` élevé (px par module) reproduit la résolution d'un vrai
QR imprimé photographié avec un téléphone, lisible par le décodeur OpenCV.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
import qrcode

DEFAULT_URL = "https://mondomaine.com/api/equipements/5"
BOX_SIZE = 12


def make_qr_png(url: str, box_size: int = BOX_SIZE) -> Image.Image:
    qr = qrcode.QRCode(version=None, box_size=box_size,
                       border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère des images QR de test GMAO-OCR.")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="URL à encoder.")
    parser.add_argument("-o", "--output", default="GMAO-OCR/tests/assets/qr_test.png",
                        help="Chemin de sortie PNG.")
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    make_qr_png(args.url).save(out)
    print(f"QR écrit : {out} ({out.stat().st_size} octets)")

    # Test de robustesse : rotation de 90° (le décodeur doit s'en sortir)
    rot = make_qr_png(args.url).rotate(90, expand=True)
    rot_path = out.with_name(out.stem + "_rotated.png")
    rot.save(rot_path)
    print(f"QR incliné (90°) : {rot_path}")


if __name__ == "__main__":
    main()

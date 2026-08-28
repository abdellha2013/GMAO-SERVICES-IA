"""GMAO-OCR — lecture de QR codes sur les équipements par photo (vision OCR).

Service FastAPI autonome du monorepo ``Gmao-Services-IA``. Décodage QR via
``pyzbar`` (préféré) ou ``OpenCV`` (fallback), validation du format d'URL
attendue (``/api/equipements/{id}``) et enrichissement optionnel via l'API
Laravel.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]

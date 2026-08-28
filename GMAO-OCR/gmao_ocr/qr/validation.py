"""Validation anti-phishing de l'URL encodée dans un QR code.

Le QR code d'un équipement encode l'URL de sa fiche, attendue au format
``https://<hote>/api/equipements/{id}``. Pour éviter qu'un QR arbitraire
(ou frauduleux) soit accepté, on vérifie à la fois :

- le format du chemin ``/api/equipements/{id}`` (id numérique) ;
- le domaine, si une liste d'hôtes autorisés est configurée.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

__all__ = ["validate_qr_url", "EQUIPEMENT_URL_RE", "extract_id_from_url"]

# /api/equipements/{id} — id numérique, slash final optionnel.
EQUIPEMENT_URL_RE = re.compile(r"^https?://(?P<host>[^/\s]+)/api/equipements/(?P<id>\d+)/?$")


def extract_id_from_url(raw: str) -> int | None:
    """Extrait l'``id_equipement`` si le chemin correspond, sinon ``None``."""

    match = EQUIPEMENT_URL_RE.match(raw.strip())
    if not match:
        return None
    try:
        return int(match.group("id"))
    except ValueError:
        return None


def host_matches_allowed(url: str, allowed_hosts: list[str]) -> bool:
    """Vérifie que le domaine de l'URL figure dans la liste autorisée.

    Sans hôte(s) autorisé(s) configuré(s), retourne toujours ``True``
    (seul le format du chemin est alors contrôlé).
    """

    if not allowed_hosts:
        return True
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return any(host == a.lower() or host.endswith("." + a.lower()) for a in allowed_hosts)


def validate_qr_url(raw: str, allowed_hosts: list[str] | None = None) -> int | None:
    """Valide l'URL d'un QR équipement.

    Parameters
    ----------
    raw:
        Donnée brute décodée du QR (normalement une URL).
    allowed_hosts:
        Hôtes autorisés (optionnel). Vide → tout domaine valide accepté.

    Returns
    -------
    int | None
        ``id_equipement`` si l'URL est conforme, sinon ``None``.
    """

    if not raw or not isinstance(raw, str):
        return None
    equipement_id = extract_id_from_url(raw)
    if equipement_id is None:
        return None
    if not host_matches_allowed(raw, allowed_hosts or []):
        return None
    return equipement_id

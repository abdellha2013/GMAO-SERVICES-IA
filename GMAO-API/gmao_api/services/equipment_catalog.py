"""Catalogue statique des équipements (copie de la table ``equipements``).

Source : GMAO-ML/db/user&demende_intervention.sql — 12 équipements de test.
Sert à enrichir les demandes d'intervention (nom, localisation, criticité)
sans interroger la base Laravel : GMAO-API n'accède jamais directement au SGBD.
"""

from __future__ import annotations

from typing import Any

EQUIPEMENTS: list[dict[str, Any]] = [
    {
        "id_equipement": 1,
        "nom_equipement": "Compresseur industriel",
        "marque": "Atlas Copco",
        "modele": "GA 75",
        "numero_serie": "AC-GA75-001",
        "etat": "fonctionnel",
        "criticite": "elevee",
        "localisation": "Atelier A - Zone 1",
    },
    {
        "id_equipement": 2,
        "nom_equipement": "Pompe hydraulique",
        "marque": "Bosch Rexroth",
        "modele": "A10VSO",
        "numero_serie": "BR-A10VSO-002",
        "etat": "fonctionnel",
        "criticite": "critique",
        "localisation": "Atelier A - Zone 2",
    },
    {
        "id_equipement": 3,
        "nom_equipement": "Moteur électrique",
        "marque": "Siemens",
        "modele": "1LE1001",
        "numero_serie": "SI-1LE1001-003",
        "etat": "fonctionnel",
        "criticite": "moyenne",
        "localisation": "Ligne de production 1",
    },
    {
        "id_equipement": 4,
        "nom_equipement": "Convoyeur industriel",
        "marque": "SEW-Eurodrive",
        "modele": "DRN",
        "numero_serie": "SEW-DRN-004",
        "etat": "maintenance",
        "criticite": "elevee",
        "localisation": "Ligne de production 1",
    },
    {
        "id_equipement": 5,
        "nom_equipement": "Tour CNC",
        "marque": "Mazak",
        "modele": "QT-200",
        "numero_serie": "MZ-QT200-005",
        "etat": "fonctionnel",
        "criticite": "critique",
        "localisation": "Atelier d'usinage",
    },
    {
        "id_equipement": 6,
        "nom_equipement": "Fraiseuse CNC",
        "marque": "Haas",
        "modele": "VF-2",
        "numero_serie": "HA-VF2-006",
        "etat": "fonctionnel",
        "criticite": "elevee",
        "localisation": "Atelier d'usinage",
    },
    {
        "id_equipement": 7,
        "nom_equipement": "Chaudière industrielle",
        "marque": "Bosch",
        "modele": "Uni 3000",
        "numero_serie": "BO-UNI3000-007",
        "etat": "fonctionnel",
        "criticite": "critique",
        "localisation": "Salle énergétique",
    },
    {
        "id_equipement": 8,
        "nom_equipement": "Ventilateur industriel",
        "marque": "ABB",
        "modele": "ACH580",
        "numero_serie": "ABB-ACH580-008",
        "etat": "en_panne",
        "criticite": "moyenne",
        "localisation": "Atelier B - Zone 1",
    },
    {
        "id_equipement": 9,
        "nom_equipement": "Groupe électrogène",
        "marque": "Caterpillar",
        "modele": "C18",
        "numero_serie": "CAT-C18-009",
        "etat": "fonctionnel",
        "criticite": "critique",
        "localisation": "Local énergie",
    },
    {
        "id_equipement": 10,
        "nom_equipement": "Robot industriel",
        "marque": "ABB",
        "modele": "IRB 2600",
        "numero_serie": "ABB-IRB2600-010",
        "etat": "fonctionnel",
        "criticite": "critique",
        "localisation": "Ligne robotisée",
    },
    {
        "id_equipement": 11,
        "nom_equipement": "Machine de soudage",
        "marque": "Fronius",
        "modele": "TPS 500i",
        "numero_serie": "FR-TPS500I-011",
        "etat": "fonctionnel",
        "criticite": "elevee",
        "localisation": "Atelier soudage",
    },
    {
        "id_equipement": 12,
        "nom_equipement": "Presse hydraulique",
        "marque": "Schuler",
        "modele": "HP 500",
        "numero_serie": "SC-HP500-012",
        "etat": "hors_service",
        "criticite": "critique",
        "localisation": "Atelier B - Zone 3",
    },
]

_BY_ID: dict[int, dict[str, Any]] = {eq["id_equipement"]: eq for eq in EQUIPEMENTS}

CRITICITES_VALIDES = {"faible", "moyenne", "elevee", "critique"}


def get_equipement(id_equipement: int) -> dict[str, Any] | None:
    """Retourne l'équipement du catalogue, ou None si ID inconnu."""

    return _BY_ID.get(int(id_equipement))


def equipment_ids() -> list[int]:
    """IDs valides (colonne ``equipements.id_equipement``)."""

    return sorted(_BY_ID)


def describe(id_equipement: int) -> str:
    """« Tour CNC (#5) » — fallback « Équipement #<id> » si inconnu."""

    eq = get_equipement(id_equipement)
    if eq is None:
        return f"Équipement #{id_equipement}"
    return f"{eq['nom_equipement']} (#{id_equipement})"


__all__ = [
    "EQUIPEMENTS",
    "CRITICITES_VALIDES",
    "get_equipement",
    "equipment_ids",
    "describe",
]

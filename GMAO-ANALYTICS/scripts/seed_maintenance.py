"""Seed des données de maintenance de test (GMAO-ANALYTICS).

Peuple les tables de maintenance MySQL (vides par défaut dans le schéma
de référence) avec un historique réaliste sur ~12 mois pour les 12
équipements : pannes, ordres de travail terminés et demandes
d'intervention liées.

Ordre d'insertion respecté pour les FK :
    demande_interventions → ordre_travails → pannes

Usage :
    uv run python GMAO-ANALYTICS/scripts/seed_maintenance.py
    # ou avec une URL précise :
    uv run python GMAO-ANALYTICS/scripts/seed_maintenance.py \
        --db "mysql+pymysql://root:pass@127.0.0.1:3306/gmao_rag" \
        --months 12 --seed 7 --reset
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

import pymysql

# Profil de fiabilité par équipement (nb de pannes ≈ sur 12 mois).
# À chaque panne correspond ~1 OT terminé + 1 demande d'intervention.
EQUIP_PROFILE: dict[int, int] = {
    1: 4,   # Compresseur
    2: 5,   # Pompe hydraulique
    3: 3,   # Moteur électrique
    4: 4,   # Convoyeur
    5: 6,   # Tour CNC
    6: 5,   # Fraiseuse CNC
    7: 3,   # Chaudière
    8: 7,   # Ventilateur
    9: 2,   # Groupe électrogène
    10: 4,  # Robot
    11: 3,  # Soudage
    12: 6,  # Presse hydraulique
}

GRAVITES = ["faible", "moyenne", "grave", "critique"]
PRIORITES = ["faible", "moyenne", "elevee", "critique"]
TITRES = [
    "Défaillance capteur",
    "Usure mécanique",
    "Surchauffe anormale",
    "Bruit excessif",
    "Perte de pression",
    "Défaut électrique",
    "Vibration anormale",
    "Fuite hydraulique",
]


def _assert_no_literal_percent(table: str, row: tuple) -> None:
    """Signal clairement toute valeur contenant un ``%`` littéral.

    pymysql (style pyformat ``%s``) applique ``query % args`` : un ``%``
    littéral dans une valeur de chaîne provoque une erreur de formatage
    obscure. Mieux vaut l'identifier que de le laisser échouer.
    """

    offenders = [
        (i, repr(value)) for i, value in enumerate(row)
        if isinstance(value, str) and "%" in value
    ]
    if offenders:
        raise ValueError(
            f"[{table}] Valeur(s) contenant un '%' littéral (à échapper) : {offenders}"
        )


def _insert_one(cur, table: str, columns: list[str], row: tuple) -> int:
    """Insère une ligne et retourne son ``id`` réel (``cursor.lastrowid``).

    Retourner l'ID réel est indispensable pour l'intégrité référentielle :
    l'``auto_increment`` MySQL peut différer des compteurs locaux, en
    particulier si la table conserve un historique avant le ``reset``.
    """

    _assert_no_literal_percent(table, row)
    if len(row) != len(columns):
        raise ValueError(
            f"[{table}] Cardinalité : {len(columns)} colonne(s) mais "
            f"{len(row)} valeur(s) → {row!r}"
        )
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    cur.execute(sql, row)
    if cur.lastrowid is None:
        raise ValueError(f"[{table}] Aucun id retourné (table sans auto_increment ?)")
    return int(cur.lastrowid)


def build_equipment_dates(
    equipement_id: int,
    months: int,
    rng: random.Random,
) -> list[datetime]:
    """Dates de détection de pannes réparties sur la période (triées)."""

    n = EQUIP_PROFILE.get(equipement_id, 3)
    end = datetime.now()
    start = end - timedelta(days=months * 30)
    span = (end - start).total_seconds()
    # Séquences espacées (type dérive) : on choisit des instants croissants.
    days = sorted(rng.uniform(0, months * 30 - 2) for _ in range(n))
    return [start + timedelta(days=d) for d in days]


def seed(conn, months: int = 12, seed: int = 7, reset: bool = True) -> dict[str, int]:
    """Effectue le remplissage ; retourne un décompte des lignes insérées."""

    rng = random.Random(seed)
    global_ot_id = 0
    nb_demandes = 0
    nb_ot = 0
    nb_pannes = 0

    with conn.cursor() as cur:
        if reset:
            cur.execute("DELETE FROM pannes")
            cur.execute("DELETE FROM ordre_travails")
            cur.execute("DELETE FROM demande_interventions")

        di_columns = ["titre", "description", "priorite", "statut", "date_creation",
                      "date_validation", "id_equipement", "id_utilisateur"]
        ot_columns = ["titre", "description", "priorite", "statut", "date_planifiee",
                      "date_debut", "date_fin", "temps_reel", "commentaire_cloture",
                      "id_demande", "id_equipement"]
        panne_columns = ["titre", "description", "gravite", "date_detection", "cause",
                         "solution", "symptomes", "id_equipement", "id_ot"]

        # On utilise les IDs réels (auto_increment) retournés par MySQL pour
        # garantir les FK, plutôt que des compteurs locaux arbitraires.
        for eq_id, _count in EQUIP_PROFILE.items():
            dates = build_equipment_dates(eq_id, months, rng)
            for panne_date in reversed(dates):  # pannes ancienne → récente
                titre = rng.choice(TITRES)

                # 1. Demande d'intervention → id_demande réel
                id_demande = _insert_one(cur, "demande_interventions", di_columns, (
                    f"DI — {titre}",
                    f"Panne détectée sur équipement #{eq_id}.",
                    rng.choice(PRIORITES),
                    "terminee",
                    panne_date - timedelta(hours=rng.uniform(0, 24)),
                    panne_date,
                    eq_id,
                    1,
                ))

                # 2. Ordre de travail terminé → id_ot réel
                global_ot_id += 1
                mttr_hours = rng.uniform(4, 40)  # durée de réparation
                date_debut = panne_date + timedelta(hours=rng.uniform(1, 8))
                date_fin = date_debut + timedelta(hours=mttr_hours)
                id_ot = _insert_one(cur, "ordre_travails", ot_columns, (
                    f"OT-{global_ot_id:04d} — {titre}",
                    f"Correction de la panne sur équipement #{eq_id}.",
                    rng.choice(PRIORITES),
                    "termine",
                    date_debut - timedelta(hours=rng.uniform(0, 24)),  # date_planifiee
                    date_debut,  # date_debut
                    date_fin,  # date_fin
                    int(mttr_hours * 60),  # temps_reel en minutes
                    "Intervention réalisée.",  # commentaire_cloture
                    id_demande,  # id_demande (réel)
                    eq_id,  # id_equipement
                ))

                # 3. Panne rattachée à l'OT (id_ot réel)
                _insert_one(cur, "pannes", panne_columns, (
                    f"Panne : {titre}",
                    f"Détection d'une défaillance sur équipement #{eq_id}.",
                    rng.choice(GRAVITES),
                    panne_date,
                    "Cause en cours d'analyse.",
                    "Correction appliquée lors de l'OT.",
                    "Symptômes : fonctionnement dégradé.",
                    eq_id,
                    id_ot,
                ))
                nb_demandes += 1
                nb_ot += 1
                nb_pannes += 1

        conn.commit()

    return {
        "demande_interventions": nb_demandes,
        "ordre_travails": nb_ot,
        "pannes": nb_pannes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed données de maintenance GMAO-ANALYTICS.")
    parser.add_argument("--db", default=None, help="URL MySQL (défaut : env MAINTENANCE_DB_URL).")
    parser.add_argument("--months", type=int, default=12, help="Historique en mois.")
    parser.add_argument("--seed", type=int, default=7, help="Graine de reproductibilité.")
    parser.add_argument("--reset", action="store_true", help="Vider les tables avant insertion.")
    args = parser.parse_args()

    db_url = args.db or _default_db_url()
    if not db_url:
        raise SystemExit(
            "Aucune URL MySQL. Passez --db ou définissez MAINTENANCE_DB_URL dans "
            "GMAO-ANALYTICS/.env."
        )

    conn = pymysql.connect(**parse_dsn(db_url))
    try:
        counts = seed(conn, months=args.months, seed=args.seed, reset=args.reset)
    finally:
        conn.close()

    print(f"Seed terminé — {counts}")


def parse_dsn(url: str) -> dict:
    """Convertit mysql+pymysql://u:p@host:3306/db en dict pymysql.connect."""

    body = url.split("://", 1)[1]
    creds, host_part = body.rsplit("@", 1)
    user, _, pwd = creds.partition(":")
    host, _, db = host_part.partition("/")
    port = 3306
    if ":" in host:
        host, _, port = host.partition(":")
        port = int(port)
    return {"host": host, "port": port, "user": user, "password": pwd, "database": db}


def _default_db_url() -> str | None:
    import os

    return os.getenv("MAINTENANCE_DB_URL")


if __name__ == "__main__":
    main()

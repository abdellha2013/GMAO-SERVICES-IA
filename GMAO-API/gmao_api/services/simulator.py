"""Générateur artificiel de relevés capteurs (autonome, sans dépendance à gmao_ml).

Les relevés « sains » respectent les plages opératoires nominales ; les relevés
« panne » violent l'une des règles physiques validées sur le jeu AI4I 2020 :

* PWF : puissance hors [3500, 9000] W avec ``power = Torque × RPM × 2π / 60`` ;
* HDF : ΔT = T_process − T_air < 8.6 K **et** RPM < 1380 ;
* OSF : Torque × Tool wear > {L: 11 000 · M: 12 000 · H: 13 000} Nm·min.

Chaque relevé porte un ``equipement_id`` tiré de la table ``equipements``
(catalogue statique local).
"""

from __future__ import annotations

import math
import random
from typing import Any

from gmao_api.services import equipment_catalog

MODES = ("pwf_low", "pwf_high", "hdf", "osf")

_POWER_MIN_W = 3500.0
_POWER_MAX_W = 9000.0
_HDF_DELTA_MAX_K = 8.6
_HDF_RPM_MAX = 1380.0
_OSF_THRESHOLDS = {"L": 11000.0, "M": 12000.0, "H": 13000.0}


def compute_power_w(torque_nm: float, rpm: float) -> float:
    """Puissance mécanique en watts."""

    return torque_nm * rpm * (2.0 * math.pi / 60.0)


def _healthy_reading(rng: random.Random, equipement_id: int) -> dict[str, Any]:
    machine_type = rng.choice(["L", "M", "H"])
    rpm = round(rng.uniform(1385.0, 1515.0), 0)
    torque = round(rng.uniform(26.0, 52.0), 2)
    air_temp = round(rng.uniform(297.9, 301.4), 1)
    process_temp = round(air_temp + rng.uniform(8.8, 10.8), 1)  # ΔT > 8.6 → pas HDF
    wear = int(rng.uniform(0, 240))

    # Garde-fou OSF : produit sous le seuil du type.
    limit = _OSF_THRESHOLDS[machine_type] - 700.0
    if torque * wear > limit:
        wear = int(limit / torque)

    return {
        "equipement_id": equipement_id,
        "Type": machine_type,
        "Air temperature [K]": air_temp,
        "Process temperature [K]": process_temp,
        "Rotational speed [rpm]": rpm,
        "Torque [Nm]": torque,
        "Tool wear [min]": wear,
    }


def _failure_reading(rng: random.Random, equipement_id: int) -> dict[str, Any]:
    mode = rng.choice(MODES)
    machine_type = rng.choice(["L", "M", "H"])
    air_temp = round(rng.uniform(297.9, 301.4), 1)

    if mode == "pwf_low":
        rpm = round(rng.uniform(2700.0, 3100.0), 0)
        torque = round(rng.uniform(2.5, 4.5), 2)
        process_temp = round(air_temp + rng.uniform(9.0, 10.5), 1)
        wear = int(rng.uniform(0, 200))
    elif mode == "pwf_high":
        rpm = round(rng.uniform(1400.0, 1600.0), 0)
        torque = round(rng.uniform(92.0, 118.0), 2)
        process_temp = round(air_temp + rng.uniform(9.0, 10.5), 1)
        wear = int(rng.uniform(0, 200))
    elif mode == "hdf":
        rpm = round(rng.uniform(1230.0, 1360.0), 0)
        torque = round(rng.uniform(30.0, 55.0), 2)
        process_temp = round(air_temp + rng.uniform(6.4, 8.3), 1)  # ΔT < 8.6
        wear = int(rng.uniform(0, 200))
    else:  # osf
        rpm = round(rng.uniform(1385.0, 1510.0), 0)
        torque = round(rng.uniform(70.0, 95.0), 2)
        process_temp = round(air_temp + rng.uniform(9.0, 10.5), 1)
        wear = int((_OSF_THRESHOLDS[machine_type] + 800.0 - rng.uniform(0, 600)) / torque)

    return {
        "equipement_id": equipement_id,
        "Type": machine_type,
        "Air temperature [K]": air_temp,
        "Process temperature [K]": process_temp,
        "Rotational speed [rpm]": rpm,
        "Torque [Nm]": torque,
        "Tool wear [min]": wear,
    }


def reading_mode(reading: dict[str, Any]) -> str:
    """Re-classe un relevé selon les règles physiques ('healthy' ou mode de panne)."""

    torque = float(reading["Torque [Nm]"])
    rpm = float(reading["Rotational speed [rpm]"])
    wear = float(reading["Tool wear [min]"])
    delta_t = float(reading["Process temperature [K]"]) - float(reading["Air temperature [K]"])

    power = compute_power_w(torque, rpm)
    if power < _POWER_MIN_W or power > _POWER_MAX_W:
        return "pwf"
    if delta_t < _HDF_DELTA_MAX_K and rpm < _HDF_RPM_MAX:
        return "hdf"
    if torque * wear > _OSF_THRESHOLDS[str(reading["Type"])]:
        return "osf"
    return "healthy"


def generate_reading(
    mode: str = "healthy",
    *,
    random_state: int | None = None,
    equipement_id: int | None = None,
) -> dict[str, Any]:
    """Génère un seul relevé ('healthy' ou 'failure')."""

    if mode not in ("healthy", "failure"):
        raise ValueError("mode doit valoir 'healthy' ou 'failure'")
    rng = random.Random(random_state)
    eq_id = equipement_id or rng.choice(equipment_catalog.equipment_ids())
    builder = _failure_reading if mode == "failure" else _healthy_reading
    return builder(rng, eq_id)


def generate_batch(
    count: int,
    failure_rate: float,
    *,
    random_state: int | None = None,
    equipement_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Génère ``count`` relevés artificiels (dicts compatibles :class:`SensorReading`)."""

    if count < 1:
        raise ValueError("count doit être >= 1")
    if not 0.0 <= failure_rate <= 1.0:
        raise ValueError("failure_rate doit être dans [0, 1]")

    rng = random.Random(random_state)
    pool_ids = equipement_ids or equipment_catalog.equipment_ids()

    n_failures = round(count * failure_rate)
    modes = ["failure"] * n_failures + ["healthy"] * (count - n_failures)
    rng.shuffle(modes)

    readings: list[dict[str, Any]] = []
    for mode in modes:
        eq_id = rng.choice(pool_ids)
        builder = _failure_reading if mode == "failure" else _healthy_reading
        readings.append(builder(rng, eq_id))

    return readings


__all__ = [
    "MODES",
    "compute_power_w",
    "generate_batch",
    "generate_reading",
    "reading_mode",
]

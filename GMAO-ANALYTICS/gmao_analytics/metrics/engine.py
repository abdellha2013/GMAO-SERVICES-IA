"""Moteur de calcul des indicateurs de maintenance (MTBF / MTTR / disponibilité).

Les fonctions de ce module sont **pures** : elles prennent des
``DataFrame``/listes Python en entrée et retournent des dictionnaires
sérialisables, sans effet de bord (pas d'accès DB). Leur logique est
ainsi unitairement testable sans dépendre de MySQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

__all__ = [
    "compute_mttr",
    "compute_mtbf",
    "compute_availability",
    "metric_summary_from_df",
    "global_summary",
]


def _safe_mean(values: Iterable[float]) -> float | None:
    """Moyenne d'une série ; ``None`` si aucune valeur exploitable."""

    numbers = [float(v) for v in values if v is not None and not np.isnan(v)]
    if not numbers:
        return None
    return float(np.mean(numbers))


def compute_mttr(ot_df: pd.DataFrame) -> float | None:
    """Temps moyen de réparation (h) à partir des ordres de travail terminés.

    Utilise ``temps_reel`` (minutes) s'il est renseigné, sinon la durée
    entre ``date_debut`` et ``date_fin``. Retourne ``None`` si aucun OT
    exploitable.
    """

    if ot_df is None or ot_df.empty:
        return None

    rows: list[float] = []
    for _, row in ot_df.iterrows():
        duration = _ot_duration_hours(row)
        if duration is not None:
            rows.append(duration)

    return _safe_mean(rows)


def _ot_duration_hours(row: pd.Series) -> float | None:
    """Durée d'un OT en heures (temps_reel en minutes, sinon date_fin - date_debut)."""

    temps_reel = row.get("temps_reel")
    if temps_reel is not None and not pd.isna(temps_reel):
        try:
            return float(temps_reel) / 60.0
        except (TypeError, ValueError):
            pass

    debut = row.get("date_debut")
    fin = row.get("date_fin")
    if debut is None or fin is None or pd.isna(debut) or pd.isna(fin):
        return None
    debut = pd.to_datetime(debut)
    fin = pd.to_datetime(fin)
    if fin <= debut:
        return None
    return float((fin - debut).total_seconds()) / 3600.0


def compute_mtbf(panne_dates: Iterable[Any]) -> float | None:
    """Temps moyen entre deux pannes (h) à partir des dates de détection.

    MTBF = moyenne des écarts entre dates de pannes consécutives.
    Retourne ``None`` s'il y a moins de deux pannes exploitables.
    """

    dates = sorted(pd.to_datetime(d) for d in panne_dates if d is not None and not pd.isna(d))
    if len(dates) < 2:
        return None

    gaps_hours = [
        float((dates[i + 1] - dates[i]).total_seconds()) / 3600.0
        for i in range(len(dates) - 1)
    ]
    return float(np.mean(gaps_hours))


def compute_availability(mtbf_hours: float | None, mttr_hours: float | None) -> float | None:
    """Taux de disponibilité = MTBF / (MTBF + MTTR)."""

    if mtbf_hours is None or mttr_hours is None or mtbf_hours + mttr_hours == 0:
        return None
    return float(mtbf_hours / (mtbf_hours + mttr_hours) * 100.0)


def metric_summary_from_df(
    panne_df: pd.DataFrame,
    ot_df: pd.DataFrame,
) -> dict[str, Any]:
    """Calcule les indicateurs d'un équipement à partir de ses pannes et OT.

    Contrairement aux fonctions unitaires ci-dessus (qui opèrent sur un
    référentiel), cette fonction inclut les écarts de fin de série :
    le dernier intervalle de fonctionnement (dernière panne → aujourd'hui)
    participe au MTBF, afin de refléter le temps écoulé sans panne courante.
    """

    mtbf_series = _mtbf_with_uptime(panne_df)
    mtbf_hours = _safe_mean(mtbf_series)

    mttr_hours = compute_mttr(ot_df)
    availability = compute_availability(mtbf_hours, mttr_hours)

    return {
        "mtbf_hours": _round(mtbf_hours),
        "mttr_hours": _round(mttr_hours),
        "availability_pct": _round(availability),
        "nb_pannes": int(len(panne_df)),
        "nb_interventions": int(len(ot_df)),
    }


def global_summary(per_equipement: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrège les indicateurs individuels en une lecture globale du parc."""

    mtbfs = [e["mtbf_hours"] for e in per_equipement if e["mtbf_hours"] is not None]
    mttrs = [e["mttr_hours"] for e in per_equipement if e["mttr_hours"] is not None]

    global_mtbf = _safe_mean(mtbfs)
    global_mttr = _safe_mean(mttrs)
    global_avail = compute_availability(global_mtbf, global_mttr)

    return {
        "mtbf_hours": _round(global_mtbf),
        "mttr_hours": _round(global_mttr),
        "availability_pct": _round(global_avail),
        "nb_pannes": int(sum(e["nb_pannes"] for e in per_equipement)),
        "nb_interventions": int(sum(e["nb_interventions"] for e in per_equipement)),
    }


def _mtbf_with_uptime(panne_df: pd.DataFrame) -> list[float]:
    """Écarts entre pannes consécutives, incluant l'uptime courant.

    Ajoute le dernier intervalle (dernière panne → now) lorsque l'historique
    contient au moins deux pannes, pour refléter la disponibilité en cours.
    """

    if panne_df is None or panne_df.empty:
        return []

    dates = sorted(pd.to_datetime(d) for d in panne_df["date_detection"] if d is not None)
    if len(dates) < 2:
        return []

    gaps = [
        float((dates[i + 1] - dates[i]).total_seconds()) / 3600.0
        for i in range(len(dates) - 1)
    ]
    # uptime courant depuis la dernière panne (borné pour ne pas masquer l'absence de panne)
    now = datetime.now()
    try:
        last = dates[-1]
        if isinstance(last, pd.Timestamp):
            last = last.to_pydatetime()
        current_uptime = max(0.0, (now - last).total_seconds() / 3600.0)
    except Exception:
        current_uptime = None
    if current_uptime is not None:
        gaps.append(current_uptime)

    return gaps


def _round(value: float | None, ndigits: int = 2) -> float | None:
    if value is None:
        return None
    return float(round(value, ndigits))

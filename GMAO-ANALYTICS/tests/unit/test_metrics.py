"""Tests du moteur de calcul MTBF/MTTR/disponibilité."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from gmao_analytics.metrics.engine import (
    compute_availability,
    compute_mtbf,
    compute_mttr,
    global_summary,
    metric_summary_from_df,
)


def _panne_df(dates: list[datetime]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id_equipement": 1, "date_detection": d} for d in dates]
    )


def _ot_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class TestComputeMtbf:
    def test_moins_de_deux_pannes_retourne_none(self) -> None:
        assert compute_mtbf([]) is None
        assert compute_mtbf([datetime(2024, 1, 1)]) is None

    def test_une_paire_calcule_ecart(self) -> None:
        d1 = datetime(2024, 1, 1, 0, 0)
        d2 = datetime(2024, 1, 3, 0, 0)  # 48 h
        assert compute_mtbf([d1, d2]) == 48.0

    def test_trois_dates_moyenne_des_ecarts(self) -> None:
        # écarts : 48h puis 24h → moyenne 36h
        d1 = datetime(2024, 1, 1)
        d2 = datetime(2024, 1, 3)
        d3 = datetime(2024, 1, 4)
        assert compute_mtbf([d1, d2, d3]) == 36.0

    def test_ordre_chronologique_ignore(self) -> None:
        d1 = datetime(2024, 1, 1)
        d2 = datetime(2024, 1, 3)
        assert compute_mtbf([d2, d1]) == 48.0


class TestComputeMttr:
    def test_temps_reel_minutes_convertis_en_heures(self) -> None:
        rows = [{"id_equipement": 1, "statut": "termine", "date_debut": None, "date_fin": None, "temps_reel": 120}]
        assert compute_mttr(_ot_df(rows)) == 2.0

    def test_ecart_dates_si_temps_reel_absent(self) -> None:
        a = datetime(2024, 1, 1, 8)
        b = datetime(2024, 1, 1, 11)  # 3 h
        rows = [{"id_equipement": 1, "statut": "termine", "date_debut": a, "date_fin": b, "temps_reel": None}]
        assert compute_mttr(_ot_df(rows)) == 3.0

    def test_ignorer_les_ot_non_terminés_nest_pas_la_purge(self) -> None:
        # compute_mttr opère sur un df déjà filtré (statut=termine) côté service.
        a = datetime(2024, 1, 1, 8)
        b = datetime(2024, 1, 1, 9)
        rows = [
            {"id_equipement": 1, "statut": "termine", "date_debut": a, "date_fin": b, "temps_reel": None},
            {"id_equipement": 1, "statut": "termine", "date_debut": a, "date_fin": a, "temps_reel": None},  # invalide
        ]
        assert compute_mttr(_ot_df(rows)) == 1.0

    def test_vide_retourne_none(self) -> None:
        assert compute_mttr(_ot_df([])) is None


class TestAvailability:
    def test_formule_standard(self) -> None:
        # MTBF=100h, MTTR=25h → dispo = 100/(100+25) = 80 %
        assert compute_availability(100.0, 25.0) == 80.0

    def test_none_si_manquant(self) -> None:
        assert compute_availability(None, 25.0) is None
        assert compute_availability(100.0, None) is None


class TestMetricSummary:
    def test_summary_global(self) -> None:
        now = datetime.now()
        panne = _panne_df([now - timedelta(days=10), now - timedelta(days=5), now - timedelta(days=2)])
        ot = _ot_df([
            {"id_equipement": 1, "statut": "termine", "date_debut": now - timedelta(days=9), "date_fin": now - timedelta(days=9), "temps_reel": 60},
            {"id_equipement": 1, "statut": "termine", "date_debut": now - timedelta(days=4), "date_fin": now - timedelta(days=4), "temps_reel": 120},
        ])
        summary = metric_summary_from_df(panne, ot)
        assert summary["nb_pannes"] == 3
        assert summary["nb_interventions"] == 2
        assert summary["mttr_hours"] == 1.5  # (1h + 2h)/2
        assert summary["mtbf_hours"] is not None
        assert summary["availability_pct"] is not None

    def test_summary_sans_donnees(self) -> None:
        summary = metric_summary_from_df(_panne_df([]), _ot_df([]))
        assert summary["nb_pannes"] == 0
        assert summary["mtbf_hours"] is None
        assert summary["availability_pct"] is None


class TestGlobalSummary:
    def test_agrege_sur_les_valeurs_valides(self) -> None:
        per = [
            {"mtbf_hours": 100.0, "mttr_hours": 10.0, "availability_pct": 90.9, "nb_pannes": 3, "nb_interventions": 3},
            {"mtbf_hours": 200.0, "mttr_hours": 20.0, "availability_pct": 90.9, "nb_pannes": 5, "nb_interventions": 5},
        ]
        g = global_summary(per)
        assert g["mtbf_hours"] == 150.0
        assert g["mttr_hours"] == 15.0
        assert g["nb_pannes"] == 8
        assert g["availability_pct"] == round(150 / (150 + 15) * 100, 2)

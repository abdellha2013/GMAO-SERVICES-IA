"""Tests du simulateur artificiel et du catalogue équipements."""

from __future__ import annotations

import pytest

from gmao_api.services import equipment_catalog, simulator


class TestCatalogue:
    def test_12_equipements_ids_1_a_12(self) -> None:
        assert equipment_catalog.equipment_ids() == list(range(1, 13))
        assert len(equipment_catalog.EQUIPEMENTS) == 12

    def test_criticites_valides(self) -> None:
        for equipement in equipment_catalog.EQUIPEMENTS:
            assert equipement["criticite"] in equipment_catalog.CRITICITES_VALIDES

    def test_describe_inconnu(self) -> None:
        assert equipment_catalog.describe(999) == "Équipement #999"
        assert "Tour CNC" in equipment_catalog.describe(5)


class TestSimulateur:
    def test_reproductible_avec_seed(self) -> None:
        batch_a = simulator.generate_batch(10, 0.5, random_state=42)
        batch_b = simulator.generate_batch(10, 0.5, random_state=42)
        assert batch_a == batch_b

    def test_champs_complets_et_equipement_valide(self) -> None:
        valid_ids = set(equipment_catalog.equipment_ids())
        required = {
            "equipement_id",
            "Type",
            "Air temperature [K]",
            "Process temperature [K]",
            "Rotational speed [rpm]",
            "Torque [Nm]",
            "Tool wear [min]",
        }
        for reading in simulator.generate_batch(30, 0.5, random_state=1):
            assert required <= set(reading)
            assert reading["equipement_id"] in valid_ids
            assert reading["Type"] in {"L", "M", "H"}

    def test_sains_dans_plages_operatoires(self) -> None:
        """Puissance dans [3500, 9000] W, ΔT > 8.6 K, pas d'OSF."""

        for reading in simulator.generate_batch(50, 0.0, random_state=3):
            assert simulator.reading_mode(reading) == "healthy", reading
            power = simulator.compute_power_w(
                reading["Torque [Nm]"], reading["Rotational speed [rpm]"]
            )
            assert 3500.0 <= power <= 9000.0, (reading, power)

    def test_pannes_violent_une_regule(self) -> None:
        modes = {
            simulator.reading_mode(r)
            for r in simulator.generate_batch(40, 1.0, random_state=4)
        }
        assert modes <= {"pwf", "hdf", "osf"}
        assert modes != {"healthy"}

    def test_parametres_invalides_levent(self) -> None:
        with pytest.raises(ValueError):
            simulator.generate_batch(0, 0.5)
        with pytest.raises(ValueError):
            simulator.generate_batch(5, 1.5)

    def test_generate_reading_modes(self) -> None:
        healthy = simulator.generate_reading("healthy", random_state=9)
        failure = simulator.generate_reading("failure", random_state=9)
        assert simulator.reading_mode(healthy) == "healthy"
        assert simulator.reading_mode(failure) != "healthy"

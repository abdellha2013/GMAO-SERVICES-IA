"""Contrat abstrait d'une stratégie d'entraînement GMAO-ML."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TrainingStrategy(ABC):
    """Fournit un estimateur sklearn compatible pour la classification.

    Le prétraitement (imputation, encodage) est géré en amont par le
    ``Pipeline`` de l'orchestrateur : une stratégie ne définit que le
    classifieur final et ses hyperparamètres.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Retourne l'identifiant stable de la stratégie dans le registre."""

        raise NotImplementedError

    @abstractmethod
    def create_estimator(self) -> Any:
        """Retourne une instance d'estimateur sklearn non entraînée."""

        raise NotImplementedError

    def get_params(self) -> dict[str, Any]:
        """Retourne les hyperparamètres à journaliser (défaut : rien)."""

        return {}

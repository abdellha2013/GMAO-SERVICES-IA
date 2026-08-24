"""
gmao_ml/scripts/load_ai4i_dataset.py
====================================

Télécharge le dataset public **AI4I 2020 Predictive Maintenance**
(Kaggle : ``stephanmatzka/predictive-maintenance-dataset-ai4i-2020``)
via ``kagglehub``, l'enrichit et le sauvegarde localement en CSV.

Enrichissements :

- ``failure_type`` : libellé du mode de défaillance principal
  (``No Failure``, ``TWF``, ``HDF``, ``PWF``, ``OSF``, ``RNF`` ou
  ``Multiple Failures``) — pratique pour une future cible multi-classes ;
- colonnes identifiants (``UDI``, ``Product ID``) retirées.

Colonnes finales (cible par défaut : ``machine_failure``, binaire) :

- ``Type``                : qualité produit L/M/H (catégorielle)
- ``Air temperature [K]`` / ``Process temperature [K]``
- ``Rotational speed [rpm]`` / ``Torque [Nm]`` / ``Tool wear [min]``
- ``machine_failure``     : 0/1
- ``TWF HDF PWF OSF RNF failure_type``

Usage::

    uv run python GMAO-ML/scripts/load_ai4i_dataset.py [--out GMAO-ML/data/ai4i_2020.csv]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import kagglehub
import pandas as pd

__all__ = ["load_ai4i", "main"]

KAGGLE_HANDLE = "stephanmatzka/predictive-maintenance-dataset-ai4i-2020"

FAILURE_MODES = ["TWF", "HDF", "PWF", "OSF", "RNF"]

 
def _find_csv(dataset_path: Path) -> Path:
    """Localise le fichier CSV principal dans le dataset téléchargé."""

    csv_files = sorted(dataset_path.rglob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV file found inside downloaded dataset: {dataset_path}"
        )
    return csv_files[0]


def load_ai4i(out_path: str | Path) -> pd.DataFrame:
    """Télécharge, nettoie et sauvegarde le dataset AI4I 2020.

    Parameters
    ----------
    out_path:
        Chemin du CSV de sortie.

    Returns
    -------
    pd.DataFrame
        Le dataset nettoyé et enrichi.
    """

    print(f"Downloading Kaggle dataset '{KAGGLE_HANDLE}' via kagglehub...")
    dataset_dir = Path(kagglehub.dataset_download(KAGGLE_HANDLE))
    csv_file = _find_csv(dataset_dir)
    print(f"Found data file: {csv_file}")

    df = pd.read_csv(csv_file)

    # --- Dérivation d'une cible multi-classes explicite ---
    mode_columns = [col for col in FAILURE_MODES if col in df.columns]
    if mode_columns and "failure_type" not in df.columns:

        def _label_failure(row: pd.Series) -> str:
            active = [mode for mode in mode_columns if row[mode] == 1]
            if not active:
                return "No Failure"
            if len(active) > 1:
                return "Multiple Failures"
            return active[0]

        df["failure_type"] = df.apply(_label_failure, axis=1)

    # --- Retrait des identifiants non prédictifs + normalisation de la cible ---
    drop_columns = [col for col in ("UDI", "Product ID") if col in df.columns]
    df = df.drop(columns=drop_columns)

    if "Machine failure" in df.columns:
        df = df.rename(columns={"Machine failure": "machine_failure"})

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_file, index=False)

    print(f"Dataset saved: {out_file} ({len(df)} rows, {len(df.columns)} columns)")
    print(df.head().to_string())

    target = "machine_failure"
    if target in df.columns:
        print(f"\nTarget distribution ('{target}'):")
        print(df[target].value_counts().to_string())
    if "failure_type" in df.columns:
        print("\nFailure types distribution:")
        print(df["failure_type"].value_counts().to_string())

    return df


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI."""

    parser = argparse.ArgumentParser(
        prog="load_ai4i_dataset.py",
        description="Download the AI4I 2020 predictive maintenance dataset.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: GMAO-ML/data/ai4i_2020.csv).",
    )
    args = parser.parse_args(argv)

    out_path = (
        Path(args.out)
        if args.out
        else Path(__file__).resolve().parents[1] / "data" / "ai4i_2020.csv"
    )
    load_ai4i(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Mock Laravel — simule la réception des demandes d'intervention (port 9000).

Reproduit le comportement attendu du vrai backend :

* ``POST /api/intervention-requests`` — valide la structure de la table
  ``demande_interventions`` (colonnes + valeurs ENUM), attribue un
  ``id_demande`` auto-incrémenté et une ``date_creation``, répond au format
  Eloquent ``{"created": true, "data": {...}}`` ;
* ``GET /api/intervention-requests`` — liste des demandes stockées.

Lancement :
    uv run uvicorn scripts.mock_laravel:app --app-dir GMAO-API --port 9000
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s MOCK-LARAVEL %(message)s")
logger = logging.getLogger("mock_laravel")

PRIORITES = {"faible", "moyenne", "elevee", "critique"}
STATUTS = {"en_attente", "validee", "refusee", "en_cours", "terminee"}

COLUMNS = ("titre", "description", "priorite", "statut", "id_equipement", "id_utilisateur")

app = FastAPI(title="Mock Laravel — demande_interventions", version="0.1.0")

_state: dict[str, Any] = {"next_id": 1, "rows": []}


def _validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for column in COLUMNS:
        if column not in payload:
            errors.append(f"colonne manquante : {column}")
    if payload.get("priorite") is not None and payload["priorite"] not in PRIORITES:
        errors.append(f"priorite invalide : {payload['priorite']!r}")
    if payload.get("statut") is not None and payload["statut"] not in STATUTS:
        errors.append(f"statut invalide : {payload['statut']!r}")
    for int_column in ("id_equipement", "id_utilisateur"):
        value = payload.get(int_column)
        if value is not None and not isinstance(value, int):
            errors.append(f"{int_column} doit être un entier (reçu {type(value).__name__})")
    return errors


@app.post("/api/intervention-requests")
async def create_demande(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "JSON invalide"})

    errors = _validate(payload)
    if errors:
        logger.warning("REJET — %s", errors)
        return JSONResponse(
            status_code=422,
            content={"message": "Payload non conforme à demande_interventions", "errors": errors},
        )

    row = {
        "id_demande": _state["next_id"],
        **{column: payload[column] for column in COLUMNS},
        "date_creation": datetime.now().isoformat(timespec="seconds"),
        "date_validation": None,
    }
    _state["next_id"] += 1
    _state["rows"].append(row)

    logger.info(
        "INSERT INTO demande_interventions → id=%s equipement=%s user=%s priorite=%s | %s",
        row["id_demande"],
        row["id_equipement"],
        row["id_utilisateur"],
        row["priorite"],
        row["titre"],
    )
    return JSONResponse(status_code=201, content={"created": True, "data": row})


@app.get("/api/intervention-requests")
async def list_demandes() -> dict[str, Any]:
    return {"count": len(_state["rows"]), "data": _state["rows"]}


@app.post("/_reset")
async def reset() -> dict[str, Any]:
    _state["next_id"] = 1
    _state["rows"] = []
    return {"reset": True}

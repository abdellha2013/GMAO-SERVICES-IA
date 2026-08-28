"""
GMAO-RAG — Création de la collection Qdrant et de ses index de payload.

Cette collection est le pendant vectoriel de la table `document_chunks` (MySQL) :
- id du point Qdrant  == document_chunks.id_chunk (entier partagé)
- payload.id_chunk    == document_chunks.id_chunk (permet de revenir en MySQL
                          pour relire le contenu complet, etc.)

Aucune jointure n'existe côté Qdrant : tout champ nécessaire au filtrage
doit être dupliqué dans le payload au moment de l'indexation.
"""


from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import (
    Distance,
    VectorParams,
    PayloadSchemaType,
)

from app.embedding import SentenceTransformerEmbedding


load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class QdrantSettings:
    """Configuration Qdrant et du modèle sélectionné depuis ``.env``."""

    host: str
    port: int
    collection_name: str
    model_name: str
    model_revision: str | None
    device: str


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"La variable {name} doit être définie dans .env.")
    return value


def choose_model_size() -> str:
    """Ask which configured embedding model must define the collection."""
    while True:
        choice = input("Choisissez le modèle d'embedding [small/large] : ").strip().lower()
        if choice in {"small", "large"}:
            return choice
        print("Choix invalide. Saisissez 'small' ou 'large'.")


def load_settings(model_size: str) -> QdrantSettings:
    """Read the selected model and Qdrant connection settings from ``.env``."""
    if model_size not in {"small", "large"}:
        raise ValueError("model_size doit être 'small' ou 'large'.")

    prefix = f"EMBEDDING_{model_size.upper()}"
    revision = os.getenv(f"{prefix}_MODEL_REVISION", "").strip() or None
    try:
        port = int(os.getenv("QDRANT_PORT", "6333"))
    except ValueError as exc:
        raise RuntimeError("QDRANT_PORT doit être un entier.") from exc

    return QdrantSettings(
        host=os.getenv("QDRANT_HOST", "localhost").strip() or "localhost",
        port=port,
        collection_name=os.getenv("QDRANT_COLLECTION_NAME", "gmao_chunks").strip() or "gmao_chunks",
        model_name=_required_env(f"{prefix}_MODEL_NAME"),
        model_revision=revision,
        device=os.getenv("EMBEDDING_DEVICE", "auto").strip() or "auto",
    )


def resolve_vector_size(settings: QdrantSettings) -> int:
    """Load the selected model and return its real embedding dimension."""
    strategy = SentenceTransformerEmbedding(
        model_name=settings.model_name,
        model_revision=settings.model_revision,
        device=settings.device,
    )
    return strategy.dimension


def verify_qdrant_connection(client: QdrantClient, settings: QdrantSettings) -> None:
    """Fail early with an actionable message when the Qdrant server is down."""
    try:
        client.get_collections()
    except ResponseHandlingException as exc:
        raise RuntimeError(
            f"Qdrant est inaccessible sur {settings.host}:{settings.port}. "
            "Démarrez le serveur Qdrant, ou corrigez QDRANT_HOST et QDRANT_PORT dans .env."
        ) from exc


def create_collection(client: QdrantClient, settings: QdrantSettings, vector_size: int) -> None:
    """Crée la collection si elle n'existe pas déjà."""
    if client.collection_exists(settings.collection_name):
        collection = client.get_collection(settings.collection_name)
        vectors = collection.config.params.vectors
        existing_size = vectors.size if isinstance(vectors, VectorParams) else None
        if existing_size != vector_size:
            raise RuntimeError(
                f"La collection '{settings.collection_name}' utilise des vecteurs de dimension "
                f"{existing_size}, mais le modèle '{settings.model_name}' produit des vecteurs "
                f"de dimension {vector_size}. Utilisez le même modèle ou une autre collection."
            )
        print(
            f"Collection '{settings.collection_name}' déjà existante "
            f"(dimension={existing_size}) — compatible avec le modèle sélectionné."
        )
        return

    client.create_collection(
        collection_name=settings.collection_name,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )
    print(
        f"Collection '{settings.collection_name}' créée "
        f"(modèle={settings.model_name}, dimension={vector_size}, distance=cosine)."
    )


def create_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """
    Index de payload pour les champs effectivement utilisés en filtrage
    lors du retrieval (ex: ne chercher que dans les Panne d'un équipement
    donné, ou exclure/inclure les Document).
    """
    indexes = {
        "type_source": PayloadSchemaType.KEYWORD,   # "Document" | "Panne"
        "id_equipement": PayloadSchemaType.INTEGER,
    }

    for field_name, schema_type in indexes.items():
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=schema_type,
        )
        print(f"Index créé sur payload.{field_name} ({schema_type}).")


# ----------------------------------------------------------------------------
# Structure d'un point (rappel — pas de code, juste la forme attendue) :
#
# {
#     "id": 1042,                         # identique à chunk_rag.id_chunk
#     "vector": [0.0123, -0.0456, ...],   # longueur = dimension du modèle
#     "payload": {
#         # Payload volontairement minimal : uniquement les champs utiles au
#         # PRE-FILTRAGE de la recherche vectorielle (avant comparaison des
#         # vecteurs). Tout le reste (contenu, id_document/id_panne, ordre_chunk,
#         # embedding_model...) est redondant : il est récupérable en une seule
#         # requête MySQL via `id_chunk` une fois les meilleurs points connus
#         # (SELECT ... FROM chunk_rag WHERE id_chunk IN (...)).
#         "id_chunk": 1042,        # clé de jointure vers chunk_rag (MySQL) — indispensable
#         "type_source": "Panne",  # ou "Document" — filtre pré-recherche
#         "id_equipement": 58,     # filtre pré-recherche ("cherche sur cet équipement")
#     },
# }
# ----------------------------------------------------------------------------


if __name__ == "__main__":
    selected_size = choose_model_size()
    settings = load_settings(selected_size)
    client = QdrantClient(host=settings.host, port=settings.port)
    try:
        verify_qdrant_connection(client, settings)
        vector_size = resolve_vector_size(settings)
        create_collection(client, settings, vector_size)
        create_payload_indexes(client, settings.collection_name)
    except RuntimeError as exc:
        print(f"Erreur : {exc}")
        raise SystemExit(1) from exc

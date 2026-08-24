"""
app/models/document.py

Description
-----------
Définition du modèle Document utilisé dans le pipeline RAG.

Cette classe représente le format standard de toutes les données
entrant dans le système, quelle que soit leur origine :

- PDF
- DOCX
- TXT
- HTML
- CSV
- XLSX
- PPTX
- MySQL
- API
- Futures sources

Tous les Data Sources doivent retourner une instance de cette classe.

Le Document est ensuite utilisé par :

    Loader
        ↓
    Parser
        ↓
    Chunker
        ↓
    Embedding
        ↓
    Retrieval

Cette classe ne contient aucune logique métier.
Elle sert uniquement de conteneur de données.

- diagramme de classe :
"/" --> Attributs Dérivés
<u>from_dict</u> --> est soulignee segnifie que c'est une Méthode de Classe 
+--------------------------------------------------------------------------+

|                                Document                                  |
|                                {slots}                                   |
+--------------------------------------------------------------------------+
| + source_name : str                                                      |
| + source_type : str                                                      |
| + source_path : Path | None = None                                       |
| + content : str = ""                                                     |
| + mime_type : str | None = None                                          |
| + size : int = 0                                                         |
| + created_at : datetime | None = None                                    |
| + updated_at : datetime | None = None                                    |
| + metadata : dict[str, Any]                                              |
| / is_empty : bool {readOnly}                                             |
| / content_length : int {readOnly}                                        |
| / extension : str | None {readOnly}                                      |
| / filename : str {readOnly}                                              |
+--------------------------------------------------------------------------+
| + to_dict() : dict[str, Any]                                             |
| + <u>from_dict</u>(data: dict[str, Any]) : Document                      |
| + __str__() : str                                                        |
| + __repr__() : str                                                       |
+--------------------------------------------------------------------------+

"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Document:
    """
    Représentation standard d'un document dans le système.

    Toutes les sources de données (fichiers, base de données,
    API, etc.) doivent produire une instance de cette classe.

    Cette uniformisation permet aux modules suivants
    (Parser, Chunker, Embedding...) d'ignorer complètement
    l'origine des données.
    """

    # ==========================================================
    # Source
    # ==========================================================

    source_name: str
    """Nom de la source (ex: maintenance.pdf)."""

    source_type: str
    """
    Type de la source.

    Exemples :
        - pdf
        - docx
        - txt
        - mysql
        - api
    """

    source_path: Path | None = None
    """Chemin vers la source si disponible."""

    # ==========================================================
    # Content
    # ==========================================================

    content: str = ""
    """Contenu brut du document."""

    # ==========================================================
    # Metadata
    # ==========================================================

    mime_type: str | None = None
    """Type MIME."""

    size: int = 0
    """Taille en octets."""

    # created_at: datetime = field(default_factory=datetime.now)
    created_at: datetime | None = None
    """Date de création."""
    # updated_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None
    """Date de dernière modification."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Métadonnées spécifiques à la source.

    Exemple PDF :
        - author
        - title
        - pages

    Exemple MySQL :
        - database
        - table
        - primary_key
    """

    # ==========================================================
    # Properties
    # ==========================================================

    @property
    def is_empty(self) -> bool:
        """
        Retourne True si le document ne contient aucun texte.
        """
        return not self.content or self.content.isspace() #isspace retutn true si il existe une suite des espaces

    @property
    def content_length(self) -> int:
        """
        Retourne la longueur du contenu.
        """
        return len(self.content)

    @property
    def extension(self) -> str | None:
        """
        Retourne l'extension du fichier.

        Exemple :
            ".pdf"

        Retourne None si la source ne possède pas de chemin.
        """
        
        if self.source_path is None:
            return None
    
        return Path(self.source_path).suffix.lower()

    @property
    def filename(self) -> str:
        """
        Retourne le nom du fichier.

        Si aucun chemin n'existe,
        retourne simplement source_name.
        """
        if self.source_path is None:
            return self.source_name

        return Path(self.source_path).name # 

    # ==========================================================
    # Serialization
    # ==========================================================

    def to_dict(self) -> dict[str, Any]:
        """
        Convertit le document en dictionnaire.

        Cette méthode est utilisée pour :

        - les tests
        - la sérialisation JSON
        - les APIs
        - les bases de données
        """
        data = asdict(self)

        if self.source_path is not None:
            data["source_path"] = str(self.source_path)

        return data

    # Méthode Statique Cela permet d'appeler la méthode directement
    # depuis la classe (ex: Document.from_dict(...)), 
    # sans avoir besoin de créer un document au préalable.
    @classmethod 
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        """
        Crée un Document à partir d'un dictionnaire.
        """
        data = data.copy()

        if data.get("source_path"):
            data["source_path"] = Path(data["source_path"])
        # effectuent ce qu'on appelle un "dictionnary unpacking" 
        # (dépaquetage de dictionnaire). Cela transforme les clés et valeurs du 
        # dictionnaire en arguments nommés pour la fonction
        return cls(**data)

    # ==========================================================
    # Display
    # ==========================================================

    def __str__(self) -> str:
        """
        Représentation lisible destinée aux utilisateurs.
        """
        return (
            f"Document("
            f"name='{self.source_name}', "
            f"type='{self.source_type}', "
            f"size={self.size} bytes)"
        )

    def __repr__(self) -> str:
        """
        Représentation destinée au débogage.

        Le contenu du document n'est jamais affiché
        afin d'éviter des logs volumineux.
        """
        return (
            f"Document("
            f"source_name={self.source_name!r}, "
            f"source_type={self.source_type!r}, "
            f"size={self.size}, "
            f"content_length={self.content_length})"
        )


SourceDocument = Document # SourceDocument est un alias pour Document. Cela permet de clarifier le rôle du document dans le pipeline RAG. 
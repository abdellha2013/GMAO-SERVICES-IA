"""Ingestion endpoints — file, files, database.

These endpoints expose the full ingestion pipeline (load → parse →
chunk → embed → store) as HTTP APIs.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from typing import Annotated

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import create_engine, text

from app.api.auth import verify_api_key
from app.api.deps import (
    get_chunker_orchestrator,
    get_data_source_orchestrator,
    get_embedding_orchestrator,
    get_parser_orchestrator,
    get_storage_orchestrator,
)
from app.api.schemas import (
    IngestDatabaseRequest,
    IngestFileRequest,
    IngestMultipleRequest,
    IngestResponse,
    IngestResult,
)
from app.chunker.orchestrator import ChunkerOrchestrator
from app.exceptions.database import ForeignKeyError

from app.api.v1.documents import delete_document_by_id

logger = logging.getLogger("gmao_rag.api.ingest")

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

_STRUCTURED_SOURCE_TYPES = {"csv", "json", "xlsx"}
_STRUCTURED_CHUNK_SIZE = 3000
_DEFAULT_CHUNK_SIZE = 500
_DEFAULT_CHUNK_OVERLAP = 50


def _resolve_chunk_options(
    source_type: str | None,
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> tuple[int, int]:
    """
    Resolve effective chunking options for a parsed document.

    Explicit ``chunk_size`` / ``chunk_overlap`` values win.  When omitted,
    structured tabular formats (CSV/JSON/XLSX) use a larger default
    chunk_size with no overlap — the same content then produces far fewer
    chunks and, on a CPU-only node, a much faster embedding step.
    """
    is_structured = (source_type or "").strip().lower() in _STRUCTURED_SOURCE_TYPES
    eff_size = chunk_size if chunk_size is not None else (
        _STRUCTURED_CHUNK_SIZE if is_structured else _DEFAULT_CHUNK_SIZE
    )
    eff_overlap = chunk_overlap if chunk_overlap is not None else (
        0 if is_structured else _DEFAULT_CHUNK_OVERLAP
    )
    return eff_size, eff_overlap


def _resolve_chunker(
    chunker_orch: object,
    chunk_size: int,
    chunk_overlap: int,
) -> object:
    """
    Reuse the shared chunker when its options match, otherwise build a
    dedicated orchestrator with the requested options.  The shared
    orchestrator is constructed once at startup, so per-ingest overrides
    would otherwise be silently ignored.
    """
    if (
        chunker_orch.chunk_size == chunk_size
        and chunker_orch.chunk_overlap == chunk_overlap
    ):
        return chunker_orch
    return ChunkerOrchestrator(
        chunker_orch.registry,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


# =====================================================================
# MySQL document registration helper
# =====================================================================

# Map file extensions to the document.type_fichier values.
_EXT_TO_TYPE: dict[str, str] = {
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".doc": "DOCX",
    ".txt": "TXT",
    ".html": "HTML",
    ".htm": "HTML",
    ".md": "MD",
    ".csv": "CSV",
    ".json": "JSON",
    ".xlsx": "XLSX",
}


def _dsn_from_env() -> str | None:
    """Build a MySQL DSN from individual ``GMAO_DB_*`` env vars.

    Mirrors ``MySQLStorage._dsn_from_env`` so that the ingest layer
    does not depend on the storage strategy for basic DB access.
    """
    host = os.getenv("GMAO_DB_HOST")
    user = os.getenv("GMAO_DB_USER")
    database = os.getenv("GMAO_DB_NAME")
    if not all((host, user, database)):
        return None
    password = os.getenv("GMAO_DB_PASSWORD", "")
    port = os.getenv("GMAO_DB_PORT", "3306")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?$")


def _increment_version(version: str) -> str:
    """Return the next document version for a re-ingestion.

    Numeric versions are bumped on the major part ("1.0" -> "2.0",
    "3" -> "4").  Non-numeric versions are suffixed with ".1"
    ("rc1" -> "rc1.1").
    """
    match = _VERSION_RE.match(version.strip())
    if not match:
        return f"{version}.1"
    major = int(match.group(1)) + 1
    minor = match.group(2)
    if minor is not None:
        return f"{major}.{minor}"
    return str(major)


def _check_equipment_exists(engine: object, id_equipement: int | None) -> None:
    """Raise a friendly ForeignKeyError when the equipment is unknown.

    ``documents.id_equipement`` is constrained by ``fk_document_equipement``
    toward ``equipements``.  Instead of leaking the raw SQL integrity error
    to the API caller, check up-front and provide a clear message.
    """
    if id_equipement is None:
        return
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id_equipement FROM equipements "
                "WHERE id_equipement = :id"
            ),
            {"id": id_equipement},
        ).fetchone()
    if row is None:
        raise ForeignKeyError(
            f"L'équipement id_equipement={id_equipement} n'existe pas dans la "
            f"table 'equipements' (id_equipement doit être un ID existant)."
        )


def _find_document_by_identifier(
    engine: object,
    identifier: str,
) -> dict | None:
    """Return ``{id_document, version}`` for a document matching an identity.

    Pipeline documents are matched on ``chemin_fichier``, which for
    database ingests holds the ``database.table`` identity.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id_document, version "
                "FROM documents WHERE chemin_fichier = :ident "
                "ORDER BY id_document DESC LIMIT 1"
            ),
            {"ident": identifier},
        ).fetchone()
    if row is None:
        return None
    return {"id_document": row[0], "version": row[1]}


def _build_database_source_config(
    request: IngestDatabaseRequest,
) -> tuple[dict, str]:
    """Build the loader config + document identity for a database ingest.

    The MySQL loader requires *exactly one* of ``table``/``query``.  A
    custom ``query`` is meant to override ``table``, so when it is
    provided the ``table`` key is dropped from the config.

    The identity (used to match re-ingestions by ``chemin_fichier``)
    stays ``database.table``.
    """
    table = request.table
    config: dict = {
        "driver": request.driver,
        "host": request.host,
        "port": request.port,
        "database": request.database,
        "user": request.user,
        "password": request.password,
    }
    if request.query:
        config["query"] = request.query
    else:
        config["table"] = table
    identity = f"{request.database}.{table}"
    return config, identity


def _create_document(
    engine: object,
    source_name: str,
    source_path: str | None,
    *,
    id_equipement: int | None = None,
    file_size: int = 0,
    titre: str | None = None,
    type_fichier: str | None = None,
    version: str = "1.0",
    description: str | None = None,
    is_database: bool = False,
    source_identifier: str | None = None,
) -> int:
    """Insert a ``documents`` row in MySQL and return ``id_document``.

    The storage strategies (MySQL + Qdrant) require every chunk to carry
    ``id_document`` in its metadata.  This function is called once per
    ingested file, right after chunking, so that the IDs can be injected
    into every chunk before the embed → store steps.

    All editable ``documents`` columns are filled: ``titre``,
    ``nom_fichier``, ``type_fichier``, ``chemin_fichier``, ``taille``,
    ``version``, ``description`` and ``id_equipement``.

    For database sources (``is_database=True``):
    - there is no file extension, so ``type_fichier`` is stored as
      ``NULL`` unless an explicit ``type_fichier`` override is provided;
    - ``chemin_fichier`` holds the ``source_identifier`` (the
      ``database.table`` identity) used to detect re-ingestions.
    """
    ext = os.path.splitext(source_name)[1].lower() if source_name else ""
    if is_database:
        doc_type = type_fichier or None
    else:
        doc_type = type_fichier or _EXT_TO_TYPE.get(ext, "TXT")
    title = titre or (os.path.splitext(source_name)[0] if source_name else "untitled")
    chemin = source_path or source_identifier or source_name

    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO documents "
                "(titre, nom_fichier, type_fichier, chemin_fichier, taille, "
                " version, description, id_equipement) "
                "VALUES (:titre, :nom, :type, :chemin, :taille, "
                " :version, :description, :equip)"
            ),
            {
                "titre": title,
                "nom": source_name,
                "type": doc_type,
                "chemin": chemin,
                "taille": file_size,
                "version": version,
                "description": description,
                "equip": id_equipement,
            },
        )
        return int(result.lastrowid)


# =====================================================================
# Pipeline helper
# =====================================================================

async def _ingest_source(  # noqa: C901 — complex but linear pipeline
    source: object,
    *,
    data_source_orch: object,
    parser_orch: object,
    chunker_orch: object,
    embedding_orch: object,
    storage_orch: object,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    id_equipement: int | None = None,
    titre: str | None = None,
    source_type: str | None = None,
    version: str = "1.0",
    description: str | None = None,
    is_database: bool = False,
    source_identifier: str | None = None,
) -> IngestResult:
    """Run the full ingestion pipeline: load → parse → chunk → embed → store.

    This is the core function shared by all ingestion endpoints.
    It catches exceptions per-file to allow partial success in batch mode.

    Between chunking and embedding, a ``document`` row is created in MySQL
    and ``id_document`` / ``id_equipement`` are injected into each chunk's
    metadata — this is required by both MySQLStorage and QdrantStorage.
    """
    start = time.perf_counter()
    doc_name = str(source)

    try:
        # --- Step 1: Load ---
        doc = data_source_orch.load(source)

        # --- Step 2: Parse ---
        parsed = parser_orch.parse(doc)

        # --- Step 3: Chunk ---
        eff_chunk_size, eff_chunk_overlap = _resolve_chunk_options(
            doc.source_type, chunk_size, chunk_overlap,
        )
        chunker = _resolve_chunker(
            chunker_orch, eff_chunk_size, eff_chunk_overlap,
        )
        chunks = chunker.chunk(parsed)

        # --- Step 3.5: Register document in MySQL + inject IDs ---
        # MySQLStorage requires id_document or id_panne in chunk metadata.
        # QdrantStorage requires id_chunk (generated by MySQLStorage).
        # We create the document row now so that MySQLStorage can link
        # chunks to it during its save() step.
        load_dotenv()
        dsn = os.getenv("MYSQL_DSN") or _dsn_from_env()
        if dsn:
            engine = create_engine(dsn)
            _check_equipment_exists(engine, id_equipement)
            file_size = doc.size if doc.size else 0
            # type_fichier: prefer the explicit form field, else derive it
            # from the loader-detected source type (doc.source_type) so a
            # CSV/JSON/XLSX file is never stored as "TXT".
            ingest_type = source_type
            if not is_database and not source_type:
                ingest_type = (doc.source_type or "").strip().upper() or None
            id_document = _create_document(
                engine,
                doc.source_name,
                str(doc.source_path) if doc.source_path else None,
                id_equipement=id_equipement,
                file_size=file_size,
                titre=titre,
                type_fichier=ingest_type,
                version=version,
                description=description,
                is_database=is_database,
                source_identifier=source_identifier,
            )
            for chunk in chunks:
                chunk.metadata["id_document"] = id_document
                if id_equipement is not None:
                    chunk.metadata["id_equipement"] = id_equipement

        # --- Step 4: Embed ---
        embeddings = embedding_orch.embed(chunks)

        # --- Step 5: Store ---
        storage_orch.save(chunks, embeddings)

        elapsed = (time.perf_counter() - start) * 1000
        return IngestResult(
            status="ok",
            document_name=doc.source_name,
            chunks_count=len(chunks),
            duration_ms=round(elapsed, 2),
        )

    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error("Ingestion failed for %s: %s", doc_name, exc)
        return IngestResult(
            status="error",
            document_name=doc_name,
            chunks_count=0,
            duration_ms=round(elapsed, 2),
            error=str(exc),
        )


# =====================================================================
# POST /api/v1/ingest/file — Single file upload
# =====================================================================

@router.post(
    "/file",
    response_model=IngestResponse,
    summary="Ingest a single file",
    description="Upload a file and run the full ingestion pipeline (load → parse → chunk → embed → store).",
)
async def ingest_file(
    _token: Annotated[str, Depends(verify_api_key)],
    file: UploadFile = File(..., description="File to ingest"),
    id_equipement: Annotated[int | None, Form()] = None,
    chunk_size: Annotated[int | None, Form()] = None,
    chunk_overlap: Annotated[int | None, Form()] = None,
    titre: Annotated[str | None, Form()] = None,
    source_type: Annotated[str | None, Form()] = None,
    version: Annotated[str, Form()] = "1.0",
    description: Annotated[str | None, Form()] = None,
    data_source_orch = Depends(get_data_source_orchestrator),
    parser_orch = Depends(get_parser_orchestrator),
    chunker_orch = Depends(get_chunker_orchestrator),
    embedding_orch = Depends(get_embedding_orchestrator),
    storage_orch = Depends(get_storage_orchestrator),
) -> IngestResponse:
    """Upload a file and ingest it through the full pipeline.

    The file is saved to a temporary location, processed, and deleted
    after ingestion.  Supported formats are determined by the data
    source layer (PDF, DOCX, TXT, HTML, CSV, JSON, XLSX, Markdown).

    All editable fields of the ``documents`` table can be provided as
    multipart form fields: ``titre``, ``source_type`` (→ ``type_fichier``),
    ``version``, ``description``, ``id_equipement``, plus the chunking
    options ``chunk_size`` / ``chunk_overlap``.
    """
    suffix = os.path.splitext(file.filename or "upload")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await _ingest_source(
            tmp_path,
            data_source_orch=data_source_orch,
            parser_orch=parser_orch,
            chunker_orch=chunker_orch,
            embedding_orch=embedding_orch,
            storage_orch=storage_orch,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            id_equipement=id_equipement,
            titre=titre,
            source_type=source_type,
            version=version,
            description=description,
        )
    finally:
        os.unlink(tmp_path)

    status = "ok" if result.status == "ok" else "partial"
    return IngestResponse(
        status=status,
        results=[result],
        total_files=1,
        success_count=1 if result.status == "ok" else 0,
        error_count=1 if result.status == "error" else 0,
    )


# =====================================================================
# POST /api/v1/ingest/database — MySQL ingestion
# =====================================================================

@router.post(
    "/database",
    response_model=IngestResponse,
    summary="Ingest from MySQL",
    description="Load data from a MySQL table or custom query and run the full ingestion pipeline.",
)
async def ingest_database(
    request: IngestDatabaseRequest,
    _token: Annotated[str, Depends(verify_api_key)],
    data_source_orch = Depends(get_data_source_orchestrator),
    parser_orch = Depends(get_parser_orchestrator),
    chunker_orch = Depends(get_chunker_orchestrator),
    embedding_orch = Depends(get_embedding_orchestrator),
    storage_orch = Depends(get_storage_orchestrator),
) -> IngestResponse:
    """Ingest data from a MySQL source.

    The database connection parameters are provided in the request body.
    A custom SQL query (``request.query``) overrides the simple
    table-based loading: only the query is then sent to the loader,
    which requires *exactly one* of ``table``/``query``.

    Re-ingestion: if a document whose ``database.table`` identity already
    exists in ``documents``, it is deleted together with its chunks
    (MySQL + Qdrant) before the new ingestion, and the document version
    is incremented.
    """
    source_config, identity = _build_database_source_config(request)

    version = request.version

    try:
        dsn = os.getenv("MYSQL_DSN") or _dsn_from_env()
        if dsn:
            engine = create_engine(dsn, pool_pre_ping=True)
            try:
                existing = _find_document_by_identifier(engine, identity)
                if existing is not None:
                    delete_document_by_id(engine, existing["id_document"])
                    version = _increment_version(existing["version"])
                    logger.info(
                        "Re-ingesting '%s': removed document %s "
                        "(version %s -> %s).",
                        identity,
                        existing["id_document"],
                        existing["version"],
                        version,
                    )
            finally:
                engine.dispose()
    except Exception as exc:
        logger.warning(
            "Re-ingestion check failed for '%s' (continuing ingest): %s",
            identity,
            exc,
        )

    result = await _ingest_source(
        source_config,
        data_source_orch=data_source_orch,
        parser_orch=parser_orch,
        chunker_orch=chunker_orch,
        embedding_orch=embedding_orch,
        storage_orch=storage_orch,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        titre=request.titre or identity,
        source_type=request.source_type,
        version=version,
        description=request.description,
        is_database=True,
        source_identifier=identity,
    )

    status = "ok" if result.status == "ok" else "partial"
    return IngestResponse(
        status=status,
        results=[result],
        total_files=1,
        success_count=1 if result.status == "ok" else 0,
        error_count=1 if result.status == "error" else 0,
    )


# =====================================================================
# POST /api/v1/ingest/files — Batch ingestion
# =====================================================================

@router.post(
    "/files",
    response_model=IngestResponse,
    summary="Batch ingest multiple files",
    description="Ingest multiple files from their absolute paths on the server.",
)
async def ingest_files(
    request: IngestMultipleRequest,
    _token: Annotated[str, Depends(verify_api_key)],
    data_source_orch = Depends(get_data_source_orchestrator),
    parser_orch = Depends(get_parser_orchestrator),
    chunker_orch = Depends(get_chunker_orchestrator),
    embedding_orch = Depends(get_embedding_orchestrator),
    storage_orch = Depends(get_storage_orchestrator),
) -> IngestResponse:
    """Ingest multiple files in batch.

    Each file is processed independently — a failure on one file does
    not prevent the others from being ingested.
    """
    results: list[IngestResult] = []

    for path in request.paths:
        result = await _ingest_source(
            path,
            data_source_orch=data_source_orch,
            parser_orch=parser_orch,
            chunker_orch=chunker_orch,
            embedding_orch=embedding_orch,
            storage_orch=storage_orch,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            id_equipement=request.id_equipement,
            titre=request.titre,
            source_type=request.source_type,
            version=request.version,
            description=request.description,
        )
        results.append(result)

    success_count = sum(1 for r in results if r.status == "ok")
    error_count = sum(1 for r in results if r.status == "error")

    if error_count == 0:
        status = "ok"
    elif success_count == 0:
        status = "error"
    else:
        status = "partial"

    return IngestResponse(
        status=status,
        results=results,
        total_files=len(results),
        success_count=success_count,
        error_count=error_count,
    )

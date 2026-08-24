"""Public API for file-based data sources."""

from __future__ import annotations

from pathlib import Path

from app.data_sources.file.csv_loader import CSVLoader
from app.data_sources.file.docx_loader import DOCXLoader
from app.data_sources.file.file_source import FileSource
from app.data_sources.file.html_loader import HTMLLoader
from app.data_sources.file.json_loader import JSONLoader
from app.data_sources.file.markdown_loader import MarkdownLoader
from app.data_sources.file.pdf_loader import PDFLoader
from app.data_sources.file.txt_loader import TXTLoader
from app.data_sources.file.xlsx_loader import XLSXLoader
from app.exceptions import UnsupportedFileFormatError
from app.models.document import SourceDocument

__all__ = [
    "FileSource",
    "TXTLoader",
    "MarkdownLoader",
    "CSVLoader",
    "JSONLoader",
    "HTMLLoader",
    "DOCXLoader",
    "PDFLoader",
    "XLSXLoader",
    "load_file",
    "get_loader_class",
]

_EXTENSION_LOADER_MAP: dict[str, type[FileSource]] = {
    ".txt": TXTLoader,
    ".md": MarkdownLoader,
    ".markdown": MarkdownLoader,
    ".csv": CSVLoader,
    ".json": JSONLoader,
    ".html": HTMLLoader,
    ".htm": HTMLLoader,
    ".docx": DOCXLoader,
    ".pdf": PDFLoader,
    ".xlsx": XLSXLoader,
}


def get_loader_class(path: str | Path) -> type[FileSource]:
    """Return the loader class for a given path."""
    normalized = Path(path).suffix.lower()
    if not normalized:
        raise UnsupportedFileFormatError(
            message=f"File '{path}' has no extension and cannot be resolved."
        )

    loader_cls = _EXTENSION_LOADER_MAP.get(normalized)
    if loader_cls is None:
        raise UnsupportedFileFormatError(
            message=(
                f"Unsupported file format for '{path}'. "
                f"Supported extensions: {', '.join(sorted(_EXTENSION_LOADER_MAP))}."
            )
        )
    return loader_cls


def load_file(path: str | Path) -> SourceDocument:
    """Load any supported file and return a normalized document."""
    loader_cls = get_loader_class(path)
    return loader_cls(path).read()

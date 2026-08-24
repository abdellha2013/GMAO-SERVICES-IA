"""Concrete storage strategies available to the registry."""
from __future__ import annotations

from .mysql_storage import MySQLStorage
from .qdrant_storage import QdrantStorage

ALL_STRATEGIES = (MySQLStorage, QdrantStorage)

__all__ = ["MySQLStorage", "QdrantStorage", "ALL_STRATEGIES"]

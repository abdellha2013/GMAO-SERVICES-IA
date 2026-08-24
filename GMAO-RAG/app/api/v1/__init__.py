"""Versioned API router (v1).

All ``/api/v1/*`` endpoints are mounted under this package.  Each module
owns one domain (rag, ingest, documents, health) and registers its
routes on the shared ``router``.
"""

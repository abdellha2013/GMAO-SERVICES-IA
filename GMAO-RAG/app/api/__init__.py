"""REST API layer for the GMAO-RAG pipeline.

This package exposes the RAG pipeline as HTTP endpoints consumed by the
Laravel backend (or any other HTTP client).  It adds no business logic —
it is a thin adapter between HTTP requests and the existing orchestrators
in ``app.retrieval``, ``app.reranker``, ``app.llm``, etc.

Typical usage::

    uvicorn app.api.main:app --host 0.0.0.0 --port 8000
"""

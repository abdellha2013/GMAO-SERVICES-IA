"""OpenAI-based LLM generation strategy."""
from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from threading import RLock
from typing import Any, ClassVar

from app.exceptions import (
    LLMConnectionError,
    LLMGenerationError,
    LLMModelError,
    LLMRateLimitError,
    LLMValidationError,
)
from app.models.llm import Citation, LLMResponse
from app.models.reranking import RankedChunk
from app.llm.base import LLMStrategy

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "Tu es un assistant expert en maintenance industrielle (GMAO). "
    "Réponds à la question en te basant UNIQUEMENT sur le contexte fourni. "
    "Si le contexte ne contient pas assez d'information, dis-le explicitement. "
    "Cite tes sources en mentionnant [source_name]."
)

DEFAULT_USER_TEMPLATE = (
    "## Contexte\n{context}\n\n## Question\n{query}"
)


def _build_context(candidates: Sequence[RankedChunk]) -> str:
    parts: list[str] = []
    for c in candidates:
        parts.append(
            f"[{c.rank}] {c.source_name} (score: {c.rerank_score:.3f})\n{c.content}"
        )
    return "\n\n".join(parts)


class OpenAILLM(LLMStrategy):
    """Generate answers using the OpenAI Chat Completions API.

    The client is lazily loaded on the first call to :meth:`generate` and
    cached at class level so subsequent calls reuse the same instance.
    """

    name = "openai"

    DEFAULT_MODEL_NAME: ClassVar[str] = "gpt-4o-mini"

    _client_cache: ClassVar[dict[str, Any]] = {}
    _cache_lock: ClassVar[RLock] = RLock()
    _key_locks: ClassVar[dict[str, RLock]] = {}

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        user_template: str | None = None,
        **_: object,
    ) -> None:
        import os
        from dotenv import load_dotenv

        load_dotenv()

        self._api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        if not self._api_key:
            raise LLMValidationError(
                message="api_key is required (pass it or set OPENAI_API_KEY env var).",
            )

        self._model_name = (model_name or os.getenv("LLM_MODEL_NAME", self.DEFAULT_MODEL_NAME)).strip()
        if not self._model_name:
            raise LLMValidationError(message="model_name must be a non-empty string.")

        self._base_url = (base_url or os.getenv("LLM_BASE_URL", "")).strip() or None
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._user_template = user_template or DEFAULT_USER_TEMPLATE

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def _cache_key(self) -> str:
        base = self._base_url or ""
        return f"{self._api_key[:8]}...|{self._model_name}|{base}"

    def preload(self) -> Any:
        """Initialise le client HTTP OpenAI (idempotent, cache de classe).

        Appelé au démarrage pour retirer la latence de création du client
        du premier appel ``generate``.
        """
        return self._get_client()

    def _get_client(self) -> Any:
        key = self._cache_key()

        cached = self._client_cache.get(key)
        if cached is not None:
            return cached

        with self._cache_lock:
            key_lock = self._key_locks.setdefault(key, RLock())

        with key_lock:
            cached = self._client_cache.get(key)
            if cached is not None:
                return cached

            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMModelError(
                    message="openai package is required for OpenAILLM.",
                    details={"dependency": "openai"},
                    original=exc,
                ) from exc

            try:
                kwargs: dict[str, Any] = {"api_key": self._api_key}
                if self._base_url:
                    kwargs["base_url"] = self._base_url
                client = OpenAI(**kwargs)
            except Exception as exc:
                raise LLMConnectionError(
                    message=f"Unable to create OpenAI client.",
                    details={"model_name": self._model_name},
                    original=exc,
                ) from exc

            self._client_cache[key] = client
            logger.info("OpenAI client created (model=%s).", self._model_name)
            return client

    @classmethod
    def clear_client_cache(cls) -> None:
        """Clear cached client instances; mainly intended for isolated tests."""
        with cls._cache_lock:
            cls._client_cache.clear()
            cls._key_locks.clear()

    def supports(self, query: str, candidates: Sequence[RankedChunk]) -> bool:
        return (
            isinstance(query, str)
            and bool(query.strip())
            and isinstance(candidates, Sequence)
            and not isinstance(candidates, (str, bytes))
            and all(isinstance(c, RankedChunk) for c in candidates)
        )

    def generate(
        self,
        query: str,
        candidates: Sequence[RankedChunk],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> LLMResponse:
        if not isinstance(query, str) or not query.strip():
            raise LLMValidationError(message="query must be a non-empty string.")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise LLMValidationError(message="candidates must be a sequence of RankedChunk.")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise LLMValidationError(message="max_tokens must be a positive integer.")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise LLMValidationError(message="temperature must be a number.")
        if not candidates:
            return LLMResponse(
                answer="Aucun contexte disponible pour répondre à cette question.",
                query=query,
                strategy_name=self.name,
                model_name=self._model_name,
            )

        for i, c in enumerate(candidates):
            if not isinstance(c, RankedChunk):
                raise LLMValidationError(
                    message="candidates must contain only RankedChunk objects.",
                    details={"index": i, "received_type": type(c).__name__},
                )

        client = self._get_client()
        context = _build_context(candidates)
        user_content = self._user_template.format(context=context, query=query.strip())

        t0 = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            exc_str = str(exc).lower()
            if "rate" in exc_str or "429" in exc_str or "quota" in exc_str:
                raise LLMRateLimitError(
                    message="OpenAI rate limit or quota exceeded.",
                    details={"model_name": self._model_name},
                    original=exc,
                ) from exc
            if "connection" in exc_str or "timeout" in exc_str or "network" in exc_str:
                raise LLMConnectionError(
                    message="Cannot connect to OpenAI API.",
                    details={"model_name": self._model_name},
                    original=exc,
                ) from exc
            raise LLMGenerationError(
                message="OpenAI chat completion failed.",
                details={"model_name": self._model_name},
                original=exc,
            ) from exc

        duration_ms = (time.perf_counter() - t0) * 1000

        if not response.choices:
            raise LLMGenerationError(
                message="OpenAI returned an empty response (no choices).",
                details={"model_name": self._model_name},
            )

        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            answer = "Le modèle n'a pas généré de réponse. Essayez de reformuler votre question."
        usage = response.usage
        tokens_input = usage.prompt_tokens if usage else 0
        tokens_output = usage.completion_tokens if usage else 0

        citations = tuple(
            Citation(
                chunk_id=c.chunk_id,
                source_name=c.source_name,
                source_type=c.source_type,
                rerank_score=c.rerank_score,
            )
            for c in candidates
        )

        logger.info(
            "OpenAI generation done (model=%s, tokens=%d/%d, %.0fms).",
            self._model_name, tokens_input, tokens_output, duration_ms,
        )

        return LLMResponse(
            answer=answer.strip(),
            query=query,
            strategy_name=self.name,
            model_name=self._model_name,
            citations=citations,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            duration_ms=duration_ms,
            metadata={
                "candidates_count": len(candidates),
                "finish_reason": response.choices[0].finish_reason,
            },
        )

"""High-level orchestration for LLM generation."""
from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from app.exceptions import (
    GMAOError,
    LLMValidationError,
    LLMGenerationError,
)
from app.models.llm import LLMResponse
from app.models.reranking import RankedChunk
from app.llm.base import LLMStrategy
from app.llm.registry import LLMRegistry

logger = logging.getLogger(__name__)


class LLMOrchestrator:
    """Resolve an LLM strategy and generate a response from ranked candidates.

    The orchestrator validates inputs, resolves the strategy from the
    registry, instantiates it with stored options, and delegates the
    actual generation.
    """

    def __init__(
        self,
        registry: LLMRegistry,
        *,
        strategy_name: str | None = None,
        default_max_tokens: int = 1024,
        default_temperature: float = 0.3,
        max_candidates: int = 10,
        **strategy_options: Any,
    ) -> None:
        if not isinstance(registry, LLMRegistry):
            raise LLMValidationError(
                message="registry must be a LLMRegistry instance.",
                details={"received_type": type(registry).__name__},
            )
        resolved_strategy = (
            strategy_name
            if isinstance(strategy_name, str) and strategy_name.strip()
            else os.getenv("LLM_STRATEGY", "gemini")
        )
        if not isinstance(resolved_strategy, str) or not resolved_strategy.strip():
            raise LLMValidationError(message="strategy_name must be a non-empty string.")
        if not isinstance(default_max_tokens, int) or isinstance(default_max_tokens, bool) or default_max_tokens <= 0:
            raise LLMValidationError(message="default_max_tokens must be a positive integer.")
        if isinstance(default_temperature, bool) or not isinstance(default_temperature, (int, float)):
            raise LLMValidationError(message="default_temperature must be a number.")
        if not isinstance(max_candidates, int) or isinstance(max_candidates, bool) or max_candidates <= 0:
            raise LLMValidationError(message="max_candidates must be a positive integer.")

        self._registry = registry
        self._strategy_name = resolved_strategy.strip().lower()
        self._default_max_tokens = default_max_tokens
        self._default_temperature = default_temperature
        self._max_candidates = max_candidates
        self._strategy_options = dict(strategy_options)

    @property
    def registry(self) -> LLMRegistry:
        return self._registry

    @property
    def strategy_name(self) -> str:
        return self._strategy_name

    def warmup(self) -> str:
        """Initialise le client de la stratégie LLM par défaut (idempotent).

        Appelé au démarrage pour sortir la création du client HTTP des
        temps de réponse.  Échoue proprement (exception) si la clé API
        configurée est absente — l'appelant décide de tolérer ou non.

        Returns
        -------
        str
            Le nom de la stratégie préchargée.
        """
        strategy_cls = self._registry.get(self._strategy_name)
        strategy: LLMStrategy = strategy_cls(**self._strategy_options)
        preload = getattr(strategy, "preload", None)
        if callable(preload):
            preload()
        return strategy.name

    def generate(
        self,
        query: str,
        candidates: Sequence[RankedChunk],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        strategy_name: str | None = None,
    ) -> LLMResponse:
        if not isinstance(query, str) or not query.strip():
            raise LLMValidationError(message="query must be a non-empty string.")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            raise LLMValidationError(message="candidates must be a sequence of RankedChunk.")
        if max_tokens is not None and (isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0):
            raise LLMValidationError(message="max_tokens must be a positive integer.")
        if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float))):
            raise LLMValidationError(message="temperature must be a number.")
        if strategy_name is not None and (not isinstance(strategy_name, str) or not strategy_name.strip()):
            raise LLMValidationError(message="strategy_name must be a non-empty string or None.")

        effective_max_tokens = max_tokens or self._default_max_tokens
        effective_temperature = temperature if temperature is not None else self._default_temperature
        name = (strategy_name or self._strategy_name).strip().lower()

        truncated = list(candidates[: self._max_candidates])

        if not truncated:
            logger.info("No candidates to generate from — returning default response.")
            return LLMResponse(
                answer="Aucun contexte disponible pour répondre à cette question.",
                query=query,
                strategy_name=name,
                model_name="none",
            )

        try:
            strategy_cls = self._registry.get(name)
            strategy: LLMStrategy = strategy_cls(**self._strategy_options)

            if not strategy.supports(query, truncated):
                raise LLMValidationError(
                    message="LLM strategy does not support these inputs.",
                    details={"strategy": name},
                )

            results = strategy.generate(
                query, truncated,
                max_tokens=effective_max_tokens,
                temperature=effective_temperature,
            )
        except GMAOError:
            raise
        except Exception as exc:
            raise LLMGenerationError(
                message="LLM strategy execution failed.",
                details={"strategy_name": name},
                original=exc,
            ) from exc

        if not isinstance(results, LLMResponse):
            raise LLMValidationError(
                message="generate() must return an LLMResponse.",
                details={"received_type": type(results).__name__},
            )

        return results

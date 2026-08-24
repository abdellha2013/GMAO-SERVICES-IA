"""Exceptions for the LLM layer of the RAG pipeline (``app.llm``).

Hierarchy::

    GMAOError
    └── LLMError
        ├── LLMValidationError
        ├── LLMConnectionError
        ├── LLMRateLimitError
        ├── LLMModelError
        ├── LLMGenerationError
        ├── LLMStrategyNotRegisteredError
        └── InvalidLLMStrategyError
"""
from __future__ import annotations

from .base_exception import GMAOError


class LLMError(GMAOError):
    """Base class for every exception raised by ``app.llm``."""

    DEFAULT_MESSAGE = "An LLM error occurred."
    DEFAULT_ERROR_CODE = "LLM_ERROR"
    DEFAULT_HTTP_STATUS = 500

    def __init__(self, message: str | None = None, **kwargs: object) -> None:
        super().__init__(
            message=message or self.DEFAULT_MESSAGE,
            error_code=kwargs.pop("error_code", self.DEFAULT_ERROR_CODE),
            http_status=kwargs.pop("http_status", self.DEFAULT_HTTP_STATUS),
            **kwargs,
        )


class LLMValidationError(LLMError):
    """Invalid input supplied to the LLM layer."""

    DEFAULT_MESSAGE = "Invalid LLM input."
    DEFAULT_ERROR_CODE = "LLM_VALIDATION_ERROR"
    DEFAULT_HTTP_STATUS = 400


class LLMConnectionError(LLMError):
    """Cannot reach the LLM provider endpoint."""

    DEFAULT_MESSAGE = "LLM connection failed."
    DEFAULT_ERROR_CODE = "LLM_CONNECTION_ERROR"
    DEFAULT_HTTP_STATUS = 502


class LLMRateLimitError(LLMError):
    """Rate limit or quota exceeded on the LLM provider."""

    DEFAULT_MESSAGE = "LLM rate limit exceeded."
    DEFAULT_ERROR_CODE = "LLM_RATE_LIMIT_ERROR"
    DEFAULT_HTTP_STATUS = 429


class LLMModelError(LLMError):
    """The LLM provider returned an unexpected model error."""

    DEFAULT_MESSAGE = "LLM model error."
    DEFAULT_ERROR_CODE = "LLM_MODEL_ERROR"
    DEFAULT_HTTP_STATUS = 500


class LLMGenerationError(LLMError):
    """The LLM failed to produce a valid response."""

    DEFAULT_MESSAGE = "LLM generation failed."
    DEFAULT_ERROR_CODE = "LLM_GENERATION_ERROR"
    DEFAULT_HTTP_STATUS = 500


class LLMStrategyNotRegisteredError(LLMError):
    """No LLM strategy is registered under the requested name."""

    DEFAULT_MESSAGE = "LLM strategy not registered."
    DEFAULT_ERROR_CODE = "LLM_STRATEGY_NOT_REGISTERED"
    DEFAULT_HTTP_STATUS = 400


class InvalidLLMStrategyError(LLMError):
    """A strategy class does not conform to the ``LLMStrategy`` contract."""

    DEFAULT_MESSAGE = "Invalid LLM strategy."
    DEFAULT_ERROR_CODE = "LLM_INVALID_STRATEGY"
    DEFAULT_HTTP_STATUS = 500

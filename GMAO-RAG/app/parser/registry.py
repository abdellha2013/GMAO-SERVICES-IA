"""
Parser strategy registry.

This module manages the association between source types and parser
strategies.

The registry is responsible only for registering, retrieving,
checking, and removing parser strategies. It does not perform parsing.

Strategy selection and document parsing are handled by the parser
orchestrator.
"""

from __future__ import annotations

from app.exceptions import (
    InvalidStrategyError,
    ParserValidationError,
    ParserStrategyNotRegisteredError,
)
from app.parser.base import ParserStrategy


class ParserRegistry:
    """
    Registry of parser strategies.

    A parser strategy is registered under a normalized source type
    such as ``txt``, ``markdown``, ``html``, ``json`` or ``mysql``.

    The registry stores strategy classes rather than instances.
    The parser orchestrator is responsible for instantiating and
    executing the selected strategy.

    Examples
    --------
    >>> registry = ParserRegistry()
    >>> registry.register(TextParser)
    >>> strategy = registry.get("text")
    """

    def __init__(self) -> None:
        """Initialize an empty parser strategy registry."""
        self._strategies: dict[str, type[ParserStrategy]] = {}

    def _normalize_source_type(self, source_type: str) -> str:
        """
        Validate and normalize a source type.

        Parameters
        ----------
        source_type : str
            Source type used as the registry key.

        Returns
        -------
        str
            Normalized source type.

        Raises
        ------
        ParserValidationError
            If source_type is not a string or is empty.
        """
        if not isinstance(source_type, str):
            raise ParserValidationError(
                "source_type must be a string",
                details={
                    "field": "source_type",
                    "received_type": type(source_type).__name__,
                },
            )

        normalized = source_type.strip().lower()

        if not normalized:
            raise ParserValidationError(
                "source_type must not be empty",
                details={"field": "source_type"},
            )

        return normalized

    def _validate_strategy(
        self,
        strategy: type[ParserStrategy],
    ) -> None:
        """
        Validate a parser strategy class.

        Parameters
        ----------
        strategy : type[ParserStrategy]
            Strategy class to validate.

        Raises
        ------
        InvalidStrategyError
            If strategy is not a class or does not inherit from
            ParserStrategy.
        """
        if not isinstance(strategy, type):
            raise InvalidStrategyError(
                "strategy must be a class",
                details={
                    "received_type": type(strategy).__name__,
                },
            )

        if not issubclass(strategy, ParserStrategy):
            raise InvalidStrategyError(
                "strategy must inherit from ParserStrategy",
                details={
                    "strategy": getattr(
                        strategy,
                        "__name__",
                        type(strategy).__name__,
                    ),
                    "expected_base": "ParserStrategy",
                },
            )

    def register(self, strategy: type[ParserStrategy]) -> None:
        """
        Register a parser strategy.

        A strategy is registered under every source type declared in its
        ``SUPPORTED_SOURCE_TYPES`` class attribute. When a strategy does
        not declare this attribute, the registry falls back to
        ``strategy().name`` as its single source type, preserving
        backward compatibility with single-type strategies.

        Parameters
        ----------
        strategy : type[ParserStrategy]
            ParserStrategy subclass responsible for parsing.

        Raises
        ------
        InvalidStrategyError
            If strategy is not a ParserStrategy subclass.

        ParserValidationError
            If a strategy is already registered for one of the derived
            source types.
        """
        self._validate_strategy(strategy)

        instance = strategy()

        declared_types = getattr(instance, "SUPPORTED_SOURCE_TYPES", None)

        if not declared_types:
            declared_types = {instance.name}

        source_types = {
            self._normalize_source_type(source_type)
            for source_type in declared_types
        }

        for source_type in source_types:
            if source_type in self._strategies:
                existing = self._strategies[source_type]
                raise ParserValidationError(
                    (
                        f"A parser strategy is already registered for "
                        f"source type '{source_type}'"
                    ),
                    details={
                        "source_type": source_type,
                        "existing_strategy": existing.__name__,
                        "new_strategy": strategy.__name__,
                    },
                )

        for source_type in source_types:
            self._strategies[source_type] = strategy

    def get(self, source_type: str) -> type[ParserStrategy]:
        """
        Return the strategy registered for a source type.

        Parameters
        ----------
        source_type : str
            Source type to look up.

        Returns
        -------
        type[ParserStrategy]
            Registered parser strategy class.

        Raises
        ------
        ParserValidationError
            If source_type is invalid.

        ParserStrategyNotRegisteredError
            If no strategy is registered for the source type.
        """
        normalized_type = self._normalize_source_type(source_type)

        try:
            return self._strategies[normalized_type]
        except KeyError:
            raise ParserStrategyNotRegisteredError(
                (
                    f"No parser strategy registered for source type "
                    f"'{normalized_type}'"
                ),
                details={
                    "source_type": normalized_type,
                    "supported_types": self.supported_types(),
                },
            ) from None

    def has(self, source_type: str) -> bool:
        """
        Check whether a strategy is registered.

        ``has()`` is intentionally tolerant: invalid source types
        return False instead of raising an exception.

        Parameters
        ----------
        source_type : str
            Source type to check.

        Returns
        -------
        bool
            True if a strategy is registered, otherwise False.
        """
        if not isinstance(source_type, str):
            return False

        normalized_type = source_type.strip().lower()

        if not normalized_type:
            return False

        return normalized_type in self._strategies

    def unregister(self, source_type: str) -> None:
        """
        Remove a strategy from the registry.

        Parameters
        ----------
        source_type : str
            Source type whose strategy should be removed.

        Raises
        ------
        ParserValidationError
            If source_type is invalid.

        ParserStrategyNotRegisteredError
            If no strategy is registered for the source type.
        """
        normalized_type = self._normalize_source_type(source_type)

        if normalized_type not in self._strategies:
            raise ParserStrategyNotRegisteredError(
                (
                    f"No parser strategy registered for source type "
                    f"'{normalized_type}'"
                ),
                details={
                    "source_type": normalized_type,
                    "supported_types": self.supported_types(),
                },
            )

        del self._strategies[normalized_type]

    def clear(self) -> None:
        """
        Remove all registered parser strategies.

        This operation is mainly useful for tests, isolated parser
        configurations, and controlled registry reinitialization.
        """
        self._strategies.clear()

    def supported_types(self) -> tuple[str, ...]:
        """
        Return all registered source types.

        Returns
        -------
        tuple[str, ...]
            Registered source types sorted alphabetically.
        """
        return tuple(sorted(self._strategies))

    def __contains__(self, source_type: str) -> bool:
        """
        Support the ``in`` operator for source type checks.

        Examples
        --------
        >>> "txt" in registry
        True
        """
        return self.has(source_type)

    def __len__(self) -> int:
        """
        Return the number of registered strategies.

        Returns
        -------
        int
            Number of registered parser strategies.
        """
        return len(self._strategies)


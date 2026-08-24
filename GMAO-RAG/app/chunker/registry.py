"""
Chunker strategy registry.

This module manages the association between source types and chunker
strategies.

The registry is responsible only for registering, retrieving,
checking, and removing chunker strategies.

It does not perform chunking itself.

Strategy selection and document chunking are handled by the
ChunkerOrchestrator.
"""

from __future__ import annotations

from app.exceptions import (
    ChunkerStrategyNotRegisteredError,
    ChunkerValidationError,
    InvalidChunkerStrategyError,
)
from app.chunker.base import ChunkerStrategy


class ChunkerRegistry:
    """
    Registry of chunker strategies.

    A chunker strategy can support one or more source types.

    The registry stores strategy classes rather than instances.
    The ChunkerOrchestrator is responsible for instantiating and
    executing the selected strategy.

    Examples
    --------
    >>> registry = ChunkerRegistry()
    >>> registry.register(RecursiveChunker)
    >>> strategy = registry.get("pdf")
    """

    def __init__(self) -> None:
        """
        Initialize an empty chunker strategy registry.
        """

        self._strategies: dict[
            str,
            type[ChunkerStrategy],
        ] = {}

    # ==========================================================
    # Source Type Validation
    # ==========================================================

    @staticmethod
    def _normalize_source_type(
        source_type: str,
    ) -> str:
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
        ChunkerValidationError
            If source_type is not a string or is empty.
        """

        if not isinstance(source_type, str):

            raise ChunkerValidationError(
                message="source_type must be a string.",
                details={
                    "field": "source_type",
                    "received_type": type(
                        source_type
                    ).__name__,
                },
            )

        normalized = source_type.strip().lower()

        if not normalized:

            raise ChunkerValidationError(
                message="source_type must not be empty.",
                details={
                    "field": "source_type",
                },
            )

        return normalized

    # ==========================================================
    # Strategy Validation
    # ==========================================================

    @staticmethod
    def _validate_strategy(
        strategy: type[ChunkerStrategy],
    ) -> None:
        """
        Validate a chunker strategy class.

        Parameters
        ----------
        strategy : type[ChunkerStrategy]
            Strategy class to validate.

        Raises
        ------
        InvalidChunkerStrategyError
            If strategy is not a valid ChunkerStrategy subclass.
        """

        if not isinstance(strategy, type):

            raise InvalidChunkerStrategyError(
                message="strategy must be a class.",
                details={
                    "received_type": type(
                        strategy
                    ).__name__,
                },
            )

        if not issubclass(
            strategy,
            ChunkerStrategy,
        ):

            raise InvalidChunkerStrategyError(
                message=(
                    "strategy must inherit from "
                    "ChunkerStrategy."
                ),
                details={
                    "strategy": getattr(
                        strategy,
                        "__name__",
                        type(strategy).__name__,
                    ),
                    "expected_base": (
                        "ChunkerStrategy"
                    ),
                },
            )

    # ==========================================================
    # Register
    # ==========================================================

    def register(
        self,
        strategy: type[ChunkerStrategy],
    ) -> None:
        """
        Register a chunker strategy.

        The strategy provides its supported source types through
        the ``source_types`` property.

        A single strategy may therefore be registered for several
        source types.

        Parameters
        ----------
        strategy : type[ChunkerStrategy]
            ChunkerStrategy subclass to register.

        Raises
        ------
        InvalidChunkerStrategyError
            If strategy is not a valid ChunkerStrategy subclass.

        ChunkerValidationError
            If the strategy does not define valid source types or
            if one of its source types is already registered.

        Examples
        --------
        >>> registry.register(RecursiveChunker)
        """

        self._validate_strategy(strategy)

        try:

            instance = strategy()

        except Exception as exc:

            raise InvalidChunkerStrategyError(
                message=(
                    "Unable to instantiate chunker "
                    "strategy."
                ),
                details={
                    "strategy": strategy.__name__,
                },
                original=exc,
            ) from exc

        source_types = instance.source_types

        if not isinstance(
            source_types,
            tuple,
        ):

            raise ChunkerValidationError(
                message=(
                    "strategy.source_types must "
                    "return a tuple of strings."
                ),
                details={
                    "strategy": strategy.__name__,
                    "received_type": type(
                        source_types
                    ).__name__,
                },
            )

        if not source_types:

            raise ChunkerValidationError(
                message=(
                    "A chunker strategy must "
                    "support at least one source type."
                ),
                details={
                    "strategy": strategy.__name__,
                },
            )

        normalized_types: list[str] = []

        for source_type in source_types:

            normalized = self._normalize_source_type(
                source_type
            )

            if normalized in normalized_types:

                raise ChunkerValidationError(
                    message=(
                        "A strategy cannot declare "
                        "the same source type more "
                        "than once."
                    ),
                    details={
                        "strategy": strategy.__name__,
                        "source_type": normalized,
                    },
                )

            normalized_types.append(normalized)

        # ------------------------------------------------------
        # Check conflicts before modifying the registry.
        # This keeps registration atomic.
        # ------------------------------------------------------

        conflicts: dict[
            str,
            str,
        ] = {}

        for source_type in normalized_types:

            if source_type in self._strategies:

                conflicts[source_type] = (
                    self._strategies[
                        source_type
                    ].__name__
                )

        if conflicts:

            raise ChunkerValidationError(
                message=(
                    "One or more source types are "
                    "already registered."
                ),
                details={
                    "strategy": strategy.__name__,
                    "conflicts": conflicts,
                },
            )

        # ------------------------------------------------------
        # Register all source types only after validation
        # has completed successfully.
        # ------------------------------------------------------

        for source_type in normalized_types:

            self._strategies[
                source_type
            ] = strategy

    # ==========================================================
    # Get
    # ==========================================================

    def get(
        self,
        source_type: str,
    ) -> type[ChunkerStrategy]:
        """
        Return the strategy registered for a source type.

        Parameters
        ----------
        source_type : str
            Source type to look up.

        Returns
        -------
        type[ChunkerStrategy]
            Registered chunker strategy class.

        Raises
        ------
        ChunkerValidationError
            If source_type is invalid.

        ChunkerStrategyNotRegisteredError
            If no strategy is registered for the source type.
        """

        normalized_type = self._normalize_source_type(
            source_type
        )

        try:

            return self._strategies[
                normalized_type
            ]

        except KeyError:

            raise ChunkerStrategyNotRegisteredError(
                message=(
                    "No chunker strategy registered "
                    f"for source type '{normalized_type}'."
                ),
                details={
                    "source_type": normalized_type,
                    "supported_types": (
                        self.supported_types()
                    ),
                },
            ) from None

    # ==========================================================
    # Has
    # ==========================================================

    def has(
        self,
        source_type: str,
    ) -> bool:
        """
        Check whether a strategy is registered.

        ``has()`` is intentionally tolerant. Invalid source types
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

        if not isinstance(
            source_type,
            str,
        ):

            return False

        normalized_type = (
            source_type.strip().lower()
        )

        if not normalized_type:

            return False

        return normalized_type in self._strategies

    # ==========================================================
    # Unregister
    # ==========================================================

    def unregister(
        self,
        source_type: str,
    ) -> None:
        """
        Remove the strategy associated with a source type.

        Removing one source type does not remove the same strategy
        from other source types.

        Parameters
        ----------
        source_type : str
            Source type to remove.

        Raises
        ------
        ChunkerValidationError
            If source_type is invalid.

        ChunkerStrategyNotRegisteredError
            If no strategy is registered for the source type.
        """

        normalized_type = self._normalize_source_type(
            source_type
        )

        if normalized_type not in self._strategies:

            raise ChunkerStrategyNotRegisteredError(
                message=(
                    "No chunker strategy registered "
                    f"for source type '{normalized_type}'."
                ),
                details={
                    "source_type": normalized_type,
                    "supported_types": (
                        self.supported_types()
                    ),
                },
            )

        del self._strategies[
            normalized_type
        ]

    # ==========================================================
    # Clear
    # ==========================================================

    def clear(self) -> None:
        """
        Remove all registered chunker strategies.
        """

        self._strategies.clear()

    # ==========================================================
    # Supported Types
    # ==========================================================

    def supported_types(
        self,
    ) -> tuple[str, ...]:
        """
        Return all registered source types.

        Returns
        -------
        tuple[str, ...]
            Registered source types sorted alphabetically.
        """

        return tuple(
            sorted(
                self._strategies
            )
        )

    # ==========================================================
    # Contains
    # ==========================================================

    def __contains__(
        self,
        source_type: str,
    ) -> bool:
        """
        Support the ``in`` operator.

        Examples
        --------
        >>> "pdf" in registry
        True
        """

        return self.has(source_type)

    # ==========================================================
    # Length
    # ==========================================================

    def __len__(self) -> int:
        """
        Return the number of registered source types.

        Returns
        -------
        int
            Number of registered source-type mappings.
        """

        return len(self._strategies)
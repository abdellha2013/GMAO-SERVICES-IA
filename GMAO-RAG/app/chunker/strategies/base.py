"""
Shared base implementation for concrete chunker strategies.

``ChunkerStrategy`` (``app.chunker.base``) defines the abstract
contract every strategy must satisfy. This module goes one step
further and factors out the logic that was previously duplicated,
almost verbatim, across ``RecursiveChunker``, ``MarkdownChunker`` and
``StructuredChunker``:

- validating ``chunk_size`` / ``chunk_overlap`` (including the
  ``bool`` guard, since ``bool`` is a subclass of ``int`` in Python);
- computing overlap between consecutive text pieces from the
  *original*, pre-overlap piece, so the overlap window stays bounded
  instead of compounding chunk after chunk.

Centralizing this here means a fix applied once benefits every
strategy that inherits from ``BaseChunkerStrategy``, instead of
having to be reproduced (and potentially forgotten) in each strategy
individually.
"""

from __future__ import annotations

import logging

from app.chunker.base import ChunkerStrategy
from app.exceptions import ChunkSizeError

logger = logging.getLogger(__name__)


class BaseChunkerStrategy(ChunkerStrategy):
    """
    Common behavior shared by concrete chunker strategies.

    Parameters
    ----------
    chunk_size : int, default=1000
        Maximum target size of a chunk, measured in characters.

    chunk_overlap : int, default=100
        Number of characters that may overlap between consecutive
        chunks.

    Raises
    ------
    ChunkSizeError
        If ``chunk_size`` or ``chunk_overlap`` is invalid.
    """

    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 100

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._validate_chunk_configuration(chunk_size, chunk_overlap)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    # ==========================================================
    # Configuration validation
    # ==========================================================

    @staticmethod
    def _validate_chunk_configuration(
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        """
        Validate ``chunk_size`` / ``chunk_overlap``.

        Parameters
        ----------
        chunk_size : int
            Maximum target chunk size.

        chunk_overlap : int
            Desired overlap between consecutive chunks.

        Raises
        ------
        ChunkSizeError
            If either value has the wrong type or an invalid value.
            ``bool`` is explicitly rejected even though it is a
            subclass of ``int`` in Python, otherwise
            ``chunk_size=True`` would silently be accepted as ``1``.
        """

        if (
            isinstance(chunk_size, bool)
            or not isinstance(chunk_size, int)
        ):
            raise ChunkSizeError(
                message="chunk_size must be an integer.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if chunk_size <= 0:
            raise ChunkSizeError(
                message="chunk_size must be greater than zero.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if (
            isinstance(chunk_overlap, bool)
            or not isinstance(chunk_overlap, int)
        ):
            raise ChunkSizeError(
                message="chunk_overlap must be an integer.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if chunk_overlap < 0:
            raise ChunkSizeError(
                message="chunk_overlap cannot be negative.",
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

        if chunk_overlap >= chunk_size:
            raise ChunkSizeError(
                message=(
                    "chunk_overlap must be smaller than chunk_size."
                ),
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )

    # ==========================================================
    # Shared overlap logic
    # ==========================================================

    def _apply_bounded_overlap(
        self,
        pieces: list[str],
        *,
        get_overlap,
        combine,
        skip_overlap=None,
    ) -> list[str]:
        """
        Apply overlap between consecutive pieces without drifting.

        The overlap for piece ``i`` is always computed from
        ``pieces[i - 1]`` — the *original*, not-yet-combined piece —
        never from the already-combined result of the previous
        iteration. This is what keeps the overlap bounded to roughly
        ``chunk_overlap`` characters between two consecutive chunks,
        instead of accumulating the whole document by the end (see
        ``FIX_CHUNKER_MODULE.md`` §3 for the reproduced bug).

        Parameters
        ----------
        pieces : list[str]
            Raw, non-overlapped pieces in order.

        get_overlap : Callable[[str], str]
            Extracts the trailing overlap window from the original
            previous piece.

        combine : Callable[[str, str], str]
            Combines the overlap with the current piece into a
            candidate chunk.

        skip_overlap : Callable[[str], bool] | None
            Optional predicate on the current piece; when it returns
            True, overlap is not applied to that piece (e.g. a
            Markdown chunk starting with a heading).

        Returns
        -------
        list[str]
            Pieces with bounded contextual overlap applied.
        """

        if self.chunk_overlap <= 0 or len(pieces) <= 1:
            return pieces

        result: list[str] = [pieces[0]]

        for index in range(1, len(pieces)):

            previous_original = pieces[index - 1]
            current = pieces[index]

            if skip_overlap is not None and skip_overlap(current):
                result.append(current)
                continue

            overlap = get_overlap(previous_original)

            if not overlap:
                result.append(current)
                continue

            candidate = combine(overlap, current)

            if len(candidate) <= self.chunk_size:
                result.append(candidate)
            else:
                result.append(current)

        return result

    @staticmethod
    def _log_discarded_empty_piece(
        source_name: str,
        strategy_name: str,
    ) -> None:
        """
        Log a warning when an empty piece is discarded.

        Empty pieces are filtered out rather than turned into
        ``Chunk`` objects (an empty ``Chunk.content`` is rejected by
        the model anyway). This is logged so an unexpected empty
        piece — potentially a sign of a bug upstream in parsing —
        does not pass by completely unnoticed.

        Parameters
        ----------
        source_name : str
            Name of the source document being chunked.

        strategy_name : str
            Name of the strategy performing the chunking.
        """

        logger.warning(
            "Discarded an empty chunk while chunking '%s' with the "
            "'%s' strategy.",
            source_name,
            strategy_name,
        )

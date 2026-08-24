"""
Recursive chunker strategy.

This module implements a recursive text chunking strategy for
documents whose content is primarily textual.

The strategy is designed for:

- plain text;
- PDF extracted text;
- DOCX extracted text;
- HTML extracted text;
- other text-oriented ParsedDocument instances.

The strategy recursively attempts to split text using increasingly
fine-grained separators while trying to keep each chunk within the
configured size.

Pipeline:

    ParsedDocument
        ↓
    RecursiveChunker
        ↓
    list[Chunk]
"""

from __future__ import annotations

from collections.abc import Iterable

from app.exceptions import (
    ChunkerValidationError,
    ChunkingError,
)
from app.models.chunk import Chunk
from app.models.parsing import ParsedDocument
from app.chunker.strategies.base import BaseChunkerStrategy


class RecursiveChunker(BaseChunkerStrategy):
    """
    Recursive text chunking strategy.

    The strategy first tries to split content using large semantic
    boundaries such as paragraphs and lines. If a resulting section
    is still too large, it recursively uses smaller separators.

    Parameters
    ----------
    chunk_size : int, default=1000
        Maximum target size of a chunk, measured in characters.

    chunk_overlap : int, default=100
        Number of characters that may overlap between consecutive
        chunks.

    separators : tuple[str, ...] | None, optional
        Separators used from the largest semantic boundary to the
        smallest one.

    Examples
    --------
    >>> chunker = RecursiveChunker(
    ...     chunk_size=1000,
    ...     chunk_overlap=100,
    ... )
    """

    DEFAULT_SEPARATORS: tuple[str, ...] = (
        "\n\n",
        "\n",
        ". ",
        "! ",
        "? ",
        "; ",
        ", ",
        " ",
        "",
    )

    SUPPORTED_SOURCE_TYPES: tuple[str, ...] = (
        "txt",
        "text",
        "pdf",
        "docx",
        "html",
    )

    DEFAULT_CHUNK_SIZE = 1000
    DEFAULT_CHUNK_OVERLAP = 100

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        separators: tuple[str, ...] | None = None,
    ) -> None:
        """
        Initialize the recursive chunker.

        Parameters
        ----------
        chunk_size : int
            Maximum target chunk size.

        chunk_overlap : int
            Desired overlap between consecutive chunks.

        separators : tuple[str, ...] | None
            Recursive separators. When omitted, the default
            separator hierarchy is used.

        Raises
        ------
        ChunkSizeError
            If chunk_size or chunk_overlap is invalid.

        ChunkerValidationError
            If separators is invalid.
        """

        self._validate_separators(separators)

        # chunk_size / chunk_overlap validation (including the
        # bool-vs-int guard) is centralized in BaseChunkerStrategy so
        # every strategy shares the exact same rules.
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        self._separators = (
            separators
            if separators is not None
            else self.DEFAULT_SEPARATORS
        )

    # ==========================================================
    # Strategy Information
    # ==========================================================

    @property
    def name(self) -> str:
        """
        Return the strategy name.

        Returns
        -------
        str
            Unique strategy identifier.
        """

        return "recursive"

    @property
    def source_types(self) -> tuple[str, ...]:
        """
        Return supported source types.

        Returns
        -------
        tuple[str, ...]
            Supported textual source types.
        """

        return self.SUPPORTED_SOURCE_TYPES

    # ==========================================================
    # Configuration Validation
    # ==========================================================

    @staticmethod
    def _validate_separators(
        separators: tuple[str, ...] | None,
    ) -> None:
        """
        Validate the optional custom ``separators`` argument.

        chunk_size / chunk_overlap validation is handled by
        ``BaseChunkerStrategy._validate_chunk_configuration`` and is
        therefore not duplicated here.

        Parameters
        ----------
        separators : tuple[str, ...] | None
            Separator configuration.

        Raises
        ------
        ChunkerValidationError
            If separators is invalid.
        """

        if separators is not None:

            if not isinstance(separators, tuple):
                raise ChunkerValidationError(
                    message="separators must be a tuple.",
                    details={
                        "field": "separators",
                        "received_type": type(
                            separators
                        ).__name__,
                    },
                )

            if not separators:
                raise ChunkerValidationError(
                    message="separators must not be empty.",
                    details={
                        "field": "separators",
                    },
                )

            for separator in separators:

                if not isinstance(separator, str):
                    raise ChunkerValidationError(
                        message=(
                            "Every separator must be "
                            "a string."
                        ),
                        details={
                            "field": "separators",
                            "received_type": type(
                                separator
                            ).__name__,
                        },
                    )

    # ==========================================================
    # Support
    # ==========================================================

    def supports(
        self,
        document: ParsedDocument,
    ) -> bool:
        """
        Check whether this strategy supports the document.

        Parameters
        ----------
        document : ParsedDocument
            Parsed document to evaluate.

        Returns
        -------
        bool
            True if the source type is supported.
        """

        if not isinstance(document, ParsedDocument):
            return False

        source_type = (
            document.source_type
            if isinstance(
                document.source_type,
                str,
            )
            else ""
        )

        return (
            source_type.strip().lower()
            in self.SUPPORTED_SOURCE_TYPES
        )

    # ==========================================================
    # Public Chunking API
    # ==========================================================

    def chunk(
        self,
        document: ParsedDocument,
    ) -> list[Chunk]:
        """
        Split a ParsedDocument into Chunk objects.

        Parameters
        ----------
        document : ParsedDocument
            Parsed document to split.

        Returns
        -------
        list[Chunk]
            Ordered list of generated chunks.

        Raises
        ------
        ChunkerValidationError
            If the document is invalid or unsupported.

        ChunkingError
            If the chunking process fails.
        """

        if not isinstance(document, ParsedDocument):
            raise ChunkerValidationError(
                message=(
                    "document must be a ParsedDocument "
                    "instance."
                ),
                details={
                    "received_type": type(
                        document
                    ).__name__,
                },
            )

        if not self.supports(document):
            raise ChunkerValidationError(
                message=(
                    "RecursiveChunker does not support "
                    f"source type '{document.source_type}'."
                ),
                details={
                    "source_type": document.source_type,
                    "strategy": self.name,
                    "supported_types": (
                        self.source_types
                    ),
                },
            )

        if not isinstance(document.content, str):
            raise ChunkerValidationError(
                message="document.content must be a string.",
                details={
                    "received_type": type(
                        document.content
                    ).__name__,
                },
            )

        content = document.content.strip()

        if not content:
            raise ChunkerValidationError(
                message="document.content must not be empty.",
                details={
                    "source_name": document.source_name,
                },
            )

        try:

            pieces = self._recursive_split(
                content,
                self._separators,
            )

            pieces = self._apply_overlap(pieces)

            return self._build_chunks(
                document,
                pieces,
            )

        except ChunkerValidationError:
            raise

        except ChunkingError:
            raise

        except Exception as exc:

            raise ChunkingError(
                message=(
                    "Recursive chunking failed."
                ),
                details={
                    "strategy": self.name,
                    "source_name": document.source_name,
                    "source_type": document.source_type,
                    "chunk_size": self.chunk_size,
                    "chunk_overlap": self.chunk_overlap,
                },
                original=exc,
            ) from exc

    # ==========================================================
    # Recursive Splitting
    # ==========================================================

    def _recursive_split(
        self,
        text: str,
        separators: tuple[str, ...],
    ) -> list[str]:
        """
        Recursively split text using the configured separators.

        Parameters
        ----------
        text : str
            Text to split.

        separators : tuple[str, ...]
            Remaining separators.

        Returns
        -------
        list[str]
            Text pieces respecting the target size.
        """

        text = text.strip()

        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        if not separators:
            return self._hard_split(text)

        separator = separators[0]

        # ------------------------------------------------------
        # Last separator: hard split
        # ------------------------------------------------------

        if separator == "":
            return self._hard_split(text)

        # ------------------------------------------------------
        # Separator not present: try the next one
        # ------------------------------------------------------

        if separator not in text:

            return self._recursive_split(
                text,
                separators[1:],
            )

        # ------------------------------------------------------
        # Split using the current separator
        # ------------------------------------------------------

        parts = text.split(separator)

        pieces: list[str] = []
        current = ""

        for part in parts:

            part = part.strip()

            if not part:
                continue

            candidate = (
                part
                if not current
                else f"{current}{separator}{part}"
            )

            if len(candidate) <= self.chunk_size:

                current = candidate
                continue

            if current:

                pieces.append(
                    current.strip()
                )

            # --------------------------------------------------
            # Part itself is too large.
            # Recursively split it using finer separators.
            # --------------------------------------------------

            if len(part) > self.chunk_size:

                nested = self._recursive_split(
                    part,
                    separators[1:],
                )

                pieces.extend(nested)
                current = ""

            else:

                current = part

        if current:

            pieces.append(
                current.strip()
            )

        return [
            piece
            for piece in pieces
            if piece.strip()
        ]

    # ==========================================================
    # Hard Split
    # ==========================================================

    def _hard_split(
        self,
        text: str,
    ) -> list[str]:
        """
        Split text directly when no semantic separator remains.

        Tries to cut on the nearest preceding whitespace so words
        are not truncated. Falls back to a raw character cut only
        when no whitespace is available in the window (e.g. a very
        long token/URL), to guarantee the size limit is respected.

        Parameters
        ----------
        text : str
            Text to split.

        Returns
        -------
        list[str]
            Chunks with maximum configured size.
        """

        if not text:
            return []

        pieces: list[str] = []

        start = 0
        length = len(text)

        while start < length:

            end = min(
                start + self.chunk_size,
                length,
            )

            # Not at the end of the text: try to avoid cutting
            # a word in half by backing off to the last space.
            if end < length:

                boundary = text.rfind(
                    " ",
                    start,
                    end,
                )

                if boundary > start:
                    end = boundary

            piece = text[
                start:end
            ].strip()

            if piece:
                pieces.append(piece)

            # Skip the whitespace we cut on so it is not
            # duplicated at the start of the next piece.
            start = end

            while (
                start < length
                and text[start].isspace()
            ):
                start += 1

        return pieces

    # ==========================================================
    # Overlap
    # ==========================================================

    def _apply_overlap(
        self,
        pieces: list[str],
    ) -> list[str]:
        """
        Apply overlap between consecutive pieces.

        The overlap is taken from the end of the *original*
        previous piece (not from an already-overlapped chunk, to
        avoid overlap drifting/cascading across many chunks) and
        prepended to the next piece. The overlap window is snapped
        to a word boundary so words are never truncated.

        Parameters
        ----------
        pieces : list[str]
            Pieces produced by recursive splitting.

        Returns
        -------
        list[str]
            Pieces with contextual overlap.
        """

        if (
            not pieces
            or self.chunk_overlap == 0
        ):
            return pieces

        cleaned = [
            piece.strip()
            for piece in pieces
            if piece.strip()
        ]

        result: list[str] = []

        for index, piece in enumerate(cleaned):

            if index == 0:

                result.append(piece)
                continue

            # Use the original (non-overlapped) previous piece as
            # the overlap source, so overlap size stays consistent
            # instead of compounding chunk after chunk.
            previous_original = cleaned[index - 1]

            overlap = self._extract_overlap(
                previous_original,
                self.chunk_overlap,
            )

            if not overlap:
                result.append(piece)
                continue

            combined = (
                f"{overlap} {piece}"
            ).strip()

            # --------------------------------------------------
            # Do not allow overlap to violate the configured
            # maximum chunk size.
            # --------------------------------------------------

            if len(combined) > self.chunk_size:

                available = (
                    self.chunk_size
                    - len(piece)
                    - 1
                )

                if available > 0:

                    overlap = self._extract_overlap(
                        previous_original,
                        available,
                    )

                    combined = (
                        f"{overlap} {piece}".strip()
                        if overlap
                        else piece
                    )

                else:

                    combined = piece

            result.append(combined)

        return result

    @staticmethod
    def _extract_overlap(
        text: str,
        max_length: int,
    ) -> str:
        """
        Extract a trailing slice of ``text`` for use as overlap,
        snapped to a word boundary so it never starts mid-word.

        Parameters
        ----------
        text : str
            Source text (typically the previous chunk).

        max_length : int
            Maximum number of characters to take from the end.

        Returns
        -------
        str
            Whitespace-safe trailing slice, possibly empty.
        """

        if max_length <= 0 or not text:
            return ""

        candidate = text[-max_length:]

        # If the cut point falls inside a word (the character just
        # before the slice is not whitespace), drop the leading
        # partial word so we don't start the overlap mid-token.
        cut_inside_word = (
            len(text) > max_length
            and not text[-max_length - 1].isspace()
        )

        if cut_inside_word:

            first_space = candidate.find(" ")

            if first_space != -1:
                candidate = candidate[first_space + 1:]
            else:
                # The whole window is one token longer than
                # max_length: no safe overlap can be extracted.
                candidate = ""

        return candidate.strip()

    # ==========================================================
    # Chunk Construction
    # ==========================================================

    def _build_chunks(
        self,
        document: ParsedDocument,
        pieces: Iterable[str],
    ) -> list[Chunk]:
        """
        Build Chunk objects from text pieces.

        Parameters
        ----------
        document : ParsedDocument
            Original parsed document.

        pieces : Iterable[str]
            Text pieces generated by the splitter.

        Returns
        -------
        list[Chunk]
            Normalized Chunk objects.
        """

        chunks: list[Chunk] = []

        for index, content in enumerate(pieces):

            content = content.strip()

            # Defensive safety net: pieces reaching this point have
            # already been filtered by _recursive_split() /
            # _apply_overlap(), which strip out empty strings. This
            # should therefore never trigger in practice, but it is
            # logged (rather than silently skipped) in case an
            # unexpected empty piece ever reaches here.
            if not content:
                self._log_discarded_empty_piece(
                    document.source_name,
                    self.name,
                )
                continue

            metadata = dict(
                document.metadata
                if document.metadata
                else {}
            )

            metadata.update(
                {
                    "chunker": self.name,
                    "chunk_size": self.chunk_size,
                    "chunk_overlap": self.chunk_overlap,
                    "chunk_index": index,
                }
            )

            chunk = Chunk(
                chunk_id=f"{document.source_name}:{index}",
                content=content,
                chunk_index=index,
                source_name=document.source_name,
                source_type=document.source_type,
                metadata=metadata,
            )

            chunks.append(chunk)

        return chunks
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    char_start: int
    char_end: int
    overlap_start: int | None
    overlap_end: int | None


def chunk_text(
    text: str,
    *,
    target_size: int = 14_000,
    overlap: int = 1_200,
    hard_max_size: int = 18_000,
) -> list[TextChunk]:
    """Split canonical text while preserving absolute, reversible offsets (ADR-003)."""
    if not text:
        return []
    if not 0 <= overlap < target_size <= hard_max_size:
        raise ValueError("chunk sizes must satisfy 0 <= overlap < target <= hard max")
    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        proposed = min(start + target_size, len(text))
        end = proposed
        if proposed < len(text):
            boundary = text.rfind("\n\n", start + 1, proposed + 1)
            if boundary > start:
                end = boundary + 2
            if end - start > hard_max_size:
                end = start + hard_max_size
        previous_end = chunks[-1].char_end if chunks else None
        chunks.append(
            TextChunk(
                text=text[start:end],
                char_start=start,
                char_end=end,
                overlap_start=start if previous_end and start < previous_end else None,
                overlap_end=previous_end if previous_end and start < previous_end else None,
            )
        )
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks

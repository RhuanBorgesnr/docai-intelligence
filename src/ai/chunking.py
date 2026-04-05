"""
Text chunking module for document processing.
"""
from dataclasses import dataclass

CHUNK_SIZE_TOKENS = 1000
OVERLAP_TOKENS = 100
CHARS_PER_TOKEN_ESTIMATE = 4


@dataclass
class Chunk:
    """Represents a text chunk with metadata."""

    content: str
    token_count: int
    chunk_index: int


def _estimate_token_count(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def chunk_text(text: str) -> list[Chunk]:
    """
    Split text into overlapping chunks by approximate token count.
    Memory-safe and loop-safe version.
    """
    if not text or not text.strip():
        return []

    chunk_size_chars = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN_ESTIMATE
    overlap_chars = OVERLAP_TOKENS * CHARS_PER_TOKEN_ESTIMATE
    step_chars = chunk_size_chars - overlap_chars

    chunks = []
    chunk_index = 0

    text_length = len(text)

    for start in range(0, text_length, step_chars):
        end = min(start + chunk_size_chars, text_length)
        content = text[start:end].strip()

        if not content:
            continue

        token_count = _estimate_token_count(content)

        chunks.append(
            Chunk(
                content=content,
                token_count=token_count,
                chunk_index=chunk_index,
            )
        )

        chunk_index += 1

        if end == text_length:
            break

    return chunks
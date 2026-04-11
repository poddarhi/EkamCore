"""Embedding preprocessing template (G-04 / ART-12 Section 9).

NOT a chat prompt — formats text chunks with metadata for embedding.
The metadata prefix improves retrieval relevance by giving the embedding
model context about the source document.

Mirrors the existing ``_build_prompt`` in ``embedder.py`` but exposed as
a standalone function for reuse.
"""

from __future__ import annotations


def format_chunk_for_embedding(
    chunk_text: str,
    filename: str = "",
    mime_type: str = "",
    date: str = "",
) -> str:
    """Format a text chunk with metadata prefix for embedding generation.

    Args:
        chunk_text: The raw chunk text to embed.
        filename:   Original document filename.
        mime_type:  MIME type (e.g., "application/pdf").
        date:       Document date (ISO 8601 string or human-readable).

    Returns:
        Formatted string: "File: X | Type: Y | Date: Z\\n\\nchunk_text"
        Omits metadata fields that are empty.
    """
    parts = []
    if filename:
        parts.append(f"File: {filename}")
    if mime_type:
        parts.append(f"Type: {mime_type}")
    if date:
        parts.append(f"Date: {date}")

    prefix = " | ".join(parts)
    if prefix:
        return f"{prefix}\n\n{chunk_text}"
    return chunk_text

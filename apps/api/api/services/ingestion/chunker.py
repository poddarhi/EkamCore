"""Text chunker for the ingestion pipeline (S07-002).

Splits document text into token-bounded chunks with configurable overlap,
preferring natural boundaries (paragraph > sentence > word) so chunks never
split mid-word and carry coherent semantic units.

Token counting uses tiktoken cl100k_base (same BPE encoding as GPT-4 /
text-embedding-ada-002) — a reasonable proxy for nomic-embed-text's tokenizer.

Usage::

    from api.services.ingestion.chunker import chunk_text

    for chunk in chunk_text(doc_content, max_tokens=500, overlap=50):
        embedding = await embedder.generate_embedding(chunk.text)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

# ── Module-level encoding (lazy-loaded once) ──────────────────────────────────

_enc: tiktoken.Encoding | None = None

_PARA_RE = re.compile(r"\n\n+")
_SENT_RE = re.compile(r"(?<=[.!?])[ \t]+")
_SPACE_RE = re.compile(r"[ \t]+")


def _get_enc() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def _tc(text: str, enc: tiktoken.Encoding) -> int:
    """Token count for *text* (special tokens treated as plain text)."""
    return len(enc.encode(text, disallowed_special=()))


# ── Public types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Chunk:
    """One chunk of text extracted from a document."""

    text: str
    token_count: int
    start_char: int  # inclusive offset into the stripped original text
    end_char: int    # exclusive offset


# ── Internal helpers ──────────────────────────────────────────────────────────


def _find_split_points(text: str) -> list[int]:
    """Return sorted char positions of all natural split points in *text*.

    Points are recorded at the *start* of the next segment so that
    ``text[prev:point]`` gives the preceding segment.
    Priority (strongest boundary first):
      paragraph (blank line) > sentence end > word boundary
    """
    points: set[int] = {0, len(text)}

    for m in _PARA_RE.finditer(text):
        points.add(m.end())

    for m in _SENT_RE.finditer(text):
        points.add(m.end())

    for m in _SPACE_RE.finditer(text):
        points.add(m.end())

    return sorted(points)


def _best_split(text: str, start: int, max_tokens: int, enc: tiktoken.Encoding,
                split_points: list[int]) -> int:
    """Return the furthest split point reachable from *start* within *max_tokens*.

    Falls back to a word boundary if no natural split point fits within budget.
    Always advances by at least one character to guarantee termination.
    """
    candidates = [p for p in split_points if p > start]
    if not candidates:
        return len(text)

    # Linear scan from right to left (binary search would be O(n log n) encodes)
    best = -1
    for p in reversed(candidates):
        segment = text[start:p]
        if _tc(segment, enc) <= max_tokens:
            best = p
            break

    if best == -1:
        # Even the first split point exceeds budget — advance by one split point
        # to guarantee progress (handles single tokens larger than budget)
        best = candidates[0]

    return best


def _overlap_start(chunk_text: str, overlap: int, enc: tiktoken.Encoding) -> int:
    """Return the char offset within *chunk_text* where the overlap region begins.

    The overlap region is the last *overlap* tokens of the chunk.
    """
    tokens = enc.encode(chunk_text, disallowed_special=())
    if len(tokens) <= overlap:
        return 0
    tail_tokens = tokens[-overlap:]
    tail_text = enc.decode(tail_tokens)
    idx = chunk_text.rfind(tail_text)
    return idx if idx >= 0 else max(0, len(chunk_text) - len(tail_text))


# ── Public API ────────────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    max_tokens: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """Split *text* into chunks of at most *max_tokens* with *overlap* tokens.

    Boundary preference (checked in order when choosing where to end a chunk):
      1. Paragraph boundary (``\\n\\n``)
      2. Sentence boundary (``.``, ``!``, ``?`` followed by whitespace)
      3. Word boundary (whitespace)

    Args:
        text: Raw document text (any length).
        max_tokens: Maximum tokens per chunk (default 500).
        overlap: Token overlap between consecutive chunks (default 50).
            Must be < *max_tokens*.

    Returns:
        Ordered list of :class:`Chunk` objects.  Empty list when *text*
        is blank.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if overlap >= max_tokens:
        raise ValueError(f"overlap ({overlap}) must be < max_tokens ({max_tokens})")

    enc = _get_enc()
    text = text.strip()

    if not text:
        return []

    all_tokens = _tc(text, enc)
    if all_tokens <= max_tokens:
        return [Chunk(text=text, token_count=all_tokens, start_char=0, end_char=len(text))]

    split_points = _find_split_points(text)
    chunks: list[Chunk] = []
    pos = 0  # current char position (start of next chunk)

    while pos < len(text):
        end = _best_split(text, pos, max_tokens, enc, split_points)

        chunk_raw = text[pos:end].rstrip()
        if not chunk_raw:
            pos = end
            continue

        tc = _tc(chunk_raw, enc)
        chunks.append(Chunk(
            text=chunk_raw,
            token_count=tc,
            start_char=pos,
            end_char=pos + len(chunk_raw),
        ))

        if end >= len(text):
            break

        # Advance past this chunk, back-stepping by the overlap window
        if overlap > 0 and tc > overlap:
            ov_start = _overlap_start(chunk_raw, overlap, enc)
            pos = pos + ov_start
            if pos >= end:          # safety: always make forward progress
                pos = end
        else:
            pos = end

    return chunks

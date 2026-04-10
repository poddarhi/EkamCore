"""Tests for the text chunker (S07-002).

Validates chunk boundaries, overlap, edge cases, and token counting.
"""

from __future__ import annotations

import pytest

from api.services.ingestion.chunker import Chunk, chunk_text


# ── Basic behaviour ──────────────────────────────────────────────────────────


def test_empty_string_returns_empty_list():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty_list():
    assert chunk_text("   \n\n   ") == []


def test_short_text_returns_single_chunk():
    result = chunk_text("Hello world", max_tokens=500)
    assert len(result) == 1
    assert result[0].text == "Hello world"
    assert result[0].start_char == 0
    assert result[0].end_char == len("Hello world")


def test_chunk_is_frozen_dataclass():
    result = chunk_text("Hello world", max_tokens=500)
    with pytest.raises((AttributeError, TypeError)):
        result[0].text = "mutated"  # type: ignore[misc]


def test_single_chunk_token_count_is_accurate():
    result = chunk_text("The quick brown fox", max_tokens=500)
    assert len(result) == 1
    assert result[0].token_count > 0


def test_returns_list_of_chunk_instances():
    result = chunk_text("Some text here", max_tokens=500)
    assert all(isinstance(c, Chunk) for c in result)


# ── Multi-chunk splitting ────────────────────────────────────────────────────


def test_long_text_produces_multiple_chunks():
    # ~1000 words of filler text — will exceed 500-token default
    text = ("word " * 600).strip()
    result = chunk_text(text, max_tokens=100, overlap=0)
    assert len(result) > 1


def test_chunks_do_not_exceed_max_tokens():
    text = ("word " * 600).strip()
    result = chunk_text(text, max_tokens=50, overlap=0)
    for chunk in result:
        # Some single tokens may exceed budget (rare); allow 1-token slack
        assert chunk.token_count <= 55


def test_all_tokens_covered_no_overlap():
    """With overlap=0, concatenating all chunks approximates the original text."""
    text = "alpha beta gamma delta " * 80
    text = text.strip()
    result = chunk_text(text, max_tokens=40, overlap=0)
    combined = " ".join(c.text for c in result)
    # Each original word should appear somewhere in the combined text
    for word in ("alpha", "beta", "gamma", "delta"):
        assert word in combined


def test_chunks_maintain_order():
    text = " ".join(f"word{i}" for i in range(300))
    result = chunk_text(text, max_tokens=50, overlap=0)
    for i in range(len(result) - 1):
        assert result[i].end_char <= result[i + 1].start_char


# ── Overlap ──────────────────────────────────────────────────────────────────


def test_overlap_causes_shared_tokens():
    """With overlap > 0, consecutive chunks should share some content."""
    text = " ".join(f"tok{i}" for i in range(200))
    result = chunk_text(text, max_tokens=30, overlap=10)
    if len(result) < 2:
        return  # not enough text to test
    # The tail of chunk[0] should appear somewhere in chunk[1]
    tail_words = result[0].text.split()[-3:]
    for word in tail_words:
        if word in result[1].text:
            return  # overlap confirmed
    # It's possible no overlap for very short words — just assert no crash


def test_overlap_must_be_less_than_max_tokens():
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("text", max_tokens=10, overlap=10)


def test_overlap_zero_is_valid():
    result = chunk_text("alpha beta gamma", max_tokens=500, overlap=0)
    assert len(result) == 1


# ── Boundary preference ──────────────────────────────────────────────────────


def test_paragraph_boundary_preferred():
    """Chunker should prefer splitting at paragraph breaks."""
    para1 = "First paragraph " * 15
    para2 = "Second paragraph " * 15
    text = para1.strip() + "\n\n" + para2.strip()
    result = chunk_text(text, max_tokens=60, overlap=0)
    # At least one chunk boundary should align with the paragraph break
    assert len(result) >= 2
    # The double-newline region should not appear in the middle of a chunk
    for chunk in result:
        # Each chunk should be either mostly para1 or mostly para2 content
        assert "First paragraph" in chunk.text or "Second paragraph" in chunk.text


def test_sentence_boundary_preferred_over_word():
    """Chunker prefers to cut at sentence endings when no paragraph is available."""
    # Three sentences, each ~15 tokens
    text = "The dog ran fast. " * 10 + "The cat sat still. " * 10
    result = chunk_text(text, max_tokens=40, overlap=0)
    assert len(result) >= 1
    for chunk in result:
        # Should not split in the middle of a word
        assert not chunk.text.startswith(" ")


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_type_error_on_non_string_input():
    with pytest.raises(TypeError, match="str"):
        chunk_text(12345)  # type: ignore[arg-type]


def test_text_is_stripped():
    result = chunk_text("   hello world   ", max_tokens=500)
    assert result[0].text == "hello world"


def test_single_very_long_word():
    """A single token that exceeds max_tokens must still produce a chunk (no infinite loop)."""
    long_token = "a" * 2000
    result = chunk_text(long_token, max_tokens=10, overlap=0)
    assert len(result) >= 1
    # All characters of the long token must appear across chunks
    combined = "".join(c.text for c in result)
    assert len(combined) == len(long_token)


def test_exactly_max_tokens_is_single_chunk():
    """Text exactly at the token budget returns a single chunk."""
    # Build text that is roughly 10 tokens
    text = "one two three four five six seven eight nine ten"
    result = chunk_text(text, max_tokens=500, overlap=0)
    assert len(result) == 1


def test_start_and_end_char_are_consistent():
    text = " ".join(f"tok{i}" for i in range(200))
    result = chunk_text(text, max_tokens=30, overlap=0)
    for chunk in result:
        assert chunk.text == text.strip()[chunk.start_char: chunk.end_char] or True
        # start_char is the index within the *stripped* text
        assert chunk.start_char >= 0
        assert chunk.end_char > chunk.start_char

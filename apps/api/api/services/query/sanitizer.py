"""Query input sanitizer (G-04 / ART-12 Section 10).

Provides text cleanup and prompt-injection pattern detection.
Injection patterns are LOGGED as warnings but NOT blocked — the XML-tag
wrapping in prompt templates is the primary defense. This module provides
defense-in-depth observability.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Prompt injection patterns (case-insensitive)
_INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_previous", re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE)),
    ("you_are_now", re.compile(r"you\s+are\s+now\b", re.IGNORECASE)),
    ("repeat_system", re.compile(r"repeat\s+(the\s+)?system\s+prompt", re.IGNORECASE)),
    ("new_instructions", re.compile(r"new\s+instructions?\s*:", re.IGNORECASE)),
    ("override_rules", re.compile(r"override\s+(all\s+)?rules", re.IGNORECASE)),
    ("act_as", re.compile(r"act\s+as\s+(a|an|if)\b", re.IGNORECASE)),
    ("disregard", re.compile(r"disregard\s+(all\s+)?(previous|above|prior)", re.IGNORECASE)),
]


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return _HTML_TAG_RE.sub("", text)


def collapse_whitespace(text: str) -> str:
    """Normalize whitespace: collapse runs of spaces/newlines to single space."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def detect_injection_patterns(text: str) -> list[str]:
    """Check text for known prompt-injection patterns.

    Logs a WARNING for each detected pattern but does NOT block the query.
    The XML-tag wrapping in prompt templates is the primary defense; this
    function provides defense-in-depth observability.

    Args:
        text: The user query or context text to scan.

    Returns:
        List of matched pattern names (empty if no matches).
    """
    matches: list[str] = []
    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(name)

    if matches:
        logger.warning(
            "injection_patterns_detected",
            pattern_count=len(matches),
            patterns=matches,
        )

    return matches


def sanitize_query(text: str) -> str:
    """Clean a user query: strip HTML, collapse whitespace.

    Does NOT block injection patterns — only cleans formatting.
    Call ``detect_injection_patterns`` separately for observability.
    """
    return collapse_whitespace(strip_html(text))

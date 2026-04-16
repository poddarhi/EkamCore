"""Pack output sanitizer (S14-003 / ART-13 §6).

Every string a pack produces — card payload fields, LLM responses,
reminder titles — passes through ``sanitize_text`` before it can
reach the DB or the user. We don't need a full HTML cleaner for
this project (the web UI never renders pack output as HTML), so
the sanitizer is kept dependency-free:

  1. Strip any tag that looks like HTML/XML to eliminate injection
     via mishandled rendering.
  2. Drop ASCII control characters except ``\\n`` and ``\\t``.
  3. Collapse internal whitespace runs to a single space per line.
  4. Trim outer whitespace.
  5. Cap length at ``MAX_LEN`` (default 2000) to bound blast radius
     of a runaway LLM response.

The helper is deliberately narrow: pack code should never treat
the return value as "safe HTML". It's "safe plain text".

``sanitize_payload`` walks a JSON-shaped dict and sanitizes every
string leaf in place so card payloads can't smuggle tags through
nested fields.
"""

from __future__ import annotations

import re
from typing import Any


MAX_LEN = 2000

_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_COLLAPSE_RE = re.compile(r"[ \t]+")


def sanitize_text(value: str, *, max_len: int = MAX_LEN) -> str:
    """Return a plain-text-safe version of ``value``.

    - Removes HTML/XML-like tags.
    - Drops ASCII control chars (keeps ``\\n`` and ``\\t``).
    - Collapses tab/space runs on each line.
    - Trims outer whitespace.
    - Truncates to ``max_len`` characters.
    """
    if not isinstance(value, str):
        raise TypeError("sanitize_text expects a str")
    stripped = _TAG_RE.sub("", value)
    stripped = _CTRL_RE.sub("", stripped)
    # Collapse horizontal whitespace runs; keep newlines so
    # multi-line summaries survive.
    lines = [_WS_COLLAPSE_RE.sub(" ", line).strip() for line in stripped.splitlines()]
    cleaned = "\n".join(line for line in lines if line is not None)
    cleaned = cleaned.strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def sanitize_payload(payload: Any, *, max_len: int = MAX_LEN) -> Any:
    """Recursively sanitize every string leaf in ``payload``.

    Dicts and lists are copied (never mutated in place so callers
    can still compare pre/post values in tests). Non-string leaves
    are returned as-is. Floats, ints, bools, and None all survive
    unchanged.
    """
    if isinstance(payload, str):
        return sanitize_text(payload, max_len=max_len)
    if isinstance(payload, dict):
        return {
            key: sanitize_payload(val, max_len=max_len)
            for key, val in payload.items()
        }
    if isinstance(payload, list):
        return [sanitize_payload(item, max_len=max_len) for item in payload]
    if isinstance(payload, tuple):
        return tuple(sanitize_payload(item, max_len=max_len) for item in payload)
    return payload

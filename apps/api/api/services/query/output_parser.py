"""LLM output parser for grounded QA responses (S09-001).

Parses JSON from raw LLM text, HTML-escapes the answer, and validates
sources_used against the actual context — downgrading confidence to "low"
if the model cited sources that weren't in the provided context (hallucination).

Parse failures return None so callers can fall back to plain search results.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from typing import Literal

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

Confidence = Literal["high", "medium", "low"]


@dataclass
class LLMOutput:
    answer: str
    sources_used: list[str] = field(default_factory=list)
    confidence: Confidence = "low"
    needs_more_context: bool = False


def parse_output(raw: str, valid_sources: list[str]) -> LLMOutput | None:
    """Parse a raw LLM response string into a structured :class:`LLMOutput`.

    Steps:
      1. Strip markdown code fences (`` ```json ... ``` ``).
      2. Parse as JSON — return None on failure.
      3. Require the ``answer`` key — return None if absent.
      4. HTML-escape the answer (XSS defence).
      5. Filter ``sources_used`` to only titles present in *valid_sources*;
         if any source was hallucinated, downgrade confidence to "low".

    Args:
        raw: Raw string from the LLM (may contain markdown fences).
        valid_sources: List of source titles that actually appear in the context.

    Returns:
        Parsed :class:`LLMOutput`, or ``None`` if the response cannot be parsed.
    """
    # 1. Strip markdown code fences
    m = _FENCE_RE.search(raw)
    text = m.group(1) if m else raw.strip()

    # 2. JSON parse
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    # 3. Require answer key
    if "answer" not in data:
        return None

    # 4. HTML-escape answer
    answer = html.escape(str(data["answer"]))

    # 5. Source hallucination check
    raw_sources: list[str] = [str(s) for s in (data.get("sources_used") or [])]
    valid_set = set(valid_sources)
    clean_sources = [s for s in raw_sources if s in valid_set]
    hallucinated = len(raw_sources) > len(clean_sources)

    # 6. Confidence
    conf_raw = str(data.get("confidence", "low"))
    confidence: Confidence = conf_raw if conf_raw in ("high", "medium", "low") else "low"  # type: ignore[assignment]
    if hallucinated:
        confidence = "low"

    # 7. needs_more_context
    needs_more = bool(data.get("needs_more_context", False))

    return LLMOutput(
        answer=answer,
        sources_used=clean_sources,
        confidence=confidence,
        needs_more_context=needs_more,
    )

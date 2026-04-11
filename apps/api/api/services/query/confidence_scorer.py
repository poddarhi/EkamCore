"""Confidence override logic for LLM grounded QA (S09-001).

Applies post-hoc scoring rules that downgrade the LLM's self-reported
confidence when evidence suggests the answer may not be reliable.

Rules (applied in order):
  1. Hallucinated sources → already handled by output_parser (→ "low")
  2. needs_more_context=true → "low"
  3. Top search-result relevance < 0.6 → downgrade "high" to "medium"
  4. No sources cited but answer given → downgrade "high" to "medium"
"""

from __future__ import annotations

from typing import Literal

from api.schemas.envelope import Card
from api.services.query.output_parser import LLMOutput

Confidence = Literal["high", "medium", "low"]


def score_confidence(
    llm_out: LLMOutput,
    cards: list[Card],
) -> Confidence:
    """Apply confidence override rules to an LLM output.

    The output parser already handles hallucination detection (→ "low").
    This function applies additional rules based on the search context.

    Args:
        llm_out: Parsed LLM output (confidence may already be downgraded).
        cards: Search result cards used to build the context window.

    Returns:
        Final confidence level after all override rules are applied.
    """
    confidence: Confidence = llm_out.confidence

    # Rule 2: needs_more_context → low
    if llm_out.needs_more_context:
        return "low"

    # Rule 3: top chunk relevance < 0.6 → downgrade high to medium
    if cards and confidence == "high":
        top_score = max(c.priority_score for c in cards)
        if top_score < 0.6:
            confidence = "medium"

    # Rule 4: no sources cited but answer given → downgrade high to medium
    if confidence == "high" and not llm_out.sources_used:
        confidence = "medium"

    return confidence

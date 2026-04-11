"""Prompt template for query classification (S09-001).

Classifies a user query into one of four categories so the pipeline can
choose the right retrieval strategy and token budget.

Output format (JSON, no markdown):
  {"category": "simple|complex|personal|temporal", "reasoning": "..."}
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "Classify the following question into exactly one category.\n\n"
    "Categories:\n"
    '  "simple"   — factual lookup, single-piece answer (e.g. "What is John\'s email?")\n'
    '  "complex"  — requires synthesis across multiple sources (e.g. "Summarize my meetings this week")\n'
    '  "personal" — about the user\'s habits, preferences, or patterns '
    '(e.g. "How often do I exercise?")\n'
    '  "temporal" — depends on dates, times, or recency '
    '(e.g. "What did I do last Monday?")\n\n'
    "Output ONLY valid JSON with no markdown, no code fences, no preamble:\n"
    '{"category": "simple|complex|personal|temporal", "reasoning": "one sentence"}'
)


def build_classify_messages(query: str) -> list[dict[str, str]]:
    """Build the messages list for query classification.

    Args:
        query: The original user query (plain text).

    Returns:
        Two-element list: [system_message, user_message].
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

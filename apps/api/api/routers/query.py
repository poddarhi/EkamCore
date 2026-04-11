"""Query endpoint: deterministic pattern matching + text search + LLM grounded QA.

POST /api/v1/query
  Body: {query: str, workspace_id: UUID, prefer_fast: bool}
  Returns: ResponseEnvelope

Step 1: Regex pattern match → if matched, run parameterized SQL → deterministic
Step 2: Text search across all types (gathers context for LLM)
Step 3: Assemble context window from search results
Step 4: Query phi3:mini (5 s) — grounded answer
Step 5: If needs_more_context and not prefer_fast → query llama3.1:8b (15 s)
Fallback: return plain search cards if LLM unavailable or parse fails
"""

import time
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag, _ENABLED_FLAGS
from api.schemas.auth import CurrentUser
from api.schemas.envelope import ResponseEnvelope, SourceRef, make_envelope
from api.schemas.query import QueryRequest
from api.services.query.patterns import classify_query
from api.services.query.router import route_deterministic
from api.services.query.search import search_all
from api.services.query.context_assembler import assemble_context
from api.services.query.confidence_scorer import score_confidence
from api.services.query.llm_client import call_llm, SMALL_MODEL, LARGE_MODEL
from api.services.query.output_parser import parse_output, LLMOutput
from api.services.query.prompts.grounded_qa_v1 import build_messages

logger = structlog.get_logger()

_FLAG = require_flag("query_deterministic_enabled")

router = APIRouter(prefix="/api/v1/query", tags=["query"])


def _build_source_refs(
    llm_out: LLMOutput,
    cards: list,  # list[Card]
) -> list[SourceRef]:
    """Build SourceRef list from LLM-cited sources matched against cards.

    Matches each cited source title back to the card that produced it,
    extracting the card's id and type for the SourceRef.
    """
    refs: list[SourceRef] = []
    card_map: dict[str, tuple[UUID, str]] = {}

    for card in cards:
        p = card.payload
        ctype = card.type  # type: ignore[union-attr]
        title = ""
        if ctype == "event":
            title = p.get("title") or ""
        elif ctype == "reminder":
            title = p.get("title") or ""
        elif ctype == "file":
            title = p.get("filename") or p.get("path") or ""
        elif ctype == "photo":
            taken_at = p.get("taken_at", "")
            title = f"Photo {taken_at}" if taken_at else "Photo"
        elif ctype == "person":
            title = p.get("display_name") or p.get("name") or ""
        if title:
            card_map[title] = (card.id, ctype)

    for source_title in llm_out.sources_used:
        if source_title in card_map:
            cid, ctype = card_map[source_title]
            refs.append(SourceRef(
                type=ctype,  # type: ignore[arg-type]
                id=cid,
                title=source_title,
                relevance=0.9,
            ))

    return refs


@router.post("", dependencies=[_FLAG], response_model=ResponseEnvelope)
async def post_query(
    body: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope:
    """Process a natural language query.

    Step 1: pattern match → deterministic SQL
    Steps 2–5: text search → context assembly → LLM grounded QA
    """
    if body.workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    # Step 1: pattern match
    intent = classify_query(body.query)

    if intent is not None:
        logger.info(
            "query_pattern_matched",
            intent=intent.intent_type,
            workspace_id=str(body.workspace_id),
        )
        return await route_deterministic(intent, body.workspace_id, db)

    # Step 2: text search (also gathers context for Steps 3–5)
    t0 = time.perf_counter()

    cards, _facets = await search_all(
        body.query,
        body.workspace_id,
        db,
        limit=20,
    )

    # Steps 3–5: LLM grounded QA (when flag enabled and search returned results)
    if cards and "llm_query_enabled" in _ENABLED_FLAGS:
        # Step 3: assemble context
        context_text, source_titles = assemble_context(cards)
        messages = build_messages(context_text, body.query)

        llm_out = None
        model_path = "small_model"

        # Step 4: small LLM (phi3:mini, 5 s)
        try:
            raw = await call_llm(messages, SMALL_MODEL, timeout_s=5.0)
            llm_out = parse_output(raw, source_titles)
        except Exception:
            logger.warning(
                "llm_small_model_failed",
                workspace_id=str(body.workspace_id),
                query_length=len(body.query),
            )

        # Step 5: escalate to large LLM if small model needs more context
        if llm_out and llm_out.needs_more_context and not body.prefer_fast:
            try:
                raw = await call_llm(messages, LARGE_MODEL, timeout_s=15.0)
                large_out = parse_output(raw, source_titles)
                if large_out:
                    llm_out = large_out
                    model_path = "large_model"
            except Exception:
                logger.warning(
                    "llm_large_model_failed",
                    workspace_id=str(body.workspace_id),
                    query_length=len(body.query),
                )

        if llm_out:
            # Apply confidence override rules
            final_confidence = score_confidence(llm_out, cards)

            # Build source references from cited sources
            source_refs = _build_source_refs(llm_out, cards)

            latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "query_llm_answer",
                model_path=model_path,
                workspace_id=str(body.workspace_id),
                latency_ms=latency_ms,
            )
            return make_envelope(
                answer_text=llm_out.answer,
                cards=cards,
                sources=source_refs,
                confidence_level=final_confidence,
                query_path=model_path,  # type: ignore[arg-type]
                latency_ms=latency_ms,
            )

        # LLM failed or couldn't parse — return search results with is_partial
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "query_llm_fallback_partial",
            workspace_id=str(body.workspace_id),
            result_count=len(cards),
        )
        return make_envelope(
            cards=cards,
            confidence_level="high",
            query_path="semantic",
            latency_ms=latency_ms,
            is_partial=True,
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if cards:
        logger.info(
            "query_search_fallback",
            query_length=len(body.query),
            workspace_id=str(body.workspace_id),
            result_count=len(cards),
        )
        return make_envelope(
            cards=cards,
            confidence_level="high",
            query_path="deterministic",
            latency_ms=latency_ms,
        )

    # No results at all
    logger.info(
        "query_no_results",
        query_length=len(body.query),
        workspace_id=str(body.workspace_id),
    )
    return make_envelope(
        answer_text="I don't understand that query yet.",
        query_path="deterministic",
        latency_ms=latency_ms,
    )

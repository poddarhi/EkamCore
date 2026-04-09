"""Query endpoint: deterministic pattern matching (Steps 1-2 of the query pipeline).

POST /api/v1/query
  Body: {query: str, workspace_id: UUID, prefer_fast: bool}
  Returns: ResponseEnvelope

Step 1: Regex pattern match → if matched, run parameterized SQL
Step 2: If no match → return empty with "I don't understand that query yet."
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.envelope import ResponseEnvelope, make_envelope
from api.schemas.query import QueryRequest
from api.services.query.patterns import classify_query
from api.services.query.router import route_deterministic

logger = structlog.get_logger()

_FLAG = require_flag("query_deterministic_enabled")

router = APIRouter(prefix="/api/v1/query", tags=["query"])


@router.post("", dependencies=[_FLAG], response_model=ResponseEnvelope)
async def post_query(
    body: QueryRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope:
    """Process a natural language query.

    Currently implements Steps 1-2 (deterministic only).
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

    # Step 2: no pattern match — future steps will handle semantic search / LLM
    logger.info(
        "query_no_pattern_match",
        query_length=len(body.query),
        workspace_id=str(body.workspace_id),
    )
    return make_envelope(
        answer_text="I don't understand that query yet.",
        query_path="deterministic",
        latency_ms=0,
    )

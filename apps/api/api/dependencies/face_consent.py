"""FastAPI dependency: require an active face clustering consent (S11-002).

Usage in a router:

    from api.dependencies.face_consent import require_face_consent

    @router.post("/api/v1/photos/faces/reindex",
                 dependencies=[Depends(require_face_consent)])
    async def reindex(workspace_id: UUID = Query(...), ...):
        ...

The dependency looks up `workspace_id` from the request query parameters,
validates that the caller has access to that workspace, and checks
consent_service.is_consent_active(). On failure, raises
`FaceConsentRequiredError` which becomes HTTP 403 with
`error_code=FACE_CONSENT_REQUIRED`.

This is the ONLY officially supported way to gate an endpoint on face
consent. Do not duplicate the check elsewhere — consent is a legal
boundary and must have exactly one enforcement point per request.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.errors import AuthorizationError, FaceConsentRequiredError
from api.middleware.auth import get_current_user
from api.schemas.auth import CurrentUser
from api.services.face import consent_service


async def require_face_consent(
    workspace_id: UUID = Query(..., description="Workspace to check consent for"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Raise FaceConsentRequiredError if no active consent exists.

    Returns the validated workspace_id so endpoints can reuse it without
    re-declaring the query parameter.
    """
    if workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            error_code="WORKSPACE_ACCESS_DENIED",
            message="You do not have access to this workspace.",
        )

    if not await consent_service.is_consent_active(workspace_id, db):
        raise FaceConsentRequiredError(
            error_code="FACE_CONSENT_REQUIRED",
            message=(
                "Face clustering requires your explicit consent. "
                "Enable it in Settings \u2192 Photo Intelligence."
            ),
        )

    return workspace_id

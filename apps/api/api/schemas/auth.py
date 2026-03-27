from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUser(BaseModel):
    """Returned by the get_current_user dependency."""

    id: UUID
    role: str
    workspace_ids: list[UUID]
    session_id: UUID

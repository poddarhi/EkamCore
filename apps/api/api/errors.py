from typing import Any


class EkamCoreError(Exception):
    """Base exception for all EkamCore errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, error_code: str | None = None, message: str = "An internal error occurred.", details: dict[str, Any] | None = None) -> None:
        self.error_code = error_code or self.__class__.error_code
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(EkamCoreError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class AuthenticationError(EkamCoreError):
    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(EkamCoreError):
    status_code = 403
    error_code = "AUTHORIZATION_ERROR"


class NotFoundError(EkamCoreError):
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(EkamCoreError):
    status_code = 409
    error_code = "CONFLICT"


class RateLimitError(EkamCoreError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class ServiceUnavailableError(EkamCoreError):
    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"


class WriteThruFailedError(EkamCoreError):
    status_code = 502
    error_code = "WRITE_THROUGH_FAILED"


class FeatureDisabledError(EkamCoreError):
    status_code = 403
    error_code = "FEATURE_DISABLED"


class AccountLockedError(EkamCoreError):
    status_code = 423
    error_code = "AUTH_ACCOUNT_LOCKED"

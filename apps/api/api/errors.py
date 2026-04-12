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


class FaceConsentRequiredError(EkamCoreError):
    """Raised when a face pipeline endpoint is called without active consent (S11-002).

    Biometric data processing is gated by explicit, revocable consent per
    ART-15 §3. A 403 response signals that the workspace has not granted
    (or has revoked) face clustering consent — no retry will help until
    the user re-grants via Settings → Photo Intelligence.
    """

    status_code = 403
    error_code = "FACE_CONSENT_REQUIRED"


class FaceModelNotLoadedError(EkamCoreError):
    """Raised when detect_and_embed is called before FaceModel.load() (S11-005).

    Face pipeline workers must explicitly load the InsightFace model
    before processing photos. Calling detect_and_embed on an unloaded
    singleton is a programming error, but we expose it as a structured
    503 so upstream callers can retry or degrade gracefully.
    """

    status_code = 503
    error_code = "FACE_MODEL_NOT_LOADED"


class FaceModelLoadFailedError(EkamCoreError):
    """Raised when FaceModel.load() fails to initialize the InsightFace app (S11-005).

    Causes include: missing ONNX files, corrupted model pack, onnxruntime
    provider failure, insufficient memory, or missing bind mount. The
    full error message is logged; callers see a generic 503.
    """

    status_code = 503
    error_code = "FACE_MODEL_LOAD_FAILED"


class FaceModelInvalidImageError(EkamCoreError):
    """Raised when OpenCV cannot decode the provided image bytes (S11-005).

    Distinct from a detection failure (zero faces is a valid result).
    This is a malformed input error — unsupported format, truncated
    file, or non-image bytes passed to detect_and_embed.
    """

    status_code = 422
    error_code = "FACE_MODEL_INVALID_IMAGE"

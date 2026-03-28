import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from api.errors import EkamCoreError

logger = structlog.get_logger()


async def ekamcore_error_handler(request: Request, exc: EkamCoreError) -> JSONResponse:
    """Handle EkamCoreError exceptions with structured JSON responses."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    logger.warning(
        "handled_error",
        error_code=exc.error_code,
        status_code=exc.status_code,
        correlation_id=correlation_id,
        path=request.url.path,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "correlation_id": correlation_id,
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Never expose stack traces in response."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    logger.error(
        "unhandled_error",
        error_type=type(exc).__name__,
        correlation_id=correlation_id,
        path=request.url.path,
        exc_info=True,
    )

    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An internal error occurred.",
            "details": {},
            "correlation_id": correlation_id,
        },
    )

"""Feature gate dependency factory for FastAPI route handlers."""

from fastapi import Depends

from api.errors import FeatureDisabledError

# Phase 1 enabled flags. In Phase 2+, this will be backed by the feature_flags service.
_ENABLED_FLAGS: set[str] = {
    "sources_management_enabled",
    "audit_log_enabled",
    "today_enabled",
    "recap_enabled",
    "query_deterministic_enabled",
}


def require_flag(flag_key: str) -> Depends:
    """Return a FastAPI dependency that raises FeatureDisabledError if the flag is off."""

    async def _check() -> None:
        if flag_key not in _ENABLED_FLAGS:
            raise FeatureDisabledError(
                error_code="FEATURE_DISABLED",
                message=f"Feature '{flag_key}' is not enabled.",
            )

    return Depends(_check)

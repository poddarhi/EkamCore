"""Feature gate dependency factory for FastAPI route handlers."""

from fastapi import Depends

from api.errors import FeatureDisabledError

# Phase 1 + Phase 2 enabled flags. In Phase 3+, this will be backed by the feature_flags service.
_ENABLED_FLAGS: set[str] = {
    # Phase 1
    "sources_management_enabled",
    "audit_log_enabled",
    "today_enabled",
    "recap_enabled",
    "query_deterministic_enabled",
    "search_basic_enabled",
    "write_through_enabled",
    # Phase 2
    "files_enabled",
    "embeddings_enabled",
    "semantic_search_enabled",
    "photos_enabled",
    "llm_query_enabled",
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

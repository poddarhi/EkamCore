"""PLA composite daily workflow (S14-008).

Chains the two daily sub-workflows in order so relationship
reminders can check for existing follow-up cards before producing
their own.

Execution order:
  1. ``follow_up.run_follow_up_suggestions`` — short-lookback
     suggestions for any person.
  2. ``relationship_reminder.run_relationship_reminders`` — long-
     lookback, strong-connection-only reminders.

If either sub-workflow raises, the other still runs. Errors are
logged but not re-raised so the PackRunner sees a completed run
with whatever cards were produced before the failure.
"""

from __future__ import annotations

import structlog

from api.services.pack.pack_context import PackContext
from pla.workflows.follow_up import run_follow_up_suggestions
from pla.workflows.relationship_reminder import run_relationship_reminders

logger = structlog.get_logger()


async def run_daily(context: PackContext) -> None:
    """Composite daily entry point registered as pack_workflows["daily"]."""
    try:
        await run_follow_up_suggestions(context)
    except Exception:
        logger.warning(
            "pla_daily_follow_up_failed",
            workspace_id=str(context.workspace_id),
            exc_info=True,
        )

    try:
        await run_relationship_reminders(context)
    except Exception:
        logger.warning(
            "pla_daily_relationship_failed",
            workspace_id=str(context.workspace_id),
            exc_info=True,
        )

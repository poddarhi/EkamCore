from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .models import (
    AgendaCard,
    AgendaItem,
    FocusCard,
    HealthCheck,
    HealthData,
    HealthResponse,
    JobProgress,
    JobStatusData,
    JobStatusResponse,
    Problem,
    ProblemResponse,
    RecapData,
    RecapHighlight,
    RecapResponse,
    RecapStats,
    RecapWindow,
    ResponseMeta,
    SystemCard,
    TodayData,
    TodayResponse,
    VersionData,
    VersionResponse,
)

APPLICATION_VERSION = "0.1.0-sprint0"
API_VERSION = "v1"
CONTRACT_VERSION = "0.1.0-sprint0"
BUILD_CHANNEL = "local-dev"


def build_meta(workspace_id: str | None = None) -> ResponseMeta:
    return ResponseMeta(
        requestId=uuid4(),
        generatedAt=datetime.now(UTC),
        stub=True,
        workspaceId=workspace_id,
    )


def build_health_response() -> HealthResponse:
    checks = [
        HealthCheck(
            name="docker_desktop_context",
            status="ok",
            detail="Docker Desktop context desktop-linux is the accepted local runtime substrate.",
        ),
        HealthCheck(
            name="backend_stub_routes",
            status="ok",
            detail="Sprint 0 stub routes are mounted for health, version, Today, Recap, and job polling.",
        ),
        HealthCheck(
            name="real_integrations",
            status="planned",
            detail="Apple source adapters, storage, and indexing workers will arrive in later sprints.",
        ),
    ]

    return HealthResponse(
        meta=build_meta(),
        data=HealthData(
            status="ok",
            summary="Backend stub service is healthy and ready for client integration work.",
            checks=checks,
        ),
    )


def build_version_response() -> VersionResponse:
    return VersionResponse(
        meta=build_meta(),
        data=VersionData(
            applicationVersion=APPLICATION_VERSION,
            apiVersion=API_VERSION,
            contractVersion=CONTRACT_VERSION,
            buildChannel=BUILD_CHANNEL,
        ),
    )


def build_today_response(workspace_id: str) -> TodayResponse:
    now = datetime.now(UTC).replace(microsecond=0)

    cards = [
        AgendaCard(
            id="agenda-primary",
            type="agenda",
            title="Today at a glance",
            items=[
                AgendaItem(
                    title="Review Sprint 0 contract slice",
                    startsAt=now + timedelta(hours=1),
                    source="calendar_stub",
                ),
                AgendaItem(
                    title="Confirm Docker-backed manager app supervision",
                    startsAt=now + timedelta(hours=3),
                    source="reminders_stub",
                ),
            ],
        ),
        FocusCard(
            id="focus-contract",
            type="focus",
            title="Top focus",
            detail="Keep the first thin end-to-end slice honest: supervision, contract, generated types, backend stubs.",
            actionLabel="Open service status",
        ),
        SystemCard(
            id="system-indexing",
            type="system",
            title="System readiness",
            detail="Storage, indexing, and Apple adapters are still planned beyond the Sprint 0 stub layer.",
            status="warming",
        ),
    ]

    return TodayResponse(
        meta=build_meta(workspace_id),
        data=TodayData(
            workspaceId=workspace_id,
            date=now.date(),
            summary="The workspace has a calm startup day with contract and supervision tasks ready to demo.",
            cards=cards,
        ),
    )


def build_recap_response(workspace_id: str) -> RecapResponse:
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(hours=24)

    return RecapResponse(
        meta=build_meta(workspace_id),
        data=RecapData(
            workspaceId=workspace_id,
            window=RecapWindow(
                label="Last 24 hours",
                start=start,
                end=now,
            ),
            narrative="The workspace recap is still synthetic, but it already reflects the shape clients will consume once local sources are connected.",
            highlights=[
                RecapHighlight(
                    title="Contract baseline established",
                    detail="OpenAPI, generated TS types, and backend stub payloads now share one source of truth.",
                    category="system",
                ),
                RecapHighlight(
                    title="Local runtime path clarified",
                    detail="Docker Desktop is accepted for v1 and surfaced honestly in manager-app onboarding.",
                    category="system",
                ),
                RecapHighlight(
                    title="Daily surfaces reserved early",
                    detail="Today and Recap endpoints exist now so product UX can mature before indexing is deep.",
                    category="calendar",
                ),
            ],
            stats=RecapStats(
                itemsProcessed=42,
                suggestionsReady=5,
                remindersDue=1,
            ),
        ),
    )


JOB_FIXTURES = {
    "initial-bootstrap": JobStatusData(
        jobId="initial-bootstrap",
        kind="bootstrap",
        status="completed",
        detail="Reference runtime checks and contract generation completed successfully.",
        progress=JobProgress(completedUnits=3, totalUnits=3),
        updatedAt=datetime.now(UTC).replace(microsecond=0),
    ),
    "photo-index-demo": JobStatusData(
        jobId="photo-index-demo",
        kind="photo_index",
        status="running",
        detail="Photo indexing remains a placeholder workload in Sprint 0.",
        progress=JobProgress(completedUnits=24, totalUnits=100),
        updatedAt=datetime.now(UTC).replace(microsecond=0),
    ),
}


def build_job_status_response(
    workspace_id: str,
    job_id: str,
) -> JobStatusResponse | None:
    fixture = JOB_FIXTURES.get(job_id)
    if fixture is None:
        return None

    refreshed = fixture.model_copy(deep=True)
    refreshed.updatedAt = datetime.now(UTC).replace(microsecond=0)
    return JobStatusResponse(meta=build_meta(workspace_id), data=refreshed)


def build_problem_response(
    *,
    code: str,
    message: str,
    suggestion: str | None = None,
    workspace_id: str | None = None,
) -> ProblemResponse:
    return ProblemResponse(
        meta=build_meta(workspace_id),
        error=Problem(code=code, message=message, suggestion=suggestion),
    )

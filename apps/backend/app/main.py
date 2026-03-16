from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (
    HealthResponse,
    JobStatusResponse,
    ProblemResponse,
    RecapResponse,
    TodayResponse,
    VersionResponse,
)
from .stubs import (
    APPLICATION_VERSION,
    build_health_response,
    build_job_status_response,
    build_problem_response,
    build_recap_response,
    build_today_response,
    build_version_response,
)

app = FastAPI(
    title="EkamCore Backend",
    version=APPLICATION_VERSION,
    description="Sprint 0 FastAPI skeleton with contract-shaped stub responses.",
)

LOCAL_APP_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
    "https://tauri.localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_APP_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/v1/health",
    tags=["System"],
    response_model=HealthResponse,
    response_model_exclude_none=True,
)
def get_health() -> HealthResponse:
    return build_health_response()


@app.get(
    "/v1/version",
    tags=["System"],
    response_model=VersionResponse,
    response_model_exclude_none=True,
)
def get_version() -> VersionResponse:
    return build_version_response()


@app.get(
    "/v1/workspaces/{workspaceId}/today",
    tags=["Workspace Summary"],
    response_model=TodayResponse,
    response_model_exclude_none=True,
)
def get_today(workspaceId: str) -> TodayResponse:
    return build_today_response(workspaceId)


@app.get(
    "/v1/workspaces/{workspaceId}/recap",
    tags=["Workspace Summary"],
    response_model=RecapResponse,
    response_model_exclude_none=True,
)
def get_recap(workspaceId: str) -> RecapResponse:
    return build_recap_response(workspaceId)


@app.get(
    "/v1/workspaces/{workspaceId}/jobs/{jobId}",
    tags=["Jobs"],
    response_model=JobStatusResponse,
    response_model_exclude_none=True,
    responses={404: {"model": ProblemResponse}},
)
def get_job_status(workspaceId: str, jobId: str) -> JobStatusResponse | JSONResponse:
    response = build_job_status_response(workspaceId, jobId)
    if response is not None:
        return response

    problem = build_problem_response(
        code="job_not_found",
        message=f"Job '{jobId}' is not available in the Sprint 0 stub set.",
        suggestion="Try 'initial-bootstrap' or 'photo-index-demo'.",
        workspace_id=workspaceId,
    )
    return JSONResponse(
        status_code=404,
        content=problem.model_dump(mode="json", exclude_none=True),
    )

# Backend

This directory hosts the EkamCore backend service.

## Sprint 0 Scope

- framework: `FastAPI`
- language: Python `3.13`
- milestone: `S0-015` backend skeleton with health, version, Today, Recap, and job-status stubs

## Install

Create a local virtual environment and install the backend dependencies:

```sh
cd /Users/hiteshpoddar/EkamCore/apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

From the repo root:

```sh
pnpm dev:backend
```

This binds the Sprint 0 backend stub to `http://127.0.0.1:8808`, which matches the canonical OpenAPI contract and the manager-app live demo path.

Or from this directory:

```sh
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8808
```

## Stub Endpoints

- `GET /v1/health`
- `GET /v1/version`
- `GET /v1/workspaces/{workspaceId}/today`
- `GET /v1/workspaces/{workspaceId}/recap`
- `GET /v1/workspaces/{workspaceId}/jobs/{jobId}`

## Notes

- The canonical contract lives in `docs/contracts/ekamcore-api.yaml`.
- Stub routes intentionally use response envelopes so client work can begin before real data integrations land.
- Unknown job IDs return a problem envelope instead of an unstructured error body.
- Sprint 0 enables local manager-app/web-shell CORS origins for the thin demo path only; auth enforcement still comes later.

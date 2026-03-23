# API Contract Summary (from ART-08)

## Authentication
- POST /api/v1/auth/login — email+password → {access_token (JWT 15min), refresh_token (cookie 7d), user}
- POST /api/v1/auth/refresh — cookie refresh_token → new token pair. Single-use rotation.
- POST /api/v1/auth/logout — revoke session. Idempotent.

## Core Endpoints
- GET /api/v1/today?workspace_id=&max_cards=20 → ResponseEnvelope with cards
- GET /api/v1/recap?period=daily|weekly&date= → ResponseEnvelope with sections
- POST /api/v1/query {query, workspace_id, filters, prefer_fast} → ResponseEnvelope (query_path in metadata)
- GET /api/v1/search?q=&type=all|file|contact|event|reminder|photo&per_page=20&cursor= → {data[], pagination, facets}

## People & Graph
- GET /api/v1/people?trust_level=all|trusted|candidate → paginated PersonList
- GET /api/v1/people/:id → PersonDetail with linked_objects + graph_edges + undo_history
- POST /api/v1/people/:id/confirm {link_contact_id?} → trust_level=trusted
- POST /api/v1/people/:id/merge {source_person_id} → merged result
- POST /api/v1/people/:id/split {cluster_ids[]} → {original_id, new_person_id}
- POST /api/v1/people/:id/undo → reverses last operation (90-day window)
- GET /api/v1/review-queue?per_page=10 → candidates >=0.7 confidence, sorted DESC

## Resources
- GET /api/v1/photos/:id → photo detail with faces[], metadata
- GET /api/v1/photos/:id/thumbnail → binary JPEG (300px)
- GET /api/v1/files/:id → file detail with ingestion_status, snippet, linked_persons
- GET/POST/PATCH/DELETE /api/v1/sources → CRUD. POST queues ingestion job.

## Write-Through
- POST /api/v1/reminders {title, due_at, list_name, notes, priority} → creates in EkamCore + Apple Reminders
- POST /api/v1/events {title, start_at, end_at, location, calendar_name} → creates in EkamCore + Apple Calendar
- Write-through flow: create pending → call manager EventKit bridge → update status. Rate: 10/min.

## Admin & Settings
- GET/POST /api/v1/admin/users — user management (admin only)
- GET /api/v1/admin/audit-log — paginated audit entries
- POST /api/v1/settings/face-clustering/consent {accepted, consent_version} — grant/revoke biometric consent
- GET /api/v1/flags → all feature flag states + current_phase

## Status
- GET /health — no auth. {status, version, services: {postgres, qdrant, redis, ollama}}
- GET /api/v1/status — auth required. Services + jobs + storage + ingestion progress.

## Pagination
All lists: cursor-based. Request: `per_page` (default 20, max 100) + `cursor` (opaque string). Response: `{data[], pagination: {cursor, per_page, has_more}}`.

## Internal Endpoints (localhost only, no Caddy routing)
- POST /api/v1/internal/ingest/{calendar|reminders|contacts} — manager pushes data
- POST /api/v1/internal/fs-event — FSEvents notification
- GET /api/v1/internal/ingestion-status — per-source progress
- POST /api/v1/internal/write-through/{reminder|event} — EventKit bridge

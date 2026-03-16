# ADR 0006: Authenticated Thumbnail and Preview Delivery

- Status: Accepted
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: Sprint 4 thumbnail and preview work
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/contracts/README.md`

## Context

Mobile, web, and manager-app clients will need thumbnails and previews for files and photos. The API contract document explicitly rejects sending local file paths to clients. Media delivery must remain authenticated and consistent with the same trust model as other application data.

## Decision

Photo thumbnails, full photo delivery, and file previews are delivered through authenticated API endpoints that return binary media responses. Clients receive relative API URLs, not direct local file paths.

## Decision Drivers

- Clients should never depend on local filesystem paths from the hub.
- Media access must follow the same auth and workspace rules as other data.
- Relative API URLs fit the shared contract model better than ad hoc client-specific paths.

## Consequences

### Positive

- Keeps media delivery aligned with application auth and authorization.
- Reduces accidental leakage of local path structure to clients.

### Tradeoffs

- Backend media routes need to be implemented earlier for realistic client validation.
- Media delivery now depends on contract stability and auth middleware quality.

## Alternatives Considered

### Local File Paths in Payloads

- Considered as a shortcut during early prototype work.
- Rejected because local paths are not portable, are unsafe to expose, and do not work for remote mobile clients.

### Separate Unauthenticated Media Server

- Considered as a performance-oriented simplification.
- Rejected because it would complicate trust boundaries and authorization behavior.

## Follow-up Work

- Define the exact thumbnail and preview routes in the OpenAPI contract.
- Implement authenticated media endpoints when real file and photo ingestion begins.

## Notes

This ADR sets the delivery policy. Thumbnail sizing, caching, and derivative generation details will be handled later.

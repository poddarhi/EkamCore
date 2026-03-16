# Architecture Decision Records

This directory contains EkamCore's architecture decision records (ADRs).

ADRs are the repository-level source of truth for important technical and operational decisions that affect multiple areas of the product. They exist so foundational choices do not disappear into chat history, meeting notes, or implementation assumptions.

## ADR Conventions

- File naming: `NNNN-short-kebab-case-title.md`
- Numbering: sequential and permanent
- Template: [`_template.md`](/Users/hiteshpoddar/EkamCore/docs/adr/_template.md)
- Index owner: update this file whenever a new ADR is added, accepted, or superseded

## Status Vocabulary

- `Proposed` - under active evaluation; not yet the repository baseline
- `Accepted` - approved as the current baseline
- `Superseded` - replaced by a newer ADR
- `Deprecated` - still historically relevant but no longer recommended for new work

## ADR Workflow

1. Create a new ADR from the template.
2. Give it the next sequential number.
3. Link related Sprint tasks, docs, and implementation notes.
4. Mark it `Proposed` until the team explicitly accepts it.
5. Update this index in the same change.
6. If a decision is replaced later, leave the original ADR in place and mark it `Superseded`.

## ADR Index

| ADR | Title | Status | Purpose |
| --- | --- | --- | --- |
| [0001](/Users/hiteshpoddar/EkamCore/docs/adr/0001-runtime-substrate.md) | Runtime substrate for local hub services | Proposed | Decide how EkamCore starts, supervises, updates, and repairs local services on the reference Mac. |
| [0002](/Users/hiteshpoddar/EkamCore/docs/adr/0002-api-source-of-truth.md) | API source of truth and generated shared types | Accepted | Lock OpenAPI 3.1 plus generated shared TypeScript artifacts as the contract baseline. |
| [0003](/Users/hiteshpoddar/EkamCore/docs/adr/0003-auth-session-model.md) | Local auth and session model for v1 | Accepted | Record the password-first local auth model and session rules used on LAN and over Tailscale. |
| [0004](/Users/hiteshpoddar/EkamCore/docs/adr/0004-workspace-scoping.md) | Workspace scoping at the API boundary | Accepted | Establish that workspace content must be scoped and enforced at the application boundary. |
| [0005](/Users/hiteshpoddar/EkamCore/docs/adr/0005-private-mobile-access-path.md) | Private Mobile Access path | Accepted | Record the Tailscale-first remote access approach for v1 and its trust boundaries. |
| [0006](/Users/hiteshpoddar/EkamCore/docs/adr/0006-thumbnail-delivery-path.md) | Authenticated thumbnail and preview delivery | Accepted | Lock authenticated API URLs, not local file paths, for media delivery to clients. |
| [0007](/Users/hiteshpoddar/EkamCore/docs/adr/0007-people-graph-trust-model.md) | People Graph trust model | Accepted | Capture the candidate-versus-trusted identity model and review requirements. |

## Sprint 0 Note

`S0-003` requires the ADR template, the ADR index, and initial decision entries to exist before Sprint 0 closes. The ADRs above are intentionally concise starting points. More implementation-specific detail will be added as Sprint 0 and Sprint 1 decisions are finalized.

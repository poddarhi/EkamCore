# Engineering Workflow

This document defines the lightweight collaboration model for EkamCore during Sprint 0 and the early build phases. The goal is to keep a small team aligned without adding heavy process.

## Goals

- Keep the default integration branch stable.
- Make foundational changes visible before they surprise parallel work.
- Prevent drift between code, API contracts, architecture decisions, and product/functional intent.
- Keep review expectations proportionate for a 2-3 engineer team.

## Branching Model

Use short-lived branches created from the default integration branch.

Recommended branch prefixes:

- `feature/<area>-<slug>` for new product or platform work
- `fix/<area>-<slug>` for bug fixes
- `chore/<area>-<slug>` for maintenance and tooling
- `docs/<area>-<slug>` for documentation-only changes
- `spike/<area>-<slug>` for time-boxed investigation work
- `codex/<area>-<slug>` for Codex-authored branches

Examples:

- `feature/backend-health-endpoint`
- `chore/repo-pnpm-workspace`
- `docs/sprint0-workflow`
- `codex/contracts-shared-types`

Rules:

- Branch from the current default integration branch.
- Keep branches focused on one change set or one reviewable objective.
- Rebase or merge from the default branch before opening or merging if the branch has drifted.
- Do not develop unrelated work on the same branch after review has started.

Recommended default branch name: `main`.
If the repository was initialized with a different default branch name, rename it before the first shared remote workflow is established.

## Pull Request Expectations

Every code or repo-change branch should land through a pull request, even for a small team.

Required PR content:

- what changed
- why the change was needed
- impacted areas
- whether the API contract changed
- whether architecture or functional assumptions changed
- how the change was tested

Good PR characteristics:

- small enough to review in one sitting
- one clear objective
- linked follow-up work instead of bundling unrelated cleanup
- screenshots or payload samples when UI or contract shape changes

## Merge Discipline

Use squash merge as the default. This keeps the history readable while still allowing detailed review on the branch.

Rules:

- No direct pushes to the default integration branch except emergency repo-admin actions.
- Do not merge with known broken tests, broken lint, or knowingly stale generated artifacts.
- Resolve review comments before merge, or explicitly mark them as follow-up work in the PR.
- Re-run affected checks after rebasing or after meaningful review-driven changes.

Review expectations:

- Routine implementation or docs changes: one reviewer or disciplined self-review if working solo.
- Foundational changes to contracts, runtime, auth, workspace enforcement, or architecture direction: at least one reviewer plus artifact updates in the same PR.

## Commit Guidance

Keep commits focused and readable. Conventional Commits are recommended but not mandatory.

Preferred examples:

- `feat: add backend health stub`
- `chore: wire shared types generation`
- `docs: add sprint 0 workflow policy`
- `fix: align job status envelope with contract`

## Internal Versioning Policy

EkamCore is pre-release and still establishing its platform spine. For internal repository artifacts, use milestone tags rather than semantic versioning.

Current policy:

- Use milestone-style tags for internal checkpoints such as `sprint-0-complete`, `sprint-1-complete`, or `phase-0-complete`.
- Do not introduce repository-wide semantic version numbers yet.
- Keep software package versions at `0.0.0` or other clearly pre-release placeholders until release engineering is defined.

This keeps versioning simple while the architecture, packaging, and contract shape are still moving. Semantic versioning can be introduced later when release candidates and installable artifacts become real.

## Artifact Change Rules

Foundational artifacts must change in the same review cycle as the code that depends on them. Do not merge silent contract or architecture drift.

### API Contract Changes

Canonical source: `docs/contracts/ekamcore-api.yaml` once introduced.

If a PR changes request or response shape, enums, card types, auth flows, pagination, or media delivery behavior, it must:

- update the canonical contract source
- update generated shared types and clients in `packages/shared-types`
- mention the change in the PR under `API changes`
- call out whether the change is additive or breaking

Breaking contract changes during v1 development require:

- an explicit contract revision note in the PR
- reviewer acknowledgment from backend and at least one affected client surface
- a compatibility plan or coordinated same-PR client updates

### Architecture and Runtime Decision Changes

Canonical source: ADRs in `docs/adr`.

If a PR changes runtime substrate, auth/session model, workspace scoping, storage boundaries, media delivery approach, or other cross-cutting architecture decisions, it must:

- add a new ADR or update/supersede an existing ADR
- summarize consequences and migration impact in the PR
- update any affected README or implementation note

Do not bury foundational architecture reversals inside implementation-only PRs.

### Functional Scope, Roadmap, and Acceptance Changes

Functional and roadmap intent must stay aligned with implementation.

If a PR changes product scope, acceptance criteria, Sprint commitments, or behavior that contradicts the current functional baseline, it must do one of the following before merge:

- update the relevant in-repo product or planning document, or
- explicitly link the external source-of-truth update and summarize the delta in the PR

Until all product docs are moved into the repo, use the PR as the review checkpoint that records:

- what functional assumption changed
- who reviewed it
- which upstream document needs to stay aligned

## Review Checklist for Foundational Changes

Use this checklist when a PR touches contracts, auth, runtime, architecture, or shared workspace behavior:

- Is the canonical artifact updated in the same PR?
- Are generated artifacts refreshed if needed?
- Are downstream surfaces called out explicitly?
- Is the change additive, breaking, or behavior-tightening?
- Does the PR explain rollout or migration expectations?
- Is there any mismatch between code behavior and the current functional baseline?

## Living Policy

This workflow is intentionally lightweight. Update it when the team size, release process, or branching needs change, but do so explicitly through normal review rather than by habit or side conversation.

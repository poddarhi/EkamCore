# Environment Variables

This document is the placeholder index for environment-variable documentation.

## Scope

Every new runtime variable should be documented in two places:

1. The nearest `.env.example` file for the app or package that uses it.
2. This index, so new engineers can find the right source quickly.

## Placeholder Map

| Area | Placeholder file | Status |
| --- | --- | --- |
| Repository-wide tooling | `.env.example` | Placeholder only |
| Backend service | `apps/backend/.env.example` | Placeholder only |
| Manager app | `apps/manager-app/.env.example` | Placeholder only |
| Mobile app | `apps/mobile/.env.example` | Placeholder only |

## Documentation Rules

- Prefer explicit variable names and defaults once a service is runnable.
- Keep secrets out of the repository.
- Update this file when a new app or package introduces its own env file.

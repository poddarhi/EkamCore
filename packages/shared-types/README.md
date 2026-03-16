# Shared Types

This package contains the generated TypeScript artifacts for the EkamCore API contract.

## Source of Truth

- canonical contract: `docs/contracts/ekamcore-api.yaml`
- generator: `openapi-typescript`
- consuming clients: manager app today, mobile and web clients later in Sprint 0+

## Commands

Generate the shared contract types:

```sh
pnpm generate:shared-types
```

Validate the package types:

```sh
pnpm build:shared-types
```

## Notes

- This package is intentionally source-exported inside the monorepo so the manager app can consume generated types without an extra publish step.
- When the contract changes, regenerate this package in the same review cycle.

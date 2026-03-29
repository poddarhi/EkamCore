# Keychain Secrets Design

> This document covers how EkamCore stores, retrieves, and injects service credentials using the macOS Keychain. Implementation lives in `src-tauri/src/keychain.rs` (Sprint 3).

---

## 1. The Six Secrets

| # | Keychain Service Name | Account | Description |
|---|---|---|---|
| 1 | `EkamCore-PostgreSQL` | `ekamcore` | PostgreSQL superuser password (`POSTGRES_PASSWORD`) |
| 2 | `EkamCore-Redis` | `ekamcore` | Redis `requirepass` value (`REDIS_PASSWORD`) |
| 3 | `EkamCore-Qdrant` | `ekamcore` | Qdrant API key (`QDRANT__SERVICE__API_KEY`) |
| 4 | `EkamCore-JWT-Private` | `ekamcore` | RS256 private key PEM (`JWT_PRIVATE_KEY`) |
| 5 | `EkamCore-JWT-Public` | `ekamcore` | RS256 public key PEM (`JWT_PUBLIC_KEY`) |
| 6 | `EkamCore-DataEncryption` | `ekamcore` | 256-bit AES-GCM key, base64-encoded (`DATA_ENCRYPTION_KEY`) |

All items use `kSecClassGenericPassword`. Access is restricted to the EkamCore Manager process via `kSecAttrAccessControl` (this-device-only, user-presence not required at runtime — secrets are unlocked when the login keychain is unlocked).

---

## 2. Rust API

```rust
// src-tauri/src/keychain.rs

use security_framework::passwords::{
    delete_generic_password, get_generic_password, set_generic_password,
};

/// Store (or update) a secret in the macOS Keychain.
pub fn store_secret(service: &str, account: &str, secret: &str) -> anyhow::Result<()> {
    set_generic_password(service, account, secret.as_bytes())?;
    Ok(())
}

/// Read a secret from the Keychain. Returns Err if not found.
pub fn read_secret(service: &str, account: &str) -> anyhow::Result<String> {
    let bytes = get_generic_password(service, account)?;
    Ok(String::from_utf8(bytes)?)
}

/// Delete a secret. Idempotent — does not error if the item does not exist.
pub fn delete_secret(service: &str, account: &str) -> anyhow::Result<()> {
    match delete_generic_password(service, account) {
        Ok(_) => Ok(()),
        Err(e) if e.code() == -25300 /* errSecItemNotFound */ => Ok(()),
        Err(e) => Err(e.into()),
    }
}
```

Service name constants live in `keychain.rs`:

```rust
pub const SVC_POSTGRES:        &str = "EkamCore-PostgreSQL";
pub const SVC_REDIS:           &str = "EkamCore-Redis";
pub const SVC_QDRANT:          &str = "EkamCore-Qdrant";
pub const SVC_JWT_PRIVATE:     &str = "EkamCore-JWT-Private";
pub const SVC_JWT_PUBLIC:      &str = "EkamCore-JWT-Public";
pub const SVC_DATA_ENCRYPTION: &str = "EkamCore-DataEncryption";

pub const ACCOUNT: &str = "ekamcore";
```

---

## 3. Injection Flow: Keychain → Docker → Delete

The goal is to pass secrets to Docker containers **without leaving them on disk** any longer than necessary.

```
┌──────────────────────────────────────────────────────────────────┐
│  Manager App (Rust / startup.rs)                                 │
│                                                                  │
│  1. read_secret(SVC_POSTGRES, ACCOUNT) ──────┐                   │
│  2. read_secret(SVC_REDIS, ACCOUNT)          │                   │
│  3. read_secret(SVC_QDRANT, ACCOUNT)         ▼                   │
│  4. read_secret(SVC_JWT_PRIVATE, ACCOUNT)  Build env map         │
│  5. read_secret(SVC_JWT_PUBLIC, ACCOUNT)     │                   │
│  6. read_secret(SVC_DATA_ENCRYPTION, ACCOUNT)│                   │
│                                              ▼                   │
│  7. Create tmp dir: mkdtemp("/tmp/ekamcore-XXXXXX"), mode 0700   │
│  8. Write tmp/.env  (owner-read-only, mode 0600)                 │
│                                              │                   │
│  9. docker compose --env-file tmp/.env up -d │                   │
│     (blocking; returns when all healthy)     │                   │
│                                              ▼                   │
│ 10. fs::remove_file(tmp/.env)   ◄────────────┘                   │
│ 11. fs::remove_dir(tmp dir)                                      │
└──────────────────────────────────────────────────────────────────┘
```

### Why a temp file instead of passing env vars directly?

`docker compose` does not accept per-variable overrides on the CLI without exposing them in `/proc/<pid>/cmdline`. A short-lived `--env-file` with a `0600` permission file is the least-exposure approach that works with `docker compose` semantics.

### Error handling

- If any `read_secret` call fails (item not found), the startup sequence **aborts at step 3** (Docker check) and displays an "Initial setup required" prompt directing the user to the setup wizard.
- If `remove_file` fails after `docker compose up`, the error is logged (correlation_id, no secret values) and a macOS notification is sent asking the user to manually delete the temp file.

---

## 4. Secret Lifecycle

| Event | Action |
|---|---|
| **First run (Setup Wizard step 6)** | Generate secrets for PG, Redis, Qdrant, DEK. Import user-supplied or generated RSA key pair for JWT. Store all six via `store_secret`. |
| **Normal startup** | Read all six, inject via temp `.env`, delete temp `.env`. |
| **Password rotation** | `store_secret` overwrites the existing Keychain item. Rotation triggers a rolling restart of affected containers. |
| **Factory reset** | `delete_secret` called for all six services. Keychain items removed. Docker volumes wiped. |
| **Backup** | Secrets are **excluded** from the diagnostics ZIP. Keychain items are backed up by macOS iCloud Keychain if the user has that enabled — EkamCore does not control this. |

---

## 5. Secret Generation Rules

| Secret | Generation |
|---|---|
| PostgreSQL password | 32 random bytes, hex-encoded (64 chars) |
| Redis password | 32 random bytes, hex-encoded (64 chars) |
| Qdrant API key | 32 random bytes, base64url-encoded (43 chars, no padding) |
| JWT private key | RSA-4096 via `openssl genrsa` (or `ring::signature::RsaKeyPair`) |
| JWT public key | Derived from private key |
| Data encryption key | 32 random bytes, base64-encoded (44 chars) — used for AES-256-GCM field encryption |

All random bytes sourced from `ring::rand::SystemRandom` (wraps `SecRandomCopyBytes` on macOS).

---

## 6. Docker Compose Variable Mapping

The temp `.env` file sets exactly these variables (consumed by `docker-compose.yml`):

```dotenv
POSTGRES_PASSWORD=<keychain: EkamCore-PostgreSQL>
REDIS_PASSWORD=<keychain: EkamCore-Redis>
QDRANT__SERVICE__API_KEY=<keychain: EkamCore-Qdrant>
JWT_PRIVATE_KEY=<keychain: EkamCore-JWT-Private>
JWT_PUBLIC_KEY=<keychain: EkamCore-JWT-Public>
DATA_ENCRYPTION_KEY=<keychain: EkamCore-DataEncryption>
```

No other secrets are injected via this mechanism. All other configuration (ports, paths, feature flags) comes from the committed `docker-compose.yml` and `config/` directory.

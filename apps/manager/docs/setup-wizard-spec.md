# Setup Wizard Specification (S03-005)

> **Implementation status:** Placeholder — full Tauri 2 implementation starts Sprint 3.
> This document is the authoritative spec for the 8-step first-run wizard.

---

## Overview

The Setup Wizard runs **once** on the very first launch of the EkamCore Manager app
and never again once setup is complete.  Its job is to verify the host environment,
bootstrap the Docker stack, create the admin account, and capture source permissions
before handing off to the normal Dashboard.

**State persistence:** `~/Library/Application Support/EkamCore/setup-state.json`
Each step writes its own `status` field (`pending | in_progress | passed | failed |
skipped`) plus any metadata (free bytes found, admin user UUID, etc.) so a crash-
restart can resume from the last incomplete step.

**Navigation rules:**
- Steps are displayed as a left-side progress rail (icon + label + status badge).
- User can only advance when the current step passes (or is explicitly skippable).
- The Back button is always enabled (re-runs the step's check on re-entry).
- Errors surface an inline callout with a human-readable message and a "Try Again"
  button — never a raw error code.
- Cmd+W closes the window but the wizard state is preserved; next launch resumes.

---

## Step 1 — Hardware Check

**Purpose:** Confirm the host meets the minimum requirements for running EkamCore.

| Check | Pass condition | Fail message |
|-------|---------------|--------------|
| CPU architecture | `sysctl hw.optional.arm64 = 1` (Apple Silicon) | "EkamCore requires an Apple Silicon Mac (M1 or later)." |
| RAM | ≥ 16 GB physical (`sysctl hw.memsize`) | "EkamCore requires at least 16 GB of RAM. This Mac has {n} GB." |
| macOS version | ≥ Ventura 13.0 (`sw_vers -productVersion`) | "EkamCore requires macOS Ventura 13.0 or later. You are running {version}." |

**UI:** Three check-row items, each with a spinner → green tick / red cross. All three
checks run in parallel. "Continue" is enabled only when all three pass.

**On failure:** The app shows which checks failed with the measured vs. required value.
"Continue Anyway" is **not** available — these are hard blockers.

**Rust implementation hint (`startup.rs` / `wizard.rs`):**
```rust
let arch = std::process::Command::new("sysctl")
    .args(["-n", "hw.optional.arm64"])
    .output()?;
let ram_bytes: u64 = sysctl::value("hw.memsize")?.into();
let os_ver = std::process::Command::new("sw_vers")
    .args(["-productVersion"])
    .output()?;
```

---

## Step 2 — Disk Space

**Purpose:** Ensure there is enough free space for Docker images, the PostgreSQL
data volume, Qdrant vectors, Ollama model weights, and working files.

| Check | Requirement | Notes |
|-------|-------------|-------|
| Free disk space on the boot volume | ≥ 30 GB | `statvfs("/")` — `f_bavail × f_frsize` |
| Docker data root free space | ≥ 30 GB | If Docker is already installed, also check `docker info --format '{{.DockerRootDir}}'` volume |

**UI:** A horizontal disk-usage bar showing used vs. free space. A second row
showing "EkamCore requires 30 GB free — you have {n} GB free."

**On failure:** "You have {n} GB free space. EkamCore needs at least 30 GB.
Free up disk space and click Try Again."

**Advisory (pass with warning):** 30–40 GB free shows a yellow ⚠ "Tight on space —
consider clearing more before ingesting large photo libraries."

---

## Step 3 — Docker / OrbStack

**Purpose:** Verify that a compatible container runtime is installed and currently
running.

**Supported runtimes (either is accepted):**
- Docker Desktop ≥ 4.20 (detected via `docker version --format '{{.Server.Version}}'`)
- OrbStack ≥ 1.0 (same CLI, different socket path `/var/run/docker.sock` still works)

| Check | Pass condition |
|-------|---------------|
| Runtime installed | `docker version` exits 0 |
| Daemon running | `docker info` exits 0 within 5 s |
| API version | Server API ≥ 1.43 |

**UI:** Two rows: "Docker / OrbStack installed" and "Docker daemon running."

**On failure — not installed:**
"Docker Desktop or OrbStack is not installed. Please install one before continuing."
Provide two links: [Download Docker Desktop] and [Download OrbStack].

**On failure — installed but not running:**
"Docker is installed but not running. Please start Docker Desktop (or OrbStack) and
click Try Again."

**Note:** The wizard does NOT install Docker — that is intentionally outside its
scope to avoid privilege escalation.

---

## Step 4 — Pull Images

**Purpose:** Download all Docker images required by the stack. This is the longest-
running step.

**Images to pull (from `docker-compose.yml`):**
| Image | Approx size |
|-------|------------|
| `postgres:16-alpine` | ~100 MB |
| `redis:7-alpine` | ~40 MB |
| `qdrant/qdrant:latest` | ~200 MB |
| `ghcr.io/paperless-ngx/paperless-ngx:latest` | ~1.2 GB |
| `ekamcore-api` (local build) | ~500 MB |
| `ekamcore-workers` (local build) | ~500 MB |
| `ekamcore-web` (local build) | ~300 MB |
| `caddy:2-alpine` | ~50 MB |

**UI:**
- Overall progress bar (0–100 %, computed from bytes pulled / bytes total across all
  images).
- Per-image collapsible row: image name, layer progress bars, speed (MB/s).
- "Pulling X of N images" subtitle.
- Estimated time remaining (rolling 10-second average).

**Implementation:**
Use bollard's `create_image` stream, which emits `CreateImageInfo` events with
`progressDetail.current` / `progressDetail.total`.  Accumulate across all images.

**On failure:** Show which image failed and the Docker error message. Offer "Retry
Failed Images" (re-pulls only the failed ones, not all).

**Pre-check:** Before pulling, run `docker images --format json` and skip images
that are already present at the required digest — show them as "Already present ✓".

---

## Step 5 — Initialize Database

**Purpose:** Run Alembic migrations to bring the PostgreSQL schema to the current
version.

**Sequence within this step:**
1. Start the `ekamcore-postgres` container only (via bollard).
2. Poll `pg_isready -h localhost -p 5432 -U ekamcore` every 2 s, timeout 30 s.
3. Run the `ekamcore-migrate` container (`alembic upgrade head`).
4. Tail its stdout/stderr into the collapsible log pane.
5. On exit code 0 — migration complete.

**UI:**
- Status: "Starting PostgreSQL…" → "Waiting for PostgreSQL…" → "Running
  migrations…" → "Database ready ✓"
- Collapsible "Migration log" pane (hidden by default, "Show log" link).

**On failure:**
- PostgreSQL timeout: "PostgreSQL did not start within 30 s.
  Check Docker logs: `docker logs ekamcore-postgres`"
- Migration error: show the last 20 lines of migration output inline and a link
  to "View full log."

**Idempotency:** The migrate container is idempotent — safe to re-run.

---

## Step 6 — Create Admin Account

**Purpose:** Create the first (admin) user via the EkamCore API.

**Prerequisite:** The API must be running.  If it is not already started, this step
starts it (alongside Redis, Qdrant) before presenting the form.

**Form fields:**
| Field | Validation |
|-------|-----------|
| Email address | RFC 5322 format, max 254 chars |
| Password | ≥ 12 chars, at least one uppercase, one digit, one symbol |
| Confirm password | Must match password field |

**Privacy note displayed on the form:**
> "Your credentials are stored locally in the macOS Keychain and are never sent
> to any external server."

**Submission flow:**
1. POST `http://localhost:8420/api/v1/auth/admin/bootstrap` with `{email, password}`.
   *(This endpoint is created in a later sprint — see S05-001. For now, document the
   intended interface.)*
2. On 201: store the access token in Keychain (`EkamCore-AdminToken`), store the
   email in Keychain (`EkamCore-AdminEmail`).
3. Advance to Step 7.

**On failure:**
- 422 validation error from API: surface each field error inline.
- Connection refused: "The EkamCore API is not running. Click Try Again to restart it."

**Re-entry:** If setup-state.json records that Step 6 is already complete, this step
is shown as "Account created ✓ — {email}" and the form is replaced by a "Change
admin password" link (disabled in placeholder).

---

## Step 7 — Configure Sources

**Purpose:** Grant macOS permissions for Apple framework data sources and configure
folder paths for file-based sources.

### 7a — Apple Framework Sources

Three toggles; each, when turned on, triggers a macOS privacy permission request:

| Toggle | Permission | TCC key |
|--------|-----------|---------|
| Calendar | Read calendar events | `NSCalendarsUsageDescription` |
| Reminders | Read & write reminders | `NSRemindersUsageDescription` |
| Contacts | Read contacts | `NSContactsUsageDescription` |

**UI per toggle:**
- Label + subtitle ("Sync events from your Apple Calendar")
- Toggle switch
- Status badge: "Not requested" → "Permission granted ✓" / "Permission denied ✗"
- "Open System Settings" link if denied

**Behaviour:**
- Toggling on → call `CNContactStore.requestAccess` / `EKEventStore.requestAccess`
  (bridged via Tauri Objective-C bridge).
- Toggling off does **not** revoke the OS permission; it only sets the source to
  `disabled` in setup-state.json (the API source record is not created).
- If the user granted permission in a previous run, the toggle starts in the on
  position and shows "Permission granted ✓" immediately.

### 7b — Folder Sources

| Source | Default path | Notes |
|--------|-------------|-------|
| Documents folder | `~/Documents` | Folder picker, user can change |
| Photos library | `~/Pictures/Photos Library.photoslibrary` | Auto-detected; read-only |

**UI per folder source:**
- Label + subtitle
- Toggle to enable/disable
- Read-only text field showing the path + "Browse…" button
- "Folder accessible ✓" / "Folder not found ✗" inline validation after selection

**Note on Photos source:** The Photos permission (`NSPhotoLibraryUsageDescription`)
and embedding pipeline are Phase 2 features (S08-001). The toggle is rendered but
grayed out with the label "Available in a future update."

### 7c — Source Registration

On "Continue", for each enabled source in 7a and 7b:
1. POST `/api/v1/sources` with `{name, type, path}` using the admin token.
2. The `source_id` is saved to setup-state.json for use by the EventKit bridge.

Disabled sources are skipped entirely — no source record is created.

### 7d — PaperlessNGX Configuration

This sub-step configures the document auto-ingest pipeline.  It runs after 7c and
has four sequential phases.  Each phase is shown as a collapsible row in the UI.

**User-facing headline:**
> "Drop documents in this folder and they'll be automatically organized and made
> searchable inside EkamCore."

#### Phase 1 — Consume Folder

The user picks the folder that Paperless monitors for new files.

| Element | Behaviour |
|---------|-----------|
| Toggle "Enable document auto-ingest" | On by default. Turning it off skips 7d entirely. |
| Path field + "Browse…" | Native `NSOpenPanel` (directories only). Default: `~/Documents/EkamCore Inbox`. |
| "Create folder" link | Appears when the typed path does not exist — creates it via `std::fs::create_dir_all`. |
| Inline validation | Checks path is writable; rejects system directories (`/`, `/System`, `/Library`, etc.). |

After confirmation the Manager writes `PAPERLESS_CONSUME_DIR=<path>` (and
`PAPERLESS_TIME_ZONE` / `PAPERLESS_OCR_LANGUAGE`) to
`~/Library/Application Support/EkamCore/.env` using a line-level rewrite that
preserves all other variables, then runs:
```
docker compose up -d paperless-ngx --no-deps
```

#### Phase 2 — API Token Generation

A dedicated `ekamcore_service` Paperless user is created and a long-lived token is
generated for it.  The token is stored in the macOS Keychain
(`EkamCore-Paperless` / `ekamcore_service`) and the EkamCore API is notified via
`POST /api/v1/admin/paperless/configure`.  The Manager never logs the token value.

If Keychain access is denied the wizard surfaces:
> "Could not save the Paperless token to your Keychain.  Please allow access and
> try again."

#### Phase 3 — Integration Verification

An end-to-end smoke test confirms documents flow from the consume folder into the
EkamCore search index:

```
[✓] Writing test document to consume folder…
[↻] Waiting for Paperless to process document… (up to 2 min)
[✓] Document processed by Paperless ✓
[↻] Waiting for EkamCore to index document… (up to 1 min)
[✓] Document searchable in EkamCore ✓
[✓] Cleaning up test document…
[✓] PaperlessNGX integration verified ✓
```

A synthetic PDF (< 10 KB, embedded in the Manager binary) is written to the consume
folder, polled in Paperless (`GET /api/documents/?search=EKAMCORE-SETUP-VERIFY`),
then verified in EkamCore search (`GET /api/v1/search?q=EKAMCORE-SETUP-VERIFY&type=file`),
and deleted from both systems.

If the EkamCore search check times out (embedding pipeline still starting), a
**"Continue Anyway"** affordance (yellow ⚠) is offered — search will work once the
pipeline is ready.

**Full specification:** `apps/manager/docs/paperless-integration.md`

---

## Step 8 — Tailscale Setup (Optional)

**Purpose:** Optionally configure Tailscale so EkamCore is reachable from other
devices on the user's tailnet (e.g., iPhone via mobile app).

**This step is always skippable.** A "Skip for now" button is always visible.

**UI:**
1. Explanation card: "Tailscale lets you securely access EkamCore from your phone
   or other devices. You can set this up later from Settings → Network."
2. "Is Tailscale installed?" check (look for `/Applications/Tailscale.app` and
   `tailscale status` exit code).
3. If installed and running: show the machine's Tailscale IP (`tailscale ip -4`)
   and a "Copy address" button.
4. If not installed: link to [Download Tailscale] — wizard does not install it.

**On skip:**
- Write `{"tailscale": {"status": "skipped"}}` to setup-state.json.
- Advance to the completion screen.

**Completion screen (after Step 8):**
- "EkamCore is ready!" heading.
- Summary card: containers running, sources configured, Tailscale status.
- "Open Dashboard" button → closes wizard, shows Dashboard tab.
- Writes `{"wizard_completed_at": "<ISO-8601 timestamp>"}` to setup-state.json.
- From this point the wizard tab is hidden from the sidebar.

---

## State File Schema

```json
{
  "schema_version": 1,
  "wizard_completed_at": null,
  "steps": {
    "hardware": { "status": "passed", "cpu": "arm64", "ram_gb": 32, "macos": "14.4" },
    "disk": { "status": "passed", "free_gb": 245 },
    "docker": { "status": "passed", "runtime": "OrbStack", "api_version": "1.44" },
    "pull_images": { "status": "passed", "images_pulled": 8 },
    "init_db": { "status": "passed", "alembic_revision": "006" },
    "admin_account": { "status": "passed", "admin_email": "admin@ekamcore.dev" },
    "sources": {
      "status": "passed",
      "calendar": { "enabled": true, "permission": "granted", "source_id": "uuid" },
      "reminders": { "enabled": true, "permission": "granted", "source_id": "uuid" },
      "contacts": { "enabled": true, "permission": "granted", "source_id": "uuid" },
      "documents": { "enabled": true, "path": "~/Documents", "source_id": "uuid" },
      "paperless": {
        "enabled": true,
        "consume_dir": "/Users/alice/Documents/EkamCore Inbox",
        "token_stored": true,
        "verify_status": "passed",
        "verify_doc_id": null,
        "configured_at": "2026-04-10T14:32:00Z"
      }
    },
    "tailscale": { "status": "skipped" }
  }
}
```

---

## Error Handling Conventions

| Scenario | Behaviour |
|----------|-----------|
| Step times out | Show timeout message, "Try Again" resets the timeout |
| Docker daemon stops mid-wizard | Surface error on current step, offer "Restart Docker" shortcut |
| API unreachable in Step 6+ | Attempt to start API container; show progress; surface error if it fails |
| Setup state file corrupt / unreadable | Warn user, offer to start wizard from scratch (backup corrupt file first) |
| User force-quits mid-step | On relaunch: resume from last `in_progress` step, re-run it from the start |


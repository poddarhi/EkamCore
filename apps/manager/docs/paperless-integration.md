# PaperlessNGX Integration (S08-006)

> **Implementation status:** Documentation — Tauri 2 implementation planned for Sprint 8.
> This document is the authoritative spec for how the Manager app configures and verifies
> PaperlessNGX during the Setup Wizard (Step 7) and on subsequent health checks.

---

## Overview

PaperlessNGX is the document management backend embedded in the EkamCore Docker stack.
The Manager app is responsible for:

1. **Consume folder selection** — let the user pick (or confirm) the folder that Paperless
   monitors for new documents to ingest automatically.
2. **Environment configuration** — write `PAPERLESS_CONSUME_DIR` (and related vars) to the
   `.env` file before the stack starts.
3. **API token generation** — create a Paperless API token scoped to the `ekamcore` service
   user and store it in the macOS Keychain so the EkamCore API can call Paperless securely.
4. **Integration verification** — POST a synthetic test document, confirm it appears in both
   Paperless and the EkamCore search index, then remove it.

These four phases run in sequence inside **Setup Wizard Step 7 — Configure Sources**, in the
new sub-step **7d — PaperlessNGX** (inserted after the existing folder sources in 7b).

---

## Phase 1 — Consume Folder Selection

### User-facing copy

> **"Drop documents here for automatic organization"**
>
> Choose a folder on your Mac. Any document you drop into this folder — PDFs, Word files,
> spreadsheets, images of receipts — is automatically organized, OCR-processed, and made
> searchable inside EkamCore. You can use any folder you like; we recommend creating a
> dedicated one such as `~/Documents/Inbox`.

### UI elements

| Element | Behaviour |
|---------|-----------|
| Toggle "Enable document auto-ingest" | Enabled by default. Turning it off skips this entire sub-step. |
| Path text field | Shows the currently selected path (default `~/Documents/EkamCore Inbox`). |
| "Browse…" button | Opens a native `NSOpenPanel` restricted to directories. |
| Inline validation | After selection: check the path exists and is writable. Show "Folder accessible ✓" or "Cannot write to this folder ✗". |
| "Create folder" affordance | If the typed path does not exist, show a "Create this folder" link that calls `std::fs::create_dir_all`. |

### Default path logic

```
1. Check setup-state.json for a previously saved consume path.
2. If absent, use ~/Documents/EkamCore Inbox.
3. Create the directory if it does not exist.
```

### Validation rules

- Path must be absolute (resolve `~` to `$HOME`).
- Path must not be a system directory: `/`, `/System`, `/Library`, `/usr`, `/bin`,
  `/Applications`, or any parent of those.
- The Tauri process must be able to create a temp file inside the path (write-access test).
- Path length ≤ 255 bytes (filesystem limit).

---

## Phase 2 — Environment Configuration

### Writing PAPERLESS_CONSUME_DIR to .env

The `.env` file lives at `~/Library/Application Support/EkamCore/.env` (next to
`docker-compose.yml`).  After the user confirms the consume folder, the Manager app
updates the file **in-place** using a line-by-line rewrite (never a full overwrite) to
preserve any other user-edited vars.

**Rust helper (`env_writer.rs`):**

```rust
/// Update or insert a key=value line in an .env file.
/// Preserves all other lines (including comments) unchanged.
pub fn set_env_var(path: &Path, key: &str, value: &str) -> std::io::Result<()> {
    let content = std::fs::read_to_string(path).unwrap_or_default();
    let mut lines: Vec<String> = content.lines().map(String::from).collect();
    let prefix = format!("{}=", key);
    let new_line = format!("{}={}", key, value);

    if let Some(pos) = lines.iter().position(|l| l.starts_with(&prefix)) {
        lines[pos] = new_line;
    } else {
        lines.push(new_line);
    }
    std::fs::write(path, lines.join("\n") + "\n")
}
```

**Variables written during this phase:**

| Variable | Value | Notes |
|----------|-------|-------|
| `PAPERLESS_CONSUME_DIR` | User-selected path (absolute) | Required by Paperless container |
| `PAPERLESS_OCR_LANGUAGE` | `eng` | Default; user can change in Settings later |
| `PAPERLESS_TIME_ZONE` | System time zone (from `NSTimeZone.local`) | Ensures correct document timestamps |

**After writing**, the Manager app calls `docker compose up -d paperless-ngx --no-deps` to
apply the new environment without restarting the full stack.

---

## Phase 3 — API Token Generation

The EkamCore API (Python/FastAPI) calls Paperless's REST API to search documents and
retrieve content. It authenticates with a **dedicated service-account token**, not the admin
password. The Manager app is responsible for generating this token and storing it safely.

### Service account

A dedicated `ekamcore_service` user is created inside Paperless (separate from the admin
account used in the Paperless web UI). This user has read-only access to documents and full
access to tags/correspondents/document-types (needed for the contact bridge).

### Generation flow

```
1. Wait for Paperless to be healthy:
   Poll GET http://localhost:28981/api/ with admin credentials every 3 s, timeout 60 s.

2. Create the service user (idempotent):
   POST http://localhost:28981/api/users/
   Body: { "username": "ekamcore_service", "password": "<generated>", "is_staff": false }
   If username already exists, skip creation (200 on conflict is acceptable).

3. Generate a token for the service user:
   POST http://localhost:28981/api/token/
   Body: { "username": "ekamcore_service", "password": "<generated>" }
   Response: { "token": "<40-char hex string>" }

4. Store the token in the macOS Keychain:
   keychain service: "EkamCore-Paperless"
   keychain account: "ekamcore_service"
   keychain value:   "<token>"

5. Write PAPERLESS_API_TOKEN to .env (for docker-compose health-check scripts only —
   the production path reads directly from Keychain via the Tauri bridge):
   set_env_var(&env_path, "PAPERLESS_API_TOKEN", &token)

6. POST http://localhost:8420/api/v1/admin/paperless/configure
   Body: { "base_url": "http://localhost:28981", "token": "<token>" }
   This call tells the EkamCore API to reload its Paperless client.
```

### Password generation

The service-account password is a 32-character random alphanumeric string generated with
`rand::distributions::Alphanumeric` from the Rust `rand` crate. It is stored alongside the
token in Keychain under account `"ekamcore_service_password"` in case re-generation is needed.

### Security notes

- The token is written to `.env` **only** as a fallback for scripts; the running API process
  reads from Keychain exclusively.
- The Manager app never logs the token value — only `"Paperless token stored in Keychain ✓"`.
- If Keychain storage fails (e.g., user denies access), the wizard surfaces an error:
  > "Could not save the Paperless token to your Keychain. EkamCore requires Keychain access
  > to securely connect to document management. Please allow access and try again."

---

## Phase 4 — Integration Verification

After the token is stored, the wizard performs an end-to-end smoke test to confirm that
documents flow from the consume folder through Paperless into the EkamCore search index.

### Test document

A minimal synthetic PDF is embedded in the Manager binary (< 10 KB) containing:

```
EkamCore Setup Verification Document
This document was created automatically during EkamCore setup.
It will be deleted immediately after the verification step completes.
Reference: EKAMCORE-SETUP-VERIFY-{uuid_v7}
```

The embedded file is written to the consume folder as `ekamcore-verify-{uuid}.pdf`.

### Verification sequence

```
Step A — Ingest wait
  Write the test PDF to PAPERLESS_CONSUME_DIR.
  Poll GET http://localhost:28981/api/documents/?search=EKAMCORE-SETUP-VERIFY
  every 3 s, timeout 120 s.
  Pass condition: response `count` > 0.
  The document ID is saved as `verify_doc_id`.

Step B — EkamCore search
  Poll GET http://localhost:8420/api/v1/search?q=EKAMCORE-SETUP-VERIFY&type=file
  every 5 s, timeout 60 s (the embedding pipeline runs asynchronously).
  Pass condition: response `total` > 0.

Step C — Cleanup
  DELETE http://localhost:28981/api/documents/{verify_doc_id}/
  Remove the physical file from the consume folder if it still exists
  (Paperless normally moves it).
```

### UI during verification

```
[✓] Writing test document to consume folder…
[↻] Waiting for Paperless to process document… (up to 2 min)
[✓] Document processed by Paperless ✓
[↻] Waiting for EkamCore to index document… (up to 1 min)
[✓] Document searchable in EkamCore ✓
[✓] Cleaning up test document…
[✓] PaperlessNGX integration verified ✓
```

Each row has a spinner that becomes a green tick on success or a red cross with inline error
on failure.

### Partial-pass handling

| Scenario | User-facing message | Action |
|----------|---------------------|--------|
| Step A times out | "Paperless did not process the test document within 2 minutes. This can happen on first run when models are downloading. Click **Try Again** once Paperless is fully started." | Offer retry; wizard does not advance |
| Step B times out | "The document was processed by Paperless but did not appear in EkamCore search yet. The embedding pipeline may still be starting. Click **Continue Anyway** to skip this check — search will work once the pipeline is ready." | **Continue Anyway** is offered (yellow ⚠, not red ✗) |
| Step C fails (cleanup) | Log the failure silently; do not surface to user. The test document will be processed normally and will appear in the library. | No user action required |

---

## setup-state.json additions

```json
"paperless": {
  "enabled": true,
  "consume_dir": "/Users/alice/Documents/EkamCore Inbox",
  "token_stored": true,
  "verify_status": "passed",
  "verify_doc_id": null,
  "configured_at": "2026-04-10T14:32:00Z"
}
```

---

## Re-entry and idempotency

| Situation | Behaviour |
|-----------|-----------|
| User re-opens wizard after completing Step 7 | Paperless sub-step shows "Configured ✓" summary: consume dir, token present badge, last verified date. A "Re-verify" button reruns Phase 4 only. |
| Token missing from Keychain (e.g., after migration) | Sub-step shows "Token missing — click Regenerate" which reruns Phase 3 and 4. |
| Consume dir moved or deleted | Dashboard watchdog surfaces a warning notification; user can update the path from Settings → Sources. |
| User disables the Paperless toggle on re-entry | Sets `paperless.enabled = false` in setup-state.json. Does not delete the token or revoke the Paperless user — makes re-enabling cheap. |

---

## Settings → Sources (post-wizard)

After setup, the user can reconfigure Paperless from **Manager → Settings → Sources →
Document Management**:

- Change the consume folder path (triggers `.env` rewrite + container restart).
- View the API token fingerprint (first 8 chars + `…`).
- Regenerate the token (runs Phase 3 again).
- Run the verification test again (Phase 4).
- View Paperless logs (`docker logs ekamcore-paperless --tail 100`).

---

## Related files

| File | Purpose |
|------|---------|
| `apps/manager/src-tauri/src/paperless.rs` | Rust module: consume dir picker, .env writer, token generation, verify flow |
| `apps/manager/src/pages/wizard/PaperlessStep.tsx` | React UI for setup wizard sub-step 7d |
| `apps/manager/src/pages/settings/PaperlessSettings.tsx` | React UI for post-wizard settings panel |
| `apps/api/routers/admin.py` | `POST /api/v1/admin/paperless/configure` endpoint (reload Paperless client) |
| `apps/api/services/paperless_client.py` | Paperless REST API wrapper used by EkamCore search |

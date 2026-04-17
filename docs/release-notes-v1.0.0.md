# EkamCore v1.0.0 Release Notes

**Released:** April 17, 2026

---

## Highlights

EkamCore v1.0 is the first stable release of your private, local-first life assistant. It runs entirely on your Apple Silicon Mac — no cloud services, no telemetry, no external APIs. Your data never leaves your machine.

---

## What's Inside

### Today and Recap
Your day and week at a glance, powered by Calendar, Reminders, Contacts, and your documents. Time-of-day greetings, confidence-badged cards, and daily/weekly recap with date navigation.

### Ask Anything
Search across your files, photos, events, contacts, and people with instant results. Or ask a natural language question and get a cited, AI-grounded answer — all processed locally using Ollama.

### People Graph
Face clustering (opt-in, fully consent-gated and encrypted) groups your photos by the people in them. Review candidates in a swipe-based queue. Merge, split, rename, and manage person profiles across all your data.

### Personal Life Assistant (PLA)
Daily follow-up suggestions based on who you've been in contact with. Weekly summaries that know your people. Relationship reminders scored by graph strength. All deterministic or locally-generated — no cloud AI.

### Mobile Access (iOS)
iPhone app with secure Tailscale-based hub access. Biometric unlock (Face ID / Touch ID), encrypted offline cache (SQLCipher), six-state connectivity awareness. Today, Recap, Search, People, and Settings — all from your phone.

### Manager App (macOS)
First-class native macOS installer and control plane built with Tauri 2. Eight-step setup wizard, real-time health dashboard with watchdog auto-restart, diagnostics export, storage management, and safe updates with automatic rollback.

---

## By the Numbers

| Metric | Value |
|--------|-------|
| Docker services | 10 (PostgreSQL, Redis, Qdrant, Ollama, API, Workers, Web, Proxy, PaperlessNGX, Migrate) |
| Database tables | 20+ |
| API endpoints | 60+ |
| Architecture documents (ARTs) | 28 |
| Development sprints | 16 (32 weeks) |
| Stories implemented | 130+ |
| Python test functions | 1,158 |
| Rust unit tests | 55 |
| Mobile E2E test cases | ~45 |
| Chaos test scenarios | 7 |
| User documentation pages | 34 |
| Test traceability stories | 104 |
| Performance benchmarks | 21/21 PASS |

---

## Privacy and Security

- **All data stays on your Mac.** No cloud. No telemetry. No external API calls.
- Face embeddings encrypted at rest with Fernet (AES-128-CBC + HMAC)
- Consent-gated face clustering with synchronous hard-delete on opt-out
- TLS everywhere (Caddy auto-certificates), including between local services
- Keychain-backed secret management (8 service secrets, RSA-2048 JWT keypair)
- JWT RS256 auth with refresh token rotation and brute-force protection
- CSRF protection on all state-changing endpoints
- Workspace isolation on every database query and vector search
- SBOM (SPDX) included — all dependencies audited, zero GPL/AGPL
- Pen test checklist: 25 automated checks across 9 security categories

---

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| macOS | 13 (Ventura) | 15 (Sequoia) |
| Processor | Apple Silicon (M1) | M2 Pro or later |
| RAM | 16 GB | 24 GB |
| Disk Space | 30 GB free | 50 GB free |
| Docker | Docker Desktop or OrbStack | OrbStack (lighter) |

---

## Installation

1. Download `EkamCore-Manager-v1.0.0.dmg` from the [GitHub Release](https://github.com/poddarhi/EkamCore/releases/tag/v1.0.0)
2. Open the DMG
3. **Double-click "Install EkamCore.command"** — this copies the app to Applications and removes the macOS quarantine flag
4. EkamCore Manager will launch automatically
5. Click **"Install EkamCore"** — the app handles everything else (Docker, Ollama, images, models)
6. Open https://localhost in your browser when setup completes

> **Important:** Do NOT drag the app to Applications manually on first install.
> Use the "Install EkamCore.command" script instead. This prevents the
> "app is damaged" error from macOS Gatekeeper (the app is not yet code-signed).
>
> If you already see the "damaged" error, open Terminal and run:
> ```
> xattr -cr "/Applications/EkamCore Manager.app"
> ```

---

## Known Limitations

These are documented design decisions, not bugs:

| Limitation | Planned For |
|-----------|-------------|
| Dark mode / theme switching | v1.1 |
| Android mobile app | v1.1 (iOS only in v1.0) |
| Push notifications | v1.1 (in-app only in v1.0) |
| Command palette (Cmd+K) | v1.1 |
| Public Skill SDK | v1.1 (PLA pack is first-party only) |
| Multi-language i18n | v1.1 (English only, strings externalized) |

---

## Roadmap Preview

### v1.1 (planned)
- Dark mode with system preference detection
- Android mobile app
- Push notifications via APNs
- Command palette for power users
- Additional PLA pack workflows

### v1.2 (planned)
- Public Skill SDK for third-party packs
- Advanced photo search (by scene, object, color)
- Calendar write-back (create events from suggestions)

### v1.3 (planned)
- Multi-user household mode
- Shared workspaces
- Apple Watch companion

---

## Acknowledgments

EkamCore is built on the shoulders of outstanding open-source projects:

- [FastAPI](https://fastapi.tiangolo.com/) — Python API framework
- [PostgreSQL](https://www.postgresql.org/) — Relational database
- [Qdrant](https://qdrant.tech/) — Vector search engine
- [Ollama](https://ollama.ai/) — Local LLM inference
- [Redis](https://redis.io/) — Cache and queue
- [Caddy](https://caddyserver.com/) — TLS proxy
- [PaperlessNGX](https://docs.paperless-ngx.com/) — Document management
- [Tauri](https://tauri.app/) — Native app framework
- [React Native](https://reactnative.dev/) — Mobile framework
- [InsightFace](https://insightface.ai/) — Face detection and recognition

---

*EkamCore v1.0.0 — Your life, your data, your Mac.*

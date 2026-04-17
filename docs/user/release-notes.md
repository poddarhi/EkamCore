# Release Notes

## v1.0.0 -- Initial Release

Released: April 2026

EkamCore v1.0.0 is the first public release of the privacy-first local
life assistant for Apple Silicon Macs.

### Today and Recap

- **Today briefing** with daily cards: calendar events, tasks, weather
  summary, and PLA-generated suggestions.
- **Recap** view summarizing the previous day's activity, completed tasks,
  and highlights.
- Card actions: dismiss, snooze, pin, and share to other views.

### Search and Query

- **Natural-language search** across documents, photos, notes, and
  contacts powered by local LLM inference via Ollama.
- **Semantic search** using vector embeddings stored in Qdrant.
- **Full-text search** via Meilisearch with typo tolerance and instant
  results.
- Search tips and filters: date ranges, file types, source folders, and
  person names.

### People Graph

- **Face clustering** with on-device face detection and embedding.
  Groups photos by person automatically.
- **Person profiles** showing contact info, recent interactions, related
  documents, and photo timeline.
- **Review queue** for confirming or correcting face cluster assignments.
- **Privacy controls**: disable clustering, delete all face data, exclude
  specific folders.

### Photos and Files

- Photo browsing with metadata display (EXIF, location, camera).
- Document ingestion and OCR via PaperlessNGX.
- Support for 50+ file formats including PDF, DOCX, XLSX, images, and
  plain text.
- Source folder management with ignore patterns and on-demand re-scan.

### Mobile

- **iOS app** for iPhone and iPad with five tabs: Today, Recap, Search,
  People, and Settings.
- **Tailscale integration** for secure private-network access with no
  port forwarding or public exposure.
- **Offline mode** with six connectivity states and per-tab cache TTLs.
- Biometric unlock via Face ID or Touch ID.
- Secure wipe on logout.

### Manager

- **Native macOS Manager app** with setup wizard, dashboard, jobs, storage,
  diagnostics, and update management.
- **Ten managed services**: API Server, PostgreSQL, Meilisearch, Ollama,
  PaperlessNGX, Redis, Qdrant, Face Clustering, PLA Engine, Nginx.
- **Watchdog** with automatic health checks every 30 seconds and
  auto-restart of unhealthy services.
- **One-click updates** with an eight-step process, automatic rollback on
  failure, and manual rollback from backup history.
- Scheduled and on-demand backups with configurable retention.

### PLA Pack

- **Personal Life Assistant** suggestion engine with five workflows:
  Morning Briefing, Evening Recap, Contact Follow-up, Photo Memories,
  Document Digest.
- Per-workflow enable/disable toggles.
- Configurable delivery schedule.

---

### Known Limitations

- **Dark mode**: The web interface does not yet support dark mode. A dark
  theme is planned for v1.1.
- **Android app**: Only iOS is supported at launch. Android is planned for
  a future release.
- **Push notifications**: The mobile app does not support push
  notifications in v1.0. Notifications are planned for v1.1.
- **Multi-user**: EkamCore currently supports a single user per instance.
  Multi-user access control is on the roadmap.
- **Intel Macs**: Not supported. Apple Silicon (M1 or later) is required
  for local AI inference.

### Roadmap Preview

Planned for upcoming releases:

- **v1.1**: Dark mode for web UI, push notifications, improved PLA
  suggestion relevance, reduced memory footprint.
- **v1.2**: Android app, multi-user access control, shared family
  instance mode.
- **v1.3**: Plugin system for third-party integrations, calendar sync
  with CalDAV providers, task manager integration.

For the latest updates, check the
[GitHub Releases](https://github.com/AKEkam/EkamCore/releases) page.

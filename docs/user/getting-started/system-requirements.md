# System Requirements

EkamCore runs entirely on your Mac. Nothing leaves your machine unless you
explicitly enable Tailscale remote access. Before you install, make sure your
hardware and software meet the minimums below.

## Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Chip | Apple Silicon M1 | M2 Pro or later |
| RAM | 16 GB | 32 GB |
| Free disk | 30 GB | 60 GB |

EkamCore relies on Apple Silicon for on-device AI inference. Intel Macs are
**not supported**.

The 30 GB disk figure covers Docker images, the local database, search indexes,
and a small AI model. If you plan to index large photo or document libraries,
allow extra space proportional to the size of those libraries.

## Software

| Requirement | Details |
|-------------|---------|
| macOS | 13 Ventura or later (14 Sonoma or 15 Sequoia recommended) |
| Container runtime | Docker Desktop 4.x **or** OrbStack 1.x |
| AI engine | Ollama (required for natural-language search and daily recaps) |

### Container runtime

EkamCore uses Docker containers for its services (PostgreSQL, Meilisearch,
PaperlessNGX, and more). You need one of the following installed before first
launch:

- **Docker Desktop** -- download from <https://www.docker.com/products/docker-desktop/>
- **OrbStack** -- lighter-weight alternative, download from <https://orbstack.dev/>

The Manager app detects whichever runtime is present and uses it automatically.
If both are installed, OrbStack takes priority.

### Ollama

Ollama provides local large-language-model inference for AI-powered features
such as natural-language search answers and daily recap summaries.

1. Install from <https://ollama.com/download/mac>.
2. Launch Ollama at least once so it creates its data directory.
3. EkamCore's setup wizard will pull the required model for you.

If Ollama is not installed, EkamCore still works for indexing, search, calendar,
and reminders -- AI features simply remain unavailable until you add it later.

## Network

No internet connection is required after initial setup. The first launch needs
connectivity only to pull Docker images and the Ollama model. After that,
EkamCore operates fully offline.

## Permissions

During first-run setup you will be prompted to grant access to:

- **Calendar** -- read-only access to Apple Calendar events
- **Reminders** -- read-only access to Apple Reminders
- **Contacts** -- read-only access to Apple Contacts (used by the People Graph)
- **Files and Folders** -- access to the document and photo folders you choose

You can review or revoke these permissions at any time in
**System Settings > Privacy & Security**.

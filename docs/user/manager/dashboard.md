# Dashboard

The Dashboard is the main screen of the Manager app. It gives you a
real-time overview of every EkamCore service, key metrics, and quick
actions.

## Service health tiles

The top section displays a tile for each of the ten managed services. Each
tile shows the service name, a colored status dot, and uptime.

| Service | Description |
|---------|-------------|
| **API Server** | The core EkamCore backend. Handles all web and mobile requests. |
| **PostgreSQL** | Primary database for documents, metadata, and user data. |
| **Meilisearch** | Full-text search engine powering natural-language queries. |
| **Ollama** | Local LLM runtime for embeddings and query understanding. |
| **PaperlessNGX** | Document ingestion and OCR pipeline. |
| **Redis** | In-memory cache and job queue broker. |
| **Qdrant** | Vector database for semantic search embeddings. |
| **Face Clustering** | Background worker for photo face detection and grouping. |
| **PLA Engine** | Personal Life Assistant suggestion generator. |
| **Nginx** | Reverse proxy and TLS termination. |

Status colors:

- **Green** -- Healthy. The service is running and responding to health checks.
- **Yellow** -- Degraded. The service is running but responding slowly or
  returning warnings.
- **Red** -- Down. The service has failed health checks and may need manual
  attention.
- **Gray** -- Stopped. The service is not running.

Click any tile to view that service's recent logs.

## KPI cards

Below the health tiles, five KPI cards show key numbers at a glance.

| Card | What it shows |
|------|---------------|
| **Files** | Total number of indexed files across all source folders. |
| **Photos** | Total indexed photos, with a subtitle showing how many have face data. |
| **Persons** | Number of identified persons in the People graph. |
| **Last Backup** | Timestamp of the most recent successful backup. |
| **Disk Usage** | Total disk space used by EkamCore data and Docker volumes. |

Each card updates in real time via the watchdog. Tap a card to navigate to
the related detail view (for example, tapping **Disk Usage** opens
**Storage**).

## Alert banners

When something needs your attention, a banner appears between the health
tiles and KPI cards.

- **Red banner** -- A service is down and automatic restart failed.
- **Orange banner** -- Disk usage is above 90 percent.
- **Blue banner** -- An EkamCore update is available.

Banners include an action button (for example **Restart** or **Update Now**)
so you can respond without navigating away.

## Quick actions

Three buttons sit at the bottom of the dashboard.

| Button | Action |
|--------|--------|
| **Start All** | Starts every stopped service in dependency order. Disabled when all services are running. |
| **Stop All** | Gracefully stops all services. Running jobs are allowed to finish before containers shut down. |
| **Open Web UI** | Opens the EkamCore web interface in your default browser. |

## Real-time updates

The dashboard does not poll. The watchdog pushes health and metric events
over an internal WebSocket connection. Changes appear within one to two
seconds of occurring. If the watchdog itself stops (for example during an
update), the dashboard shows a gray overlay with the message "Watchdog
offline -- waiting for reconnect".

## Next step

To learn how updates work, see [Updates](updates.md). For troubleshooting
a down service, see [Hub Unreachable](../troubleshooting/hub-unreachable.md).

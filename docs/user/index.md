# EkamCore User Guide

Welcome to EkamCore — your private, local-first life assistant running entirely on your Apple Silicon Mac.

EkamCore connects your files, photos, contacts, calendars, and reminders through local AI. No cloud services, no telemetry, no external APIs. Your data never leaves your Mac.

## Quick Links

| I want to... | Go to... |
|-------------|----------|
| Install EkamCore for the first time | [Getting Started](getting-started/installation.md) |
| Add my documents and photos | [Data Sources](sources/document-folders.md) |
| See what's on my schedule today | [Today](today-recap/today.md) |
| Search across all my data | [Search](search/search.md) |
| Ask a question in natural language | [Natural Language Queries](search/natural-language.md) |
| Set up face recognition | [Enabling Face Clustering](people/enabling-face-clustering.md) |
| Access from my phone | [Mobile Access](mobile/tailscale-setup.md) |
| Manage the Docker services | [Manager App](manager/overview.md) |
| Fix a problem | [Troubleshooting](troubleshooting/hub-unreachable.md) |

## What EkamCore Does

EkamCore runs 10 services on your Mac to provide:

- **Today view** — calendar events, reminders, and AI-powered suggestions for your day
- **Recap** — daily and weekly summaries of what happened
- **Semantic search** — find anything across documents, photos, events, and contacts
- **Natural language queries** — ask questions and get grounded answers with source citations
- **People Graph** — face clustering links photos to people, enabling relationship-aware features
- **PLA Assistant** — follow-up suggestions, relationship reminders, weekly summaries
- **Mobile access** — iPhone/iPad app via Tailscale secure network

## Privacy First

- All processing happens locally on your Mac
- No data is sent to any external server
- Face embeddings are encrypted at rest
- You control exactly what data is indexed
- Delete everything at any time — it's your data

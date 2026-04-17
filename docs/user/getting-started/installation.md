# Installation

EkamCore ships as a single macOS app. The Manager handles all background
services so you never need to touch Docker or the terminal yourself.

## Download

1. Go to the [EkamCore GitHub Releases](https://github.com/AKEkam/EkamCore/releases)
   page.
2. Find the latest release and download the `.dmg` file (for example,
   `EkamCore-1.0.0-arm64.dmg`).
3. Only download from the official repository. EkamCore is not distributed
   through the Mac App Store or any third-party site.

## Install

1. Open the downloaded `.dmg` file.
2. Drag the **EkamCore** icon into the **Applications** folder.
3. Eject the disk image.

## First launch

1. Open **EkamCore** from your Applications folder or Spotlight.
2. macOS may show a dialog saying the app is from an identified developer.
   Click **Open** to continue.
3. The **Manager** window appears. This is the control centre for every
   EkamCore service.

The Manager runs as a menu-bar app by default. You can reopen the Manager
window at any time by clicking the EkamCore icon in the menu bar.

## What the Manager does

The Manager app is responsible for:

- **Starting and stopping Docker containers** -- PostgreSQL, Meilisearch,
  PaperlessNGX, and the EkamCore API server all run as containers.
- **Health monitoring** -- a status indicator shows green, yellow, or red for
  each service.
- **Automatic updates** -- the Manager checks for new releases on launch and
  can apply updates in place.
- **Log access** -- view live logs for any service directly from the Manager
  window.

You do not need to run `docker compose` or any CLI command. The Manager
wraps all container lifecycle operations behind a single Start / Stop button.

## Uninstalling

1. Open the Manager and click **Stop All Services** to shut down containers.
2. Drag **EkamCore** from Applications to the Trash.
3. Optionally remove stored data at `~/Library/Application Support/EkamCore/`
   and Docker volumes prefixed with `ekamcore_`.

## Next step

After installation, proceed to [First-Run Setup](first-run-setup.md) to
configure your instance.

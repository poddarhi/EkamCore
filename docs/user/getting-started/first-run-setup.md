# First-Run Setup

The first time you launch EkamCore, a setup wizard walks you through eight
steps. The whole process takes five to ten minutes depending on your internet
speed (Docker images need to be pulled once).

## Step 1 -- Hardware check

The wizard verifies that you are running on Apple Silicon and that your Mac
meets the minimum RAM requirement (16 GB). If the check fails, setup stops
with a clear message explaining what is missing.

## Step 2 -- Disk space

EkamCore needs at least 30 GB of free disk space for Docker images, the
database, search indexes, and AI models. The wizard shows your current
available space and warns you if it is below the threshold.

## Step 3 -- Docker detection

The wizard looks for Docker Desktop or OrbStack. If neither is found, you are
given a link to install one. Once a container runtime is detected, the wizard
confirms the version and moves on.

## Step 4 -- Pull images

EkamCore pulls the required Docker images (PostgreSQL, Meilisearch,
PaperlessNGX, the API server, and supporting services). A progress bar shows
download status for each image. This step requires an internet connection.

## Step 5 -- Database initialisation

The wizard starts the database container, runs migrations, and creates the
internal schema. No user action is needed -- a spinner indicates progress.

## Step 6 -- Admin account

Create your local admin account:

- **Email** -- used only as your login identifier; it is never sent anywhere.
- **Password** -- must be at least 12 characters. The wizard shows a strength
  meter. Use a mix of letters, numbers, and symbols for best results.
- **Confirm password** -- re-enter to verify.

This account is stored in the local database. There is no cloud authentication.

## Step 7 -- Data sources

Grant EkamCore access to the information you want it to organise:

| Source | Permission | Notes |
|--------|------------|-------|
| Calendar | macOS Calendar read access | Imports events for Today and Recap |
| Reminders | macOS Reminders read access | Imports tasks and due dates |
| Contacts | macOS Contacts read access | Powers the People Graph |
| Document folders | Folder picker | Choose one or more folders to index |
| Photo folders | Folder picker | Choose one or more folders for photo features |

Each permission triggers a standard macOS dialog. You can skip any source
and add it later in **Settings > Data Sources**.

## Step 8 -- Tailscale (optional)

If you want to access EkamCore from your phone or another device on your
Tailscale network, toggle **Enable Tailscale access** and sign in. This step
is entirely optional -- EkamCore works fully on localhost without it.

## After setup

The wizard closes and the **Today** screen loads with your first set of cards.
Background indexing of documents and photos begins immediately and may take
a while for large libraries. You can track progress in **Settings > Indexing**.

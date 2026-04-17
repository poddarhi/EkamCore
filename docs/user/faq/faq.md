# Frequently Asked Questions

## Privacy

**Does EkamCore send my data to the cloud?**
No. All processing, storage, and AI inference happen locally on your Mac.
No data ever leaves your machine unless you explicitly configure a remote
service.

**Is there any telemetry or analytics?**
No. EkamCore does not collect telemetry, usage analytics, or crash reports.
There are no network calls to Anthropic, Apple, or any third party.

**Can someone else access my data over the network?**
Only if they are on your Tailscale tailnet and have your login credentials.
EkamCore is not exposed to the public internet. See
[Tailscale Setup](../mobile/tailscale-setup.md) for details on the private
network.

**Where is my data stored?**
All data is stored in Docker volumes and in
`~/Library/Application Support/EkamCore/`. Backups go to the `backups/`
subdirectory.

## Security

**Is my data encrypted?**
Data at rest is stored in Docker volumes which reside on your Mac's
encrypted APFS volume (FileVault). The mobile app cache is encrypted using
iOS data protection. Secrets (API keys, database credentials) are stored
in the macOS Keychain.

**Does EkamCore support multiple users?**
Currently EkamCore is designed for a single user. Multi-user support with
per-user access control is planned for a future release.

**What happens if I lose my Mac?**
If FileVault is enabled, your data is encrypted and inaccessible without
your login password. You can also reset EkamCore remotely via iCloud's
Erase Mac feature, which wipes the entire disk.

## Performance

**How much RAM does EkamCore use?**
Approximately 5 to 6 GB when all services are running. A Mac with 16 GB of
unified memory provides the best experience. EkamCore runs on 8 GB machines
but with limited headroom for other apps.

**Why is my first query slow?**
Ollama loads the language model into memory on the first query after a cold
start. This takes 15 to 30 seconds. Subsequent queries should return in one
to three seconds. See [Slow Queries](../troubleshooting/slow-queries.md).

**How long does initial indexing take?**
It depends on the size of your dataset. Typical times: 10,000 files in about
15 minutes, 50,000 files in about one hour, 100,000+ files in several hours.
Indexing runs in the background and does not block the UI.

**Does EkamCore work on Intel Macs?**
No. EkamCore requires Apple Silicon (M1 or later) for local AI inference
with Ollama.

## Face Clustering

**How accurate is face clustering?**
The face detection model correctly identifies faces in over 95% of clear,
well-lit photos. Accuracy drops with poor lighting, extreme angles, or very
small faces in group shots.

**What if someone is misidentified?**
Open the person's profile in the People section, find the misidentified
photo, and click **Not This Person**. The photo is removed from the cluster
and offered to other clusters or left unassigned.

**Can I delete all face data?**
Yes. Go to **Settings > Photo Intelligence** and click **Delete All Face
Data**. This removes all clusters, assignments, and cached face embeddings.
Your photos are not affected.

**Is face data shared or uploaded anywhere?**
No. Face embeddings and cluster data are processed and stored entirely on
your Mac. Nothing is sent to any external service.

## Mobile

**Do I need Tailscale to use the mobile app?**
Yes. Tailscale creates the private network between your phone and Mac.
Without it the mobile app cannot reach your hub. See
[Tailscale Setup](../mobile/tailscale-setup.md).

**What can I do when offline?**
The mobile app caches recent data and displays it with a stale indicator.
You can view your Today briefing (up to 4 hours old), Recap (up to 24
hours), and recent search results (up to 30 minutes). See
[Offline Behavior](../mobile/offline-behavior.md).

**Is there an Android app?**
Not yet. Android support is planned for a future release.

**Does the mobile app support push notifications?**
Not in the current release. Push notifications are on the roadmap.

## Updates

**How often are updates released?**
EkamCore follows a regular release cycle, typically once or twice per
month. Critical security fixes are released as needed.

**Is my data safe during updates?**
Yes. The Manager creates a full backup before every update and
automatically rolls back if anything goes wrong. See
[Updates](../manager/updates.md).

**Can I skip an update?**
Yes. Updates are never forced. You can dismiss the update banner and
continue using your current version.

## PLA Pack

**How do PLA suggestions work?**
The Personal Life Assistant analyzes your local data -- calendar events,
recent documents, tasks, and contacts -- to generate actionable suggestions.
For example, it may remind you to follow up with someone you have not
contacted recently or surface a document relevant to an upcoming meeting.

**Can I disable specific PLA workflows?**
Yes. Go to **Settings > PLA Pack** and toggle off any workflow you do not
want: Morning Briefing, Evening Recap, Contact Follow-up, Photo Memories,
or Document Digest.

**Does PLA learn from my behavior?**
PLA uses your local data to generate suggestions but does not build a
persistent behavioral model. Dismissing a suggestion does not train the
system. Future releases may add opt-in feedback learning.

**Can I change when PLA suggestions are delivered?**
Yes. Adjust the schedule in **Settings > PLA Pack > Schedule**. The default
is 07:00 for Morning Briefing and 21:00 for Evening Recap.

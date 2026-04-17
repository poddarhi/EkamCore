# Privacy Controls for Face Clustering

EkamCore gives you full control over face clustering data. You can disable the
feature at any time, and when you do, biometric data is permanently erased.

## Disabling face clustering

1. Open **Settings > Photo Intelligence**.
2. Toggle **Enable Face Clustering** to off.
3. A confirmation dialog appears explaining exactly what will happen.
4. Tap **Disable and Delete Face Data** to confirm.

## What happens when you disable

The following actions take place immediately and cannot be reversed:

### Face embeddings are permanently deleted

All encrypted face embedding vectors stored in the local database are
hard-deleted. This is not a soft-delete or archival -- the data is erased
from disk and cannot be recovered.

### Bounding box data is removed

Face bounding boxes (the coordinates that mark where a face appears in a
photo) are deleted along with the embeddings.

### Confirmed persons remain

Person profiles that you created by confirming clusters are **not** deleted.
Their display name, linked contact, and association with events, reminders,
and files are preserved. Only the face-to-photo links are removed.

This means:

- The person still appears in the People tab.
- Their Events, Files, and Reminders tabs are unaffected.
- Their Photos tab becomes empty because face links no longer exist.
- Their avatar reverts to an initial-based placeholder if it was sourced from
  a face thumbnail.

### Photo overlays disappear

Face overlay rectangles in the photo viewer are no longer shown because the
bounding box data has been deleted.

## Re-enabling face clustering

You can turn face clustering back on at any time by following the steps in
[Enabling Face Clustering](enabling-face-clustering.md). Because all previous
embeddings were permanently deleted, EkamCore performs a fresh scan of every
indexed photo from scratch. Previous cluster assignments and review decisions
are not restored.

## Data location

All face clustering data is stored at:

```
~/Library/Application Support/EkamCore/db/
```

within the encrypted local database. No face data is stored in Docker volumes
or any location outside your user directory.

## Frequently asked questions

**Can I delete a single person's face data without disabling the whole feature?**
Yes. Open the person's profile, tap the three-dot menu, and select
**Delete Person**. This removes their embeddings and face links while leaving
face clustering active for everyone else.

**Is face data included in EkamCore backups?**
If you back up the `EkamCore` data directory, face embeddings are included
in the database file. If you want to exclude them, disable face clustering
before backing up.

**What if I revoke photo folder access instead?**
Removing a photo folder from **Settings > Data Sources** deletes index entries
for that folder's photos, including any associated face data. This is
folder-scoped, not feature-wide.

# Photo Folders

EkamCore indexes your local photo folders so you can search, browse, and
organise photos without uploading them anywhere.

## Adding a photo folder

1. Open **Settings > Data Sources > Photo Folders**.
2. Click **Add Folder**.
3. Select a folder in the macOS picker. Subfolders are included automatically.
4. Indexing begins in the background.

You can add multiple folders. To remove one, click the trash icon next to it.
Removing a folder deletes its index entries but never modifies your original
photo files.

## Supported formats

| Format | Extensions |
|--------|------------|
| JPEG | `.jpg`, `.jpeg` |
| PNG | `.png` |
| HEIC | `.heic`, `.heif` |
| TIFF | `.tif`, `.tiff` |
| WebP | `.webp` |

Files larger than 100 MB are skipped. Unsupported formats are silently ignored.

## What gets extracted

### EXIF metadata

EkamCore reads EXIF data embedded in each photo:

- **Date taken** -- used to group photos on a timeline.
- **GPS coordinates** -- converted to a human-readable location (reverse
  geocoding runs locally).
- **Camera model and lens** -- stored for search and filtering.
- **Orientation** -- used to display the photo correctly in the grid.

Photos without EXIF data still appear in the index; they use the file
modification date as a fallback.

### Face detection (optional)

If you enable face clustering in **Settings > Photo Intelligence**, EkamCore
scans photos for faces and groups them into clusters. This feature requires
your explicit consent because it processes biometric-adjacent data.

When face detection is enabled:

- Faces are detected using an on-device model (nothing is sent to the cloud).
- Each face is converted to an encrypted embedding stored in the local database.
- Detected faces are grouped into clusters for you to review and confirm.

See [Enabling Face Clustering](../people/enabling-face-clustering.md) for full
details on privacy controls and how to turn the feature on or off.

## Sync behaviour

EkamCore watches indexed folders for file-system events. New, modified, or
deleted photos are reflected in the index within seconds. A full re-scan runs
once every 24 hours as a safety net.

## Status indicators

Each photo folder shows a badge in Settings:

| Badge | Meaning |
|-------|---------|
| Green circle | Fully indexed |
| Yellow spinner | Indexing in progress |
| Red exclamation | Error (tap for details) |
| Grey dash | Queued, waiting to start |

You can also check overall photo indexing progress in
**Settings > Indexing > Photos**.

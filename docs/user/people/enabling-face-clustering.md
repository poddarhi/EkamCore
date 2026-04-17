# Enabling Face Clustering

Face clustering lets EkamCore detect faces in your photos and group them by
person. Because this involves biometric-adjacent data, the feature is off by
default and requires your explicit consent to enable.

## What is stored

When face clustering is active, the following data is created and stored
**locally on your Mac**:

- **Face embeddings** -- a numerical vector representing each detected face.
  Embeddings are encrypted at rest in the local database. They cannot be
  reversed into an image of the face.
- **Bounding boxes** -- the pixel coordinates of each face within a photo,
  used to draw overlays in the photo viewer.
- **Cluster assignments** -- which faces belong to the same group, so you can
  label them with a person name.

No face data, embeddings, or photos are ever sent to an external server.

## How to enable

1. Open **Settings > Photo Intelligence**.
2. Read the consent explanation that describes what data will be processed
   and stored.
3. Toggle **Enable Face Clustering** to on.
4. Confirm by tapping **I Understand, Enable**.

## What happens when you enable it

Once enabled, EkamCore begins a background scan of all indexed photo folders:

1. **Detection** -- each photo is analysed by an on-device face detection
   model running on the Apple Neural Engine. Photos without faces are skipped.
2. **Embedding** -- each detected face is converted into an encrypted
   embedding vector.
3. **Clustering** -- embeddings are compared to group similar faces into
   unnamed clusters.
4. **Review queue** -- clusters appear in the
   [Review Queue](review-queue.md) for you to confirm, reject, or label.

The initial scan speed depends on your photo library size and your Mac's chip.
Expect roughly 5-10 photos per second on an M1 and faster on newer chips.
You can continue using EkamCore normally while the scan runs.

Progress is visible in **Settings > Indexing > Face Clustering**.

## Re-scanning

If you add new photo folders after enabling face clustering, the new photos
are scanned automatically. You can also trigger a manual re-scan from
**Settings > Photo Intelligence > Re-scan All Photos**.

## Disabling

You can disable face clustering at any time. See
[Privacy Controls](privacy-controls.md) for what happens to your data when
you turn the feature off.

## Frequently asked questions

**Does face clustering use the internet?**
No. The detection model runs entirely on your Mac using Core ML and the
Apple Neural Engine.

**Can someone reconstruct a face from an embedding?**
No. Embeddings are one-way numerical representations. They cannot be decoded
back into an image.

**Does enabling face clustering slow down my Mac?**
The initial scan uses background-priority threads and should not noticeably
affect foreground tasks. If you experience slowdowns, you can pause the scan
from Settings.

# Review Queue

After face clustering detects and groups faces, the Review Queue lets you
confirm, reject, or skip each cluster. This is how EkamCore learns who is
who in your photos.

## Accessing the queue

Open **People > Review Queue** from the bottom navigation bar. A badge on the
People tab shows the number of clusters waiting for review.

## What you see

Each review card shows:

- **A grid of sample faces** from the cluster (up to 9 thumbnails).
- **A suggested name** if the cluster matches an existing confirmed person
  (otherwise "Unknown person").
- **A confidence badge** indicating how tightly the faces in the cluster
  resemble each other:

| Badge | Meaning |
|-------|---------|
| High (green) | Faces are very similar; likely the same person |
| Medium (yellow) | Faces are somewhat similar; worth reviewing closely |
| Low (grey) | Faces may include more than one person; consider splitting |

## Actions

### Confirm

Accept the cluster as a single person. If a name was suggested, it is applied.
If the cluster is unnamed, you are prompted to type a name. Confirmed clusters
become person profiles visible in the People tab.

### Reject

Discard the cluster. The faces are returned to the unassigned pool and may
appear in future clusters after the next re-scan. Use this when a cluster
contains mixed faces from different people.

### Skip

Leave the cluster in the queue for later. It stays at its current position and
is shown again next time you visit the Review Queue.

## Keyboard shortcuts (web)

| Key | Action |
|-----|--------|
| C | Confirm the current cluster |
| R | Reject the current cluster |
| S | Skip to the next cluster |
| Left arrow | Go back to the previous cluster |
| Right arrow | Go forward to the next cluster |

## Swipe gestures (mobile)

- **Swipe right** to confirm.
- **Swipe left** to reject.
- **Swipe down** to skip.

## Progress indicator

A progress bar at the top of the Review Queue shows how many clusters you have
reviewed out of the total. For example, "12 of 47 reviewed". The bar fills as
you work through the queue.

## Tips

- Start with high-confidence clusters. They are almost always correct and let
  you build up confirmed persons quickly.
- Once you confirm a person, future clusters containing that person's face are
  more likely to receive a correct suggested name.
- You can revisit confirmed persons in **People > Profiles** and merge or
  rename them at any time.

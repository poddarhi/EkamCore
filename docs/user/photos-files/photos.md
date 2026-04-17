# Photos

The Photos screen lets you browse, search, and view all photos indexed from
your chosen folders. Everything runs locally on your Mac.

## Photo grid

Photos are displayed in a responsive grid grouped by date. Each date section
shows a header with the date (for example, "Tuesday, 14 January 2026") and
the number of photos in that group.

The grid loads incrementally as you scroll. Thumbnails are generated locally
and cached for fast browsing.

## Lightbox

Tap any photo to open the lightbox view:

- The photo fills the screen at full resolution.
- Swipe left or right (or use arrow keys on the web) to navigate between
  photos in the same date group.
- Tap the X button or swipe down to close the lightbox.

## EXIF metadata panel

In the lightbox, tap the **info** icon (or press I on the web) to open the
metadata panel. It displays:

| Field | Example |
|-------|---------|
| Date taken | 14 Jan 2026, 09:32 AM |
| Camera | iPhone 15 Pro |
| Lens | 24mm f/1.78 |
| ISO / Shutter / Aperture | ISO 50, 1/120s, f/1.78 |
| Location | Ahmedabad, Gujarat, India |
| File size | 4.2 MB |
| Dimensions | 4032 x 3024 |

If a photo has no EXIF data, the panel shows the file modification date and
available file-level information only.

## Face overlay

When face clustering is enabled and faces have been detected in a photo, small
rectangles appear over each face in the lightbox. Tap a rectangle to see the
person's name (if confirmed) or "Unknown" (if not yet reviewed). Tapping the
name opens the person's profile.

Face overlays are only visible when the feature is enabled. See
[Enabling Face Clustering](../people/enabling-face-clustering.md) for details.

## Filtering

A filter bar at the top of the Photos screen provides:

- **Date range** -- tap to open a date picker and restrict the grid to a
  specific period.
- **Location** -- type a place name to filter photos by GPS location. This
  uses reverse-geocoded location strings from EXIF data.
- **Person** -- if face clustering is enabled, select a confirmed person to
  show only photos containing their face.

Active filters appear as removable chips below the filter bar. Tap the X on
a chip to clear that filter.

## Supported formats

JPEG, PNG, HEIC, TIFF, and WebP. Files up to 100 MB are supported. See
[Supported Formats](supported-formats.md) for the full list.

## Tips

- Use the date filter to quickly jump to a specific month or year.
- Combine the person filter with a location to find photos of someone at a
  particular place.
- If a photo appears rotated, check whether the original file has correct
  EXIF orientation data.

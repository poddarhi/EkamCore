# S08-001: Photo Metadata Extraction — Design Spec

**Date:** 2026-04-09  
**Story:** S08-001 [CP] — Photo metadata + thumbnails  
**Phase:** 2 (Sprint 8)  
**Workstream:** backend / ml-ai  
**Status:** Approved

---

## Context

Photos in EkamCore are ingested via `photo_folder` sources (separate from Paperless documents). The ingestion pipeline already handles file discovery and fingerprinting. S08-001 adds the METADATA_EXTRACTED stage for photos: EXIF parsing, GPS reverse geocoding, perceptual hashing, and thumbnail generation. This populates the `photo_assets` table, enabling the photo gallery API and future face clustering (S11-002).

---

## Architecture

### Data Flow

```
FSEvents / manager app
        │
        ▼
POST /internal/ingest/photo  ──►  background task
        │
        ▼
ingest_photo(source_id, file_path, db)
  │
  ├─ 1. Register file → File + IngestionState(DISCOVERED)
  ├─ 2. FINGERPRINTED:   SHA-256 via dedup.compute_hash()
  ├─ 3. METADATA_EXTRACTED:
  │      photo_extractor.extract_metadata()
  │      photo_extractor.generate_thumbnail()
  │      photo_extractor.compute_perceptual_hash()
  │      → upsert photo_assets row
  │      → save thumbnail to THUMBNAIL_DIR
  ├─ 4–7. TEXT/OCR/EMBEDDING stages: instant no-op advance
  └─ 8. COMPLETED
```

### Key Design Decisions

- **No state machine shortcut**: All 8 pipeline stages are advanced sequentially. No-op stages (TEXT_EXTRACTED → EMBEDDED) are advanced immediately with no work. This preserves the state machine contract and makes CLIP embedding insertion in S10+ trivial.
- **Sync extractor, async pipeline**: `photo_extractor` functions are synchronous (CPU-bound Pillow). Called via `asyncio.to_thread()` inside the async pipeline.
- **HEIC support**: `pillow-heif` registered at module import. Covers all iPhone photos.
- **Thumbnail orientation fix**: `ImageOps.exif_transpose()` applied before saving so thumbnails are always upright.

---

## Schema

### New table: `photo_assets` (migration 008)

```sql
CREATE TABLE photo_assets (
    id UUID PRIMARY KEY DEFAULT gen_uuid_v7(),
    file_id UUID NOT NULL UNIQUE REFERENCES files(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    taken_at TIMESTAMPTZ,
    gps_lat FLOAT,
    gps_lon FLOAT,
    location_name TEXT,
    camera_make TEXT,
    camera_model TEXT,
    width INTEGER,
    height INTEGER,
    orientation INTEGER,             -- EXIF tag 274, values 1–8
    thumbnail_path TEXT,             -- relative to THUMBNAIL_DIR setting
    perceptual_hash CHAR(16),        -- imagehash.phash, 64-bit = 16 hex chars
    exif_json JSONB,                 -- full EXIF dump keyed by tag name
    face_count INTEGER DEFAULT 0,    -- populated by S11-002
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
```

> `orientation` and `exif_json` are additions beyond the db-schema-reference baseline. `orientation` is required for correct thumbnail rendering; `exif_json` future-proofs against additional metadata fields.

---

## New Files

| File | Purpose |
|---|---|
| `apps/api/alembic/versions/008_photo_assets.py` | Migration |
| `apps/api/api/db/models/photo_asset.py` | ORM model |
| `apps/api/api/services/ingestion/photo_extractor.py` | EXIF / thumbnail / pHash extraction |
| `apps/api/api/services/ingestion/photo_pipeline.py` | Full pipeline: DISCOVERED → COMPLETED |
| `apps/api/api/routers/photos.py` | GET /photos/{id} and /photos/{id}/thumbnail |
| `apps/api/tests/test_photo_extractor.py` | Unit tests for extractor functions |
| `apps/api/tests/test_photo_pipeline.py` | Pipeline integration (mocked DB) |

## Modified Files

| File | Change |
|---|---|
| `apps/api/api/db/models/__init__.py` | Add PhotoAsset |
| `apps/api/api/main.py` | Register photos router |
| `apps/api/api/routers/internal.py` | Add POST /internal/ingest/photo |
| `apps/api/api/config.py` | Add THUMBNAIL_DIR setting |
| `apps/api/pyproject.toml` | Add pillow, piexif, imagehash, reverse_geocoder, pillow-heif |

---

## Service Design: photo_extractor.py

```python
@dataclass
class PhotoMetadata:
    taken_at: datetime | None
    gps_lat: float | None
    gps_lon: float | None
    location_name: str | None
    camera_make: str | None
    camera_model: str | None
    width: int
    height: int
    orientation: int
    exif_json: dict

def extract_metadata(file_path: Path) -> PhotoMetadata: ...
def generate_thumbnail(file_path: Path, size: int = 300) -> bytes: ...   # JPEG, quality=85
def compute_perceptual_hash(file_path: Path) -> str: ...                 # 16-char hex
```

**GPS conversion:** EXIF GPS stores degrees/minutes/seconds as rational tuples `((d,1),(m,1),(s,100))`. Conversion: `d + m/60 + s/3600`. South/West → negate.

**Reverse geocode:** `reverse_geocoder.search([(lat, lon)])[0]` → `"{name}, {admin1}, {cc}"`. Offline, ~1ms, no network required.

**Supported formats:** JPEG, PNG, HEIC (via pillow-heif), TIFF, WebP. Unsupported formats → `UnsupportedMediaError`.

---

## API Endpoints

### Internal
```
POST /api/v1/internal/ingest/photo
Body:  { source_id: UUID, file_path: str }
→ 202: { status: "ingestion_started", file_id: UUID }
```

### External (require auth + photos_enabled flag)
```
GET /api/v1/photos/{id}
→ 200: ResponseEnvelope with photo card payload

GET /api/v1/photos/{id}/thumbnail
→ 200: JPEG bytes
   Headers: Content-Type: image/jpeg, Cache-Control: max-age=86400
```

---

## New Dependencies (pyproject.toml)

```toml
pillow = "^11.0.0"
piexif = "^1.1.3"
imagehash = "^4.3.0"
reverse_geocoder = "^1.5.1"
pillow-heif = "^0.21.0"
```

---

## Tests

### test_photo_extractor.py
- `test_extract_metadata_jpeg`: fixture JPEG with embedded GPS EXIF → assert lat, lon, location_name not None, camera_make present, width > 0, exif_json has keys
- `test_dms_to_decimal`: known DMS values → expected decimal (e.g. 40°26'46"N → 40.446...)
- `test_generate_thumbnail_size`: result thumbnail fits within 300×300 box, is valid JPEG
- `test_generate_thumbnail_orientation`: image with orientation=6 → thumbnail is portrait not landscape
- `test_perceptual_hash_length`: result is exactly 16 chars
- `test_perceptual_hash_deterministic`: same file → same hash, different file → different hash

### test_photo_pipeline.py
- `test_full_pipeline_stages`: mock DB, run pipeline → final stage is COMPLETED, photo_assets row created
- `test_duplicate_detection`: same file ingested twice → second is_duplicate=True, no second photo_assets row
- `test_unsupported_format`: .txt file → SKIPPED state, no photo_assets row
- `test_workspace_isolation`: photo_assets row has correct workspace_id

---

## Verification

```bash
cd apps/api && poetry run pytest tests/test_photo_extractor.py tests/test_photo_pipeline.py -v
make test-api
```

Check thumbnail file written to `./data/thumbnails/{workspace_id}/{photo_id}.jpg` on disk.

# S08 Photo Metadata + Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement photo ingestion with EXIF/GPS/thumbnail extraction (S08-001) and photo metadata search (S08-002).

**Architecture:** S08-001 adds migration + ORM model + `photo_extractor.py` (pure CPU sync functions) + `photo_pipeline.py` (async orchestrator DISCOVERED→COMPLETED) + internal ingest endpoint + GET photos router. S08-002 adds `photo_search.py` service, extends `search_all()` with `type='photo'`, adds three deterministic query patterns, and wires router handlers.

**Tech Stack:** Pillow, pillow-heif, piexif, imagehash, reverse_geocoder, SQLAlchemy async, FastAPI, pytest-asyncio

---

## File Map

### S08-001 — Create
| File | Purpose |
|---|---|
| `apps/api/alembic/versions/008_photo_assets.py` | photo_assets migration |
| `apps/api/api/db/models/photo_asset.py` | PhotoAsset ORM model |
| `apps/api/api/services/ingestion/photo_extractor.py` | extract_metadata / generate_thumbnail / compute_perceptual_hash |
| `apps/api/api/services/ingestion/photo_pipeline.py` | ingest_photo() orchestrator DISCOVERED→COMPLETED |
| `apps/api/api/routers/photos.py` | GET /photos/{id} and GET /photos/{id}/thumbnail |
| `apps/api/tests/test_photo_extractor.py` | extractor unit tests |
| `apps/api/tests/test_photo_pipeline.py` | pipeline mock tests |

### S08-001 — Modify
| File | Change |
|---|---|
| `apps/api/pyproject.toml` | Add pillow, piexif, imagehash, reverse_geocoder, pillow-heif |
| `apps/api/api/config.py` | Add THUMBNAIL_DIR setting |
| `apps/api/api/db/models/__init__.py` | Add PhotoAsset import/export |
| `apps/api/api/main.py` | Import and register photos router |
| `apps/api/api/routers/internal.py` | Add POST /internal/ingest/photo endpoint |

### S08-002 — Create
| File | Purpose |
|---|---|
| `apps/api/api/services/search/photo_search.py` | search_photos() + count_photos() + PhotoFilters |
| `apps/api/tests/test_photo_search.py` | photo search unit + pattern tests |

### S08-002 — Modify
| File | Change |
|---|---|
| `apps/api/api/services/query/search.py` | Add "photo" to SearchType, add has_gps param, dispatch |
| `apps/api/api/routers/search.py` | Add "photo" to type Literal, add has_gps query param |
| `apps/api/api/services/query/patterns.py` | Add photo_date/photo_location/photo_camera intents + patterns |
| `apps/api/api/services/query/router.py` | Add three photo handlers + dispatch entries |

---

## Task 1: Dependencies and Config

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/api/config.py`

- [ ] **Step 1: Add dependencies to pyproject.toml**

In `apps/api/pyproject.toml`, add to `[tool.poetry.dependencies]` after `tiktoken`:

```toml
pillow = "^11.0.0"
pillow-heif = "^0.21.0"
piexif = "^1.1.3"
imagehash = "^4.3.2"
reverse_geocoder = "^1.5.1"
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry add pillow pillow-heif piexif imagehash reverse_geocoder
```

Expected: packages resolve and are added to `poetry.lock`.

- [ ] **Step 3: Add THUMBNAIL_DIR to config.py**

In `apps/api/api/config.py`, add to `Settings` after `LOG_LEVEL`:

```python
    # Photo thumbnails
    THUMBNAIL_DIR: str = "./data/thumbnails"
```

- [ ] **Step 4: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/pyproject.toml apps/api/poetry.lock apps/api/api/config.py
git commit -m "chore(api): add photo processing dependencies and THUMBNAIL_DIR config (S08-001)"
```

---

## Task 2: Migration and ORM Model

**Files:**
- Create: `apps/api/alembic/versions/008_photo_assets.py`
- Create: `apps/api/api/db/models/photo_asset.py`
- Modify: `apps/api/api/db/models/__init__.py`

- [ ] **Step 1: Write the migration**

Create `apps/api/alembic/versions/008_photo_assets.py`:

```python
"""photo_assets table — S08-001 photo metadata store

Revision ID: 008
Revises: 007
Create Date: 2026-04-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "photo_assets",
        sa.Column("id", sa.UUID(as_uuid=True), server_default=sa.text("gen_uuid_v7()"), nullable=False),
        sa.Column("file_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gps_lat", sa.Float, nullable=True),
        sa.Column("gps_lon", sa.Float, nullable=True),
        sa.Column("location_name", sa.Text, nullable=True),
        sa.Column("camera_make", sa.Text, nullable=True),
        sa.Column("camera_model", sa.Text, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("orientation", sa.Integer, nullable=True),
        sa.Column("thumbnail_path", sa.Text, nullable=True),
        sa.Column("perceptual_hash", sa.String(16), nullable=True),
        sa.Column("exif_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("face_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", name="uq_photo_assets_file_id"),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_photo_assets_file_id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], name="fk_photo_assets_workspace_id"),
    )
    op.create_index("ix_photo_assets_workspace_id", "photo_assets", ["workspace_id"])
    op.create_index("ix_photo_assets_taken_at", "photo_assets", ["workspace_id", "taken_at"])
    op.create_index("ix_photo_assets_location_name", "photo_assets", ["workspace_id", "location_name"])
    op.execute("""
        CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON photo_assets
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_updated_at ON photo_assets;")
    op.drop_index("ix_photo_assets_location_name", table_name="photo_assets")
    op.drop_index("ix_photo_assets_taken_at", table_name="photo_assets")
    op.drop_index("ix_photo_assets_workspace_id", table_name="photo_assets")
    op.drop_table("photo_assets")
```

- [ ] **Step 2: Write the ORM model**

Create `apps/api/api/db/models/photo_asset.py`:

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db.models.base import Base


class PhotoAsset(Base):
    """Photo metadata extracted from image files.

    One-to-one with files table via file_id UNIQUE constraint.
    Created during METADATA_EXTRACTED pipeline stage.
    """

    __tablename__ = "photo_assets"
    __table_args__ = (UniqueConstraint("file_id", name="uq_photo_assets_file_id"),)

    file_id: Mapped[UUID] = mapped_column(ForeignKey("files.id"), nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    taken_at: Mapped[datetime | None] = mapped_column(nullable=True)
    gps_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_make: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orientation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    exif_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    face_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
```

- [ ] **Step 3: Register model in __init__.py**

In `apps/api/api/db/models/__init__.py`, add after `CorrespondentContactCandidate`:

```python
from api.db.models.photo_asset import PhotoAsset
```

And add `"PhotoAsset"` to `__all__`.

- [ ] **Step 4: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/alembic/versions/008_photo_assets.py apps/api/api/db/models/photo_asset.py apps/api/api/db/models/__init__.py
git commit -m "feat(alembic): add photo_assets migration and ORM model (S08-001)"
```

---

## Task 3: Photo Extractor (TDD)

**Files:**
- Create: `apps/api/tests/test_photo_extractor.py`
- Create: `apps/api/api/services/ingestion/photo_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `apps/api/tests/test_photo_extractor.py`:

```python
"""Unit tests for photo_extractor.py (S08-001).

Uses a programmatically-generated JPEG with known EXIF data — no static
fixture files needed.
"""

from __future__ import annotations

import io
import struct
from datetime import datetime, timezone
from pathlib import Path

import piexif
import pytest
from PIL import Image

from api.services.ingestion.photo_extractor import (
    PhotoMetadata,
    _dms_to_decimal,
    compute_perceptual_hash,
    extract_metadata,
    generate_thumbnail,
)


# ── EXIF fixture helpers ──────────────────────────────────────────────────────

def _rational(numerator: int, denominator: int) -> tuple[int, int]:
    return (numerator, denominator)


def _make_gps_ifd(lat_deg: float, lon_deg: float) -> dict:
    """Build a piexif GPS IFD for the given decimal lat/lon."""
    lat_ref = b"N" if lat_deg >= 0 else b"S"
    lon_ref = b"E" if lon_deg >= 0 else b"W"
    lat_abs = abs(lat_deg)
    lon_abs = abs(lon_deg)

    def _to_dms(dd: float):
        d = int(dd)
        m = int((dd - d) * 60)
        s = int(((dd - d) * 60 - m) * 60 * 100)
        return [_rational(d, 1), _rational(m, 1), _rational(s, 100)]

    return {
        piexif.GPSIFD.GPSLatitudeRef: lat_ref,
        piexif.GPSIFD.GPSLatitude: _to_dms(lat_abs),
        piexif.GPSIFD.GPSLongitudeRef: lon_ref,
        piexif.GPSIFD.GPSLongitude: _to_dms(lon_abs),
    }


def _make_test_jpeg(
    width: int = 200,
    height: int = 150,
    camera_make: str = "Canon",
    camera_model: str = "EOS R5",
    datetime_original: str = "2024:06:15 14:30:00",
    gps_lat: float | None = 48.8566,    # Paris
    gps_lon: float | None = 2.3522,
    orientation: int = 1,
) -> bytes:
    """Return JPEG bytes with embedded EXIF including optional GPS."""
    img = Image.new("RGB", (width, height), color=(100, 150, 200))

    zeroth = {
        piexif.ImageIFD.Make: camera_make.encode(),
        piexif.ImageIFD.Model: camera_model.encode(),
        piexif.ImageIFD.Orientation: orientation,
    }
    exif = {
        piexif.ExifIFD.DateTimeOriginal: datetime_original.encode(),
    }
    gps = _make_gps_ifd(gps_lat, gps_lon) if gps_lat is not None else {}

    exif_bytes = piexif.dump({"0th": zeroth, "Exif": exif, "GPS": gps})
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes)
    return buf.getvalue()


# ── _dms_to_decimal ───────────────────────────────────────────────────────────

def test_dms_to_decimal_north():
    # 48°51'23.76"N = 48.856600
    result = _dms_to_decimal(((48, 1), (51, 1), (2376, 100)), "N")
    assert abs(result - 48.8566) < 0.001


def test_dms_to_decimal_south():
    result = _dms_to_decimal(((33, 1), (52, 1), (0, 100)), "S")
    assert result < 0


def test_dms_to_decimal_west():
    result = _dms_to_decimal(((2, 1), (21, 1), (804, 100)), "W")
    assert result < 0


# ── extract_metadata ──────────────────────────────────────────────────────────

def test_extract_metadata_returns_dimensions(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(width=200, height=150)
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert meta.width == 200
    assert meta.height == 150


def test_extract_metadata_camera(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(camera_make="Nikon", camera_model="Z9")
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert meta.camera_make == "Nikon"
    assert meta.camera_model == "Z9"


def test_extract_metadata_taken_at(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(datetime_original="2024:06:15 14:30:00")
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert meta.taken_at is not None
    assert meta.taken_at.year == 2024
    assert meta.taken_at.month == 6
    assert meta.taken_at.day == 15


def test_extract_metadata_gps(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(gps_lat=48.8566, gps_lon=2.3522)
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert meta.gps_lat is not None
    assert abs(meta.gps_lat - 48.8566) < 0.01
    assert meta.gps_lon is not None
    assert abs(meta.gps_lon - 2.3522) < 0.01


def test_extract_metadata_location_name_set_when_gps_present(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(gps_lat=48.8566, gps_lon=2.3522)
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert meta.location_name is not None
    assert len(meta.location_name) > 0


def test_extract_metadata_no_gps(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(gps_lat=None, gps_lon=None)
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert meta.gps_lat is None
    assert meta.gps_lon is None
    assert meta.location_name is None


def test_extract_metadata_exif_json_populated(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg()
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    meta = extract_metadata(p)
    assert isinstance(meta.exif_json, dict)
    assert len(meta.exif_json) > 0


# ── generate_thumbnail ────────────────────────────────────────────────────────

def test_generate_thumbnail_is_valid_jpeg(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(width=1000, height=800)
    p = tmp_path / "big.jpg"
    p.write_bytes(jpeg_bytes)

    thumb = generate_thumbnail(p, size=300)
    assert isinstance(thumb, bytes)
    assert len(thumb) > 0
    # JPEG magic bytes
    assert thumb[:2] == b"\xff\xd8"


def test_generate_thumbnail_fits_in_box(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg(width=1000, height=800)
    p = tmp_path / "big.jpg"
    p.write_bytes(jpeg_bytes)

    thumb = generate_thumbnail(p, size=300)
    img = Image.open(io.BytesIO(thumb))
    assert img.width <= 300
    assert img.height <= 300


def test_generate_thumbnail_preserves_aspect_ratio(tmp_path: Path):
    # 400x200 → thumbnail width/height ratio should remain ~2:1
    jpeg_bytes = _make_test_jpeg(width=400, height=200)
    p = tmp_path / "wide.jpg"
    p.write_bytes(jpeg_bytes)

    thumb = generate_thumbnail(p, size=300)
    img = Image.open(io.BytesIO(thumb))
    ratio = img.width / img.height
    assert abs(ratio - 2.0) < 0.1


# ── compute_perceptual_hash ───────────────────────────────────────────────────

def test_perceptual_hash_is_16_chars(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg()
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    h = compute_perceptual_hash(p)
    assert len(h) == 16


def test_perceptual_hash_deterministic(tmp_path: Path):
    jpeg_bytes = _make_test_jpeg()
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    h1 = compute_perceptual_hash(p)
    h2 = compute_perceptual_hash(p)
    assert h1 == h2


def test_perceptual_hash_different_images(tmp_path: Path):
    p1 = tmp_path / "img1.jpg"
    p2 = tmp_path / "img2.jpg"
    p1.write_bytes(_make_test_jpeg(width=200, height=150))
    p2.write_bytes(_make_test_jpeg(width=200, height=150, camera_make="Sony"))

    # Different pixel content → different hash (with high probability)
    # Both images have same solid color so this may match; use different colors
    img_a = Image.new("RGB", (200, 150), (100, 150, 200))
    img_b = Image.new("RGB", (200, 150), (200, 50, 50))
    buf_a, buf_b = io.BytesIO(), io.BytesIO()
    img_a.save(buf_a, "JPEG")
    img_b.save(buf_b, "JPEG")
    p1.write_bytes(buf_a.getvalue())
    p2.write_bytes(buf_b.getvalue())

    h1 = compute_perceptual_hash(p1)
    h2 = compute_perceptual_hash(p2)
    assert h1 != h2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_extractor.py -v 2>&1 | head -20
```

Expected: ImportError — `photo_extractor` module does not exist yet.

- [ ] **Step 3: Implement photo_extractor.py**

Create `apps/api/api/services/ingestion/photo_extractor.py`:

```python
"""Photo metadata extraction: EXIF, GPS, thumbnails, perceptual hash (S08-001).

All three public functions are synchronous (CPU-bound Pillow operations).
Call them via asyncio.to_thread() inside async pipeline code.

Supported formats: JPEG, PNG, TIFF, WebP, HEIC (via pillow-heif).
Unsupported MIME types raise UnsupportedMediaError.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import imagehash
import piexif
import structlog
from PIL import Image, ImageOps

logger = structlog.get_logger()

# Register HEIC/HEIF support at module import.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    logger.warning("pillow_heif_not_available")

_SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".heic", ".heif"})

# EXIF tag IDs
_TAG_ORIENTATION = 274      # piexif.ImageIFD.Orientation
_TAG_MAKE = 271             # piexif.ImageIFD.Make
_TAG_MODEL = 272            # piexif.ImageIFD.Model
_TAG_DATETIME_ORIG = 36867  # piexif.ExifIFD.DateTimeOriginal
_GPS_IFD_TAG = 34853        # GPS IFD pointer in 0th IFD


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
    exif_json: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# GPS conversion
# ---------------------------------------------------------------------------

def _dms_to_decimal(dms: tuple, ref: str) -> float:
    """Convert EXIF DMS rational tuple to decimal degrees.

    dms format: ((deg_n, deg_d), (min_n, min_d), (sec_n, sec_d))
    ref: 'N', 'S', 'E', or 'W'
    """
    d = dms[0][0] / dms[0][1]
    m = dms[1][0] / dms[1][1]
    s = dms[2][0] / dms[2][1]
    decimal = d + m / 60 + s / 3600
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


# ---------------------------------------------------------------------------
# extract_metadata
# ---------------------------------------------------------------------------

def extract_metadata(file_path: Path) -> PhotoMetadata:
    """Extract EXIF metadata from a photo file.

    Returns PhotoMetadata. All fields are None/default-safe — no field raises.
    """
    with Image.open(file_path) as img:
        width, height = img.size

        raw_exif = img.info.get("exif", b"")
        if not raw_exif:
            return PhotoMetadata(
                taken_at=None, gps_lat=None, gps_lon=None, location_name=None,
                camera_make=None, camera_model=None,
                width=width, height=height, orientation=1, exif_json={},
            )

        try:
            exif_dict = piexif.load(raw_exif)
        except Exception:
            return PhotoMetadata(
                taken_at=None, gps_lat=None, gps_lon=None, location_name=None,
                camera_make=None, camera_model=None,
                width=width, height=height, orientation=1, exif_json={},
            )

    zeroth = exif_dict.get("0th", {})
    exif_ifd = exif_dict.get("Exif", {})
    gps_ifd = exif_dict.get("GPS", {})

    # Camera
    make_raw = zeroth.get(piexif.ImageIFD.Make, b"")
    model_raw = zeroth.get(piexif.ImageIFD.Model, b"")
    camera_make = make_raw.decode("utf-8", errors="replace").strip("\x00").strip() or None
    camera_model = model_raw.decode("utf-8", errors="replace").strip("\x00").strip() or None

    # Orientation
    orientation = zeroth.get(piexif.ImageIFD.Orientation, 1)

    # DateTimeOriginal
    taken_at: datetime | None = None
    dt_raw = exif_ifd.get(piexif.ExifIFD.DateTimeOriginal, b"")
    if dt_raw:
        try:
            taken_at = datetime.strptime(dt_raw.decode("ascii"), "%Y:%m:%d %H:%M:%S")
        except (ValueError, UnicodeDecodeError):
            pass

    # GPS
    gps_lat: float | None = None
    gps_lon: float | None = None
    location_name: str | None = None

    lat_raw = gps_ifd.get(piexif.GPSIFD.GPSLatitude)
    lat_ref = gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef, b"N")
    lon_raw = gps_ifd.get(piexif.GPSIFD.GPSLongitude)
    lon_ref = gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef, b"E")

    if lat_raw and lon_raw:
        try:
            ref_lat = lat_ref.decode("ascii") if isinstance(lat_ref, bytes) else lat_ref
            ref_lon = lon_ref.decode("ascii") if isinstance(lon_ref, bytes) else lon_ref
            gps_lat = _dms_to_decimal(lat_raw, ref_lat)
            gps_lon = _dms_to_decimal(lon_raw, ref_lon)
        except Exception:
            gps_lat = gps_lon = None

    if gps_lat is not None and gps_lon is not None:
        location_name = _reverse_geocode(gps_lat, gps_lon)

    # Serialise EXIF to JSON-safe dict (tag name → value)
    exif_json: dict = {}
    for ifd_name, ifd_data in exif_dict.items():
        if ifd_name in ("thumbnail",):
            continue
        if isinstance(ifd_data, dict):
            for tag_id, value in ifd_data.items():
                key = f"{ifd_name}_{tag_id}"
                if isinstance(value, bytes):
                    try:
                        exif_json[key] = value.decode("utf-8", errors="replace").strip("\x00")
                    except Exception:
                        pass
                elif isinstance(value, (int, float, str)):
                    exif_json[key] = value
                elif isinstance(value, (list, tuple)):
                    # rational tuples → float strings
                    try:
                        exif_json[key] = str(value)
                    except Exception:
                        pass

    return PhotoMetadata(
        taken_at=taken_at,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        location_name=location_name,
        camera_make=camera_make,
        camera_model=camera_model,
        width=width,
        height=height,
        orientation=orientation,
        exif_json=exif_json,
    )


def _reverse_geocode(lat: float, lon: float) -> str | None:
    """Offline reverse geocode lat/lon to a human-readable location string."""
    try:
        import reverse_geocoder as rg
        results = rg.search([(lat, lon)], verbose=False)
        if results:
            r = results[0]
            parts = [p for p in [r.get("name"), r.get("admin1"), r.get("cc")] if p]
            return ", ".join(parts) if parts else None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# generate_thumbnail
# ---------------------------------------------------------------------------

def generate_thumbnail(file_path: Path, size: int = 300) -> bytes:
    """Generate a JPEG thumbnail fitting within size×size, correct orientation.

    Returns JPEG bytes at quality=85.
    """
    with Image.open(file_path) as img:
        img_copy = img.copy()

    # Apply EXIF orientation so thumbnail is always upright
    img_copy = ImageOps.exif_transpose(img_copy)

    # Convert non-RGB modes (e.g. RGBA from PNG, P from GIF)
    if img_copy.mode not in ("RGB", "L"):
        img_copy = img_copy.convert("RGB")

    img_copy.thumbnail((size, size), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img_copy.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# compute_perceptual_hash
# ---------------------------------------------------------------------------

def compute_perceptual_hash(file_path: Path) -> str:
    """Return a 16-char hex perceptual hash (imagehash.phash, 64-bit)."""
    with Image.open(file_path) as img:
        h = imagehash.phash(img)
    return str(h)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_extractor.py -v
```

Expected: all tests pass. If GPS/location tests fail, check piexif DMS tuple format matches `_dms_to_decimal`.

- [ ] **Step 5: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/api/services/ingestion/photo_extractor.py apps/api/tests/test_photo_extractor.py
git commit -m "feat(api): implement photo metadata extractor with EXIF, GPS, thumbnails, pHash (S08-001)"
```

---

## Task 4: Photo Pipeline

**Files:**
- Create: `apps/api/tests/test_photo_pipeline.py`
- Create: `apps/api/api/services/ingestion/photo_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `apps/api/tests/test_photo_pipeline.py`:

```python
"""Tests for photo_pipeline.py (S08-001).

All DB and filesystem calls are mocked — no network or real DB needed.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import piexif
import pytest
from PIL import Image

from api.services.ingestion.photo_pipeline import ingest_photo


def _simple_jpeg() -> bytes:
    img = Image.new("RGB", (100, 80), (128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def _make_source(workspace_id=None):
    s = Mock()
    s.id = uuid4()
    s.workspace_id = workspace_id or uuid4()
    s.type = "photo_folder"
    return s


def _make_db(source, existing_file=None, existing_state=None):
    db = AsyncMock()

    source_result = MagicMock()
    source_result.scalar_one_or_none.return_value = source

    file_result = MagicMock()
    file_result.scalar_one_or_none.return_value = existing_file

    state_result = MagicMock()
    state_result.scalar_one_or_none.return_value = existing_state

    db.execute = AsyncMock(side_effect=[source_result, file_result, state_result])
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_ingest_photo_creates_file_and_state(tmp_path: Path):
    jpeg_path = tmp_path / "photo.jpg"
    jpeg_path.write_bytes(_simple_jpeg())

    source = _make_source()
    db = _make_db(source)

    with (
        patch("api.services.ingestion.photo_pipeline.compute_hash", return_value="abc123"),
        patch("api.services.ingestion.photo_pipeline.check_duplicate", return_value=None),
        patch("api.services.ingestion.photo_pipeline.asyncio.to_thread") as mock_thread,
        patch("api.services.ingestion.photo_pipeline.advance_stage", return_value=True),
        patch("api.services.ingestion.photo_pipeline._save_thumbnail", return_value="thumbnails/x.jpg"),
    ):
        from api.services.ingestion.photo_extractor import PhotoMetadata
        meta = PhotoMetadata(
            taken_at=None, gps_lat=None, gps_lon=None, location_name=None,
            camera_make="Canon", camera_model="R5",
            width=100, height=80, orientation=1, exif_json={},
        )
        mock_thread.side_effect = [meta, b"jpeg_thumb_bytes", "abcd1234abcd1234"]

        result = await ingest_photo(
            source_id=source.id,
            file_path=str(jpeg_path),
            db=db,
        )

    assert result["status"] in ("completed", "duplicate_skipped")
    db.add.assert_called()  # File + IngestionState + PhotoAsset added


@pytest.mark.asyncio
async def test_ingest_photo_unsupported_format(tmp_path: Path):
    txt_path = tmp_path / "document.txt"
    txt_path.write_text("not an image")

    source = _make_source()
    db = _make_db(source)

    result = await ingest_photo(
        source_id=source.id,
        file_path=str(txt_path),
        db=db,
    )

    assert result["status"] == "skipped_unsupported"


@pytest.mark.asyncio
async def test_ingest_photo_source_not_found():
    db = AsyncMock()
    not_found_result = MagicMock()
    not_found_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=not_found_result)

    from api.errors import NotFoundError
    with pytest.raises(NotFoundError):
        await ingest_photo(source_id=uuid4(), file_path="/any/photo.jpg", db=db)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_pipeline.py -v 2>&1 | head -10
```

Expected: ImportError — `photo_pipeline` does not exist.

- [ ] **Step 3: Implement photo_pipeline.py**

Create `apps/api/api/services/ingestion/photo_pipeline.py`:

```python
"""Photo ingestion pipeline: DISCOVERED → COMPLETED (S08-001).

Entry point: ingest_photo(source_id, file_path, db)

Pipeline stages:
  DISCOVERED        → FINGERPRINTED   : SHA-256 hash + dedup check
  FINGERPRINTED     → METADATA_EXTRACTED : EXIF extraction + thumbnail + pHash → upsert photo_assets
  METADATA_EXTRACTED→ TEXT_EXTRACTED  : no-op (photos have no text)
  TEXT_EXTRACTED    → OCR_COMPLETED   : no-op
  OCR_COMPLETED     → EMBEDDING_QUEUED: no-op (CLIP embeddings deferred to S10+)
  EMBEDDING_QUEUED  → EMBEDDED        : no-op
  EMBEDDED          → COMPLETED

CPU-bound extractor calls wrapped in asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.models.file import File
from api.db.models.ingestion_state import IngestionState
from api.db.models.photo_asset import PhotoAsset
from api.db.models.source import Source
from api.errors import NotFoundError
from api.services.ingestion.dedup import check_duplicate, compute_hash
from api.services.ingestion.photo_extractor import (
    PhotoMetadata,
    compute_perceptual_hash,
    extract_metadata,
    generate_thumbnail,
)
from api.services.ingestion.state_machine import advance_stage, fail_stage

logger = structlog.get_logger()

_PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".heic", ".heif"})

# Stages to advance through with no work (photos have no text/embeddings yet)
_NO_OP_STAGES = ["METADATA_EXTRACTED", "TEXT_EXTRACTED", "OCR_COMPLETED", "EMBEDDING_QUEUED"]


async def _save_thumbnail(thumb_bytes: bytes, workspace_id: UUID, photo_id: UUID) -> str:
    """Save thumbnail bytes to THUMBNAIL_DIR and return relative path."""
    base = Path(settings.THUMBNAIL_DIR)
    ws_dir = base / str(workspace_id)
    ws_dir.mkdir(parents=True, exist_ok=True)
    out_path = ws_dir / f"{photo_id}.jpg"
    out_path.write_bytes(thumb_bytes)
    return str(out_path.relative_to(base))


async def ingest_photo(
    *,
    source_id: UUID,
    file_path: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run the full photo ingestion pipeline for a single file.

    Returns a status dict: {status, file_id}.
    Raises NotFoundError if source_id is not found.
    """
    path = Path(file_path)

    # 1. Validate file extension
    if path.suffix.lower() not in _PHOTO_SUFFIXES:
        logger.info("photo_pipeline_unsupported", suffix=path.suffix)
        return {"status": "skipped_unsupported", "file_id": None}

    # 2. Load source
    src_result = await db.execute(
        select(Source).where(and_(Source.id == source_id, Source.deleted_at.is_(None)))
    )
    source = src_result.scalar_one_or_none()
    if source is None:
        raise NotFoundError(error_code="SOURCE_NOT_FOUND", message=f"Source {source_id} not found.")

    workspace_id = source.workspace_id

    # 3. Look up or create File row
    file_result = await db.execute(
        select(File).where(and_(File.source_id == source_id, File.path == file_path, File.deleted_at.is_(None)))
    )
    file_row = file_result.scalar_one_or_none()

    if file_row is None:
        mime_type, _ = mimetypes.guess_type(file_path)
        file_row = File(
            workspace_id=workspace_id,
            source_id=source_id,
            filename=path.name,
            path=file_path,
            mime_type=mime_type or "image/jpeg",
            size_bytes=path.stat().st_size if path.exists() else None,
        )
        db.add(file_row)
        await db.flush()  # populate file_row.id

    # 4. Look up or create IngestionState
    state_result = await db.execute(
        select(IngestionState).where(IngestionState.file_id == file_row.id)
    )
    state = state_result.scalar_one_or_none()

    if state is None:
        state = IngestionState(
            file_id=file_row.id,
            workspace_id=workspace_id,
            current_stage="DISCOVERED",
            stages_completed=[],
        )
        db.add(state)
        await db.flush()

    file_id = file_row.id

    # ── Stage: DISCOVERED → FINGERPRINTED ──────────────────────────────────
    if state.current_stage == "DISCOVERED":
        content_hash = await asyncio.to_thread(compute_hash, file_path)
        duplicate = await check_duplicate(content_hash, workspace_id, db, exclude_file_id=file_id)
        if duplicate is not None:
            file_row.is_duplicate = True
            file_row.duplicate_of_id = duplicate.id
            file_row.content_hash_sha256 = content_hash
            await db.commit()
            logger.info("photo_pipeline_duplicate", file_id=str(file_id))
            return {"status": "duplicate_skipped", "file_id": str(file_id)}

        file_row.content_hash_sha256 = content_hash
        await advance_stage(file_id, "DISCOVERED", db)

    # ── Stage: FINGERPRINTED → METADATA_EXTRACTED ──────────────────────────
    if state.current_stage == "FINGERPRINTED":
        try:
            meta: PhotoMetadata = await asyncio.to_thread(extract_metadata, path)
            thumb_bytes: bytes = await asyncio.to_thread(generate_thumbnail, path)
            phash: str = await asyncio.to_thread(compute_perceptual_hash, path)
        except Exception as exc:
            await fail_stage(file_id, "FINGERPRINTED", str(exc), db)
            logger.error("photo_pipeline_extraction_failed", file_id=str(file_id), exc_info=True)
            return {"status": "failed", "file_id": str(file_id)}

        thumbnail_rel = await _save_thumbnail(thumb_bytes, workspace_id, file_id)

        photo_asset = PhotoAsset(
            file_id=file_id,
            workspace_id=workspace_id,
            taken_at=meta.taken_at,
            gps_lat=meta.gps_lat,
            gps_lon=meta.gps_lon,
            location_name=meta.location_name,
            camera_make=meta.camera_make,
            camera_model=meta.camera_model,
            width=meta.width,
            height=meta.height,
            orientation=meta.orientation,
            thumbnail_path=thumbnail_rel,
            perceptual_hash=phash,
            exif_json=meta.exif_json,
        )
        db.add(photo_asset)
        await advance_stage(file_id, "FINGERPRINTED", db)

    # ── No-op stages: METADATA_EXTRACTED through EMBEDDING_QUEUED ──────────
    for no_op_stage in _NO_OP_STAGES:
        # Reload state to check current position
        state_r = await db.execute(select(IngestionState).where(IngestionState.file_id == file_id))
        refreshed = state_r.scalar_one_or_none()
        if refreshed and refreshed.current_stage == no_op_stage:
            await advance_stage(file_id, no_op_stage, db)

    # ── Stage: EMBEDDED → COMPLETED ────────────────────────────────────────
    state_r = await db.execute(select(IngestionState).where(IngestionState.file_id == file_id))
    refreshed = state_r.scalar_one_or_none()
    if refreshed and refreshed.current_stage == "EMBEDDED":
        await advance_stage(file_id, "EMBEDDED", db)

    await db.commit()
    logger.info("photo_pipeline_complete", file_id=str(file_id))
    return {"status": "completed", "file_id": str(file_id)}
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_pipeline.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/api/services/ingestion/photo_pipeline.py apps/api/tests/test_photo_pipeline.py
git commit -m "feat(api): implement photo ingestion pipeline DISCOVERED→COMPLETED (S08-001)"
```

---

## Task 5: Photos Router + Internal Endpoint

**Files:**
- Create: `apps/api/api/routers/photos.py`
- Modify: `apps/api/api/routers/internal.py`
- Modify: `apps/api/api/main.py`

- [ ] **Step 1: Create photos router**

Create `apps/api/api/routers/photos.py`:

```python
"""Photo asset endpoints (S08-001).

GET /api/v1/photos/{id}           — photo metadata card
GET /api/v1/photos/{id}/thumbnail — JPEG thumbnail bytes
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import settings
from api.db.models.photo_asset import PhotoAsset
from api.db.session import get_db
from api.errors import NotFoundError
from api.middleware.auth import get_current_user
from api.middleware.feature_gate import require_flag
from api.schemas.auth import CurrentUser
from api.schemas.envelope import PhotoCard

logger = structlog.get_logger()

_FLAG = require_flag("photos_enabled")

router = APIRouter(prefix="/api/v1/photos", tags=["photos"])


def _photo_to_card(photo: PhotoAsset) -> PhotoCard:
    camera = " ".join(p for p in [photo.camera_make, photo.camera_model] if p).strip() or None
    return PhotoCard(
        id=photo.id,
        priority_score=0.7,
        source_ids=[photo.file_id],
        payload={
            "photo_id": str(photo.id),
            "thumbnail_url": f"/api/v1/photos/{photo.id}/thumbnail",
            "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
            "location_name": photo.location_name,
            "camera": camera,
            "width": photo.width,
            "height": photo.height,
        },
    )


@router.get("/{photo_id}", dependencies=[_FLAG])
async def get_photo(
    photo_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(PhotoAsset).where(
        and_(
            PhotoAsset.id == photo_id,
            PhotoAsset.workspace_id.in_(user.workspace_ids),
            PhotoAsset.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    photo = result.scalar_one_or_none()
    if photo is None:
        raise NotFoundError(error_code="PHOTO_NOT_FOUND", message="Photo not found.")
    return _photo_to_card(photo).model_dump()


@router.get("/{photo_id}/thumbnail", dependencies=[_FLAG])
async def get_photo_thumbnail(
    photo_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    stmt = select(PhotoAsset).where(
        and_(
            PhotoAsset.id == photo_id,
            PhotoAsset.workspace_id.in_(user.workspace_ids),
            PhotoAsset.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    photo = result.scalar_one_or_none()
    if photo is None:
        raise NotFoundError(error_code="PHOTO_NOT_FOUND", message="Photo not found.")
    if not photo.thumbnail_path:
        raise NotFoundError(error_code="THUMBNAIL_NOT_FOUND", message="Thumbnail not yet generated.")

    thumb_path = Path(settings.THUMBNAIL_DIR) / photo.thumbnail_path
    if not thumb_path.exists():
        raise NotFoundError(error_code="THUMBNAIL_NOT_FOUND", message="Thumbnail file missing.")

    return Response(
        content=thumb_path.read_bytes(),
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=86400"},
    )
```

- [ ] **Step 2: Add internal ingest/photo endpoint**

In `apps/api/api/routers/internal.py`, add after the correspondent-bridge section (end of file):

```python
# ---------------------------------------------------------------------------
# Photo ingestion endpoint
# ---------------------------------------------------------------------------


class PhotoIngestRequest(BaseModel):
    source_id: UUID
    file_path: str = Field(min_length=1, max_length=4096)


async def _run_photo_ingest(source_id: UUID, file_path: str) -> None:
    """Run photo ingestion pipeline in a fresh DB session."""
    from api.services.ingestion.photo_pipeline import ingest_photo

    async with async_session() as db:
        try:
            result = await ingest_photo(source_id=source_id, file_path=file_path, db=db)
            logger.info(
                "photo_ingest_background_complete",
                source_id=str(source_id),
                **{k: str(v) if v else v for k, v in result.items()},
            )
        except Exception:
            logger.error(
                "photo_ingest_background_error",
                source_id=str(source_id),
                exc_info=True,
            )


@router.post("/ingest/photo", status_code=202)
async def trigger_photo_ingest(body: PhotoIngestRequest) -> dict:
    """Trigger photo ingestion for a single file.

    Runs asynchronously in the background — returns 202 immediately.
    Not exposed externally — Caddy does not route /api/v1/internal/*.
    """
    asyncio.create_task(_run_photo_ingest(body.source_id, body.file_path))
    logger.info("photo_ingest_triggered", source_id=str(body.source_id))
    return {"status": "ingestion_started", "source_id": str(body.source_id)}
```

- [ ] **Step 3: Register photos router in main.py**

In `apps/api/api/main.py`, add the import:

```python
from api.routers import admin, auth, health, internal, photos, query, recap, reminders, search, sources, today
```

And add the router registration after `reminders`:

```python
    app.include_router(photos.router)
```

- [ ] **Step 4: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/api/routers/photos.py apps/api/api/routers/internal.py apps/api/api/main.py
git commit -m "feat(api): add photos router GET /photos/{id} + /thumbnail and internal ingest endpoint (S08-001)"
```

---

## Task 6: Photo Search Service (TDD)

**Files:**
- Create: `apps/api/tests/test_photo_search.py`
- Create: `apps/api/api/services/search/photo_search.py`

- [ ] **Step 1: Write failing tests**

Create `apps/api/tests/test_photo_search.py`:

```python
"""Tests for photo_search.py (S08-002)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from api.services.search.photo_search import PhotoFilters, search_photos


def _make_photo(
    workspace_id=None,
    taken_at=None,
    location_name=None,
    camera_make=None,
    camera_model=None,
    gps_lat=None,
):
    p = Mock()
    p.id = uuid4()
    p.file_id = uuid4()
    p.workspace_id = workspace_id or uuid4()
    p.taken_at = taken_at
    p.location_name = location_name
    p.camera_make = camera_make
    p.camera_model = camera_model
    p.gps_lat = gps_lat
    p.gps_lon = gps_lat  # same value for simplicity
    p.width = 1920
    p.height = 1080
    p.deleted_at = None
    return p


def _make_db(photos, total=None):
    db = AsyncMock()

    photos_result = MagicMock()
    photos_result.scalars.return_value.all.return_value = photos

    count_result = MagicMock()
    count_result.scalar_one.return_value = total if total is not None else len(photos)

    db.execute = AsyncMock(side_effect=[photos_result, count_result])
    return db


@pytest.mark.asyncio
async def test_search_photos_returns_photo_cards():
    ws_id = uuid4()
    photo = _make_photo(workspace_id=ws_id, location_name="Paris")
    db = _make_db([photo])

    cards, total = await search_photos(
        workspace_ids=[ws_id],
        query="Paris",
        filters=PhotoFilters(),
        limit=10,
        offset=0,
        db=db,
    )

    assert len(cards) == 1
    assert cards[0].type == "photo"
    assert cards[0].payload["location_name"] == "Paris"
    assert total == 1


@pytest.mark.asyncio
async def test_search_photos_workspace_isolation():
    """DB mock returns empty list — simulates workspace filter working."""
    ws_id = uuid4()
    db = _make_db([], total=0)

    cards, total = await search_photos(
        workspace_ids=[ws_id],
        query="Paris",
        filters=PhotoFilters(),
        limit=10,
        offset=0,
        db=db,
    )

    assert cards == []
    assert total == 0


@pytest.mark.asyncio
async def test_search_photos_empty_query_returns_all():
    ws_id = uuid4()
    photos = [_make_photo(workspace_id=ws_id) for _ in range(3)]
    db = _make_db(photos, total=3)

    cards, total = await search_photos(
        workspace_ids=[ws_id],
        query="",
        filters=PhotoFilters(),
        limit=10,
        offset=0,
        db=db,
    )

    assert len(cards) == 3
    assert total == 3


@pytest.mark.asyncio
async def test_search_photos_thumbnail_url_in_payload():
    ws_id = uuid4()
    photo = _make_photo(workspace_id=ws_id)
    db = _make_db([photo])

    cards, _ = await search_photos(
        workspace_ids=[ws_id],
        query="",
        filters=PhotoFilters(),
        limit=10,
        offset=0,
        db=db,
    )

    assert f"/api/v1/photos/{photo.id}/thumbnail" == cards[0].payload["thumbnail_url"]


@pytest.mark.asyncio
async def test_search_photos_camera_payload():
    ws_id = uuid4()
    photo = _make_photo(workspace_id=ws_id, camera_make="Canon", camera_model="EOS R5")
    db = _make_db([photo])

    cards, _ = await search_photos(
        workspace_ids=[ws_id],
        query="",
        filters=PhotoFilters(),
        limit=10,
        offset=0,
        db=db,
    )

    assert cards[0].payload["camera"] == "Canon EOS R5"


@pytest.mark.asyncio
async def test_search_photos_no_camera_returns_none():
    ws_id = uuid4()
    photo = _make_photo(workspace_id=ws_id, camera_make=None, camera_model=None)
    db = _make_db([photo])

    cards, _ = await search_photos(
        workspace_ids=[ws_id],
        query="",
        filters=PhotoFilters(),
        limit=10,
        offset=0,
        db=db,
    )

    assert cards[0].payload["camera"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_search.py -v 2>&1 | head -10
```

Expected: ImportError.

- [ ] **Step 3: Implement photo_search.py**

Create `apps/api/api/services/search/photo_search.py`:

```python
"""Photo metadata search service (S08-002).

Filters on direct columns of photo_assets — no JSONB queries needed.
All string filters use ILIKE for case-insensitive partial matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.photo_asset import PhotoAsset
from api.schemas.envelope import PhotoCard

logger = structlog.get_logger()


@dataclass(frozen=True)
class PhotoFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    location_contains: str | None = None    # ILIKE on location_name
    camera: str | None = None               # ILIKE on make || ' ' || model
    has_gps: bool | None = None


def _build_filters(
    workspace_ids: list[UUID],
    query: str,
    filters: PhotoFilters,
):
    """Build a list of SQLAlchemy filter clauses."""
    clauses = [
        PhotoAsset.workspace_id.in_(workspace_ids),
        PhotoAsset.deleted_at.is_(None),
    ]

    if filters.date_from is not None:
        clauses.append(PhotoAsset.taken_at >= filters.date_from)
    if filters.date_to is not None:
        clauses.append(PhotoAsset.taken_at <= filters.date_to)
    if filters.location_contains:
        clauses.append(PhotoAsset.location_name.ilike(f"%{filters.location_contains}%"))
    if filters.camera:
        cam_like = f"%{filters.camera}%"
        clauses.append(
            or_(
                PhotoAsset.camera_make.ilike(cam_like),
                PhotoAsset.camera_model.ilike(cam_like),
            )
        )
    if filters.has_gps is True:
        clauses.append(PhotoAsset.gps_lat.isnot(None))
    elif filters.has_gps is False:
        clauses.append(PhotoAsset.gps_lat.is_(None))

    if query:
        q_like = f"%{query}%"
        clauses.append(
            or_(
                PhotoAsset.location_name.ilike(q_like),
                PhotoAsset.camera_make.ilike(q_like),
                PhotoAsset.camera_model.ilike(q_like),
            )
        )

    return clauses


def _photo_to_card(photo: PhotoAsset) -> PhotoCard:
    camera_parts = [p for p in [photo.camera_make, photo.camera_model] if p]
    camera = " ".join(camera_parts).strip() or None
    return PhotoCard(
        id=photo.id,
        priority_score=0.7,
        source_ids=[photo.file_id],
        payload={
            "photo_id": str(photo.id),
            "thumbnail_url": f"/api/v1/photos/{photo.id}/thumbnail",
            "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
            "location_name": photo.location_name,
            "camera": camera,
            "width": photo.width,
            "height": photo.height,
        },
    )


async def search_photos(
    workspace_ids: list[UUID],
    query: str,
    filters: PhotoFilters,
    limit: int,
    offset: int,
    db: AsyncSession,
) -> tuple[list[PhotoCard], int]:
    """Search photo_assets by metadata filters and free-text query.

    Returns (cards, total_count).  Cards are ordered taken_at DESC.
    """
    clauses = _build_filters(workspace_ids, query, filters)

    stmt = (
        select(PhotoAsset)
        .where(and_(*clauses))
        .order_by(PhotoAsset.taken_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    photos = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(PhotoAsset)
        .where(and_(*clauses))
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return [_photo_to_card(p) for p in photos], total
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_search.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/api/services/search/photo_search.py apps/api/tests/test_photo_search.py
git commit -m "feat(api): implement photo metadata search service (S08-002)"
```

---

## Task 7: Wire Photo Search into search_all() and Router

**Files:**
- Modify: `apps/api/api/services/query/search.py`
- Modify: `apps/api/api/routers/search.py`

- [ ] **Step 1: Extend search.py aggregator**

In `apps/api/api/services/query/search.py`:

1. Change the `SearchType` Literal:
```python
SearchType = Literal["calendar", "reminder", "contact", "file", "photo"]
```

2. Add import at top:
```python
from api.services.search.photo_search import PhotoFilters, search_photos
```

3. Add `has_gps` param to `search_all()` signature:
```python
async def search_all(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    types: list[SearchType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    has_gps: bool | None = None,          # NEW
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Card], dict[str, int]]:
```

4. Update `search_types` default to include `"photo"`:
```python
search_types = types or ["calendar", "reminder", "contact", "file", "photo"]
```

5. Add photo dispatch block after the `"file"` block:
```python
    if "photo" in search_types:
        photo_filters = PhotoFilters(
            date_from=date_from,
            date_to=date_to,
            has_gps=has_gps,
        )
        photo_cards, photo_total = await search_photos(
            workspace_ids=[workspace_id],
            query=query,
            filters=photo_filters,
            limit=limit,
            offset=offset,
            db=db,
        )
        all_cards.extend(photo_cards)
        facets["photo"] = photo_total
```

- [ ] **Step 2: Extend search router**

In `apps/api/api/routers/search.py`:

1. Update the `type` Literal to include `"photo"`:
```python
    type: Literal["calendar", "reminder", "contact", "file", "photo", "all"] = Query(
        "all", description="Type filter"
    ),
```

2. Add `has_gps` query param after `date_to`:
```python
    has_gps: bool | None = Query(None, description="Filter photos with GPS coordinates"),
```

3. Update the `search_all()` call to pass `has_gps`:
```python
    cards, facets = await search_all(
        q,
        workspace_id,
        db,
        types=types,
        date_from=date_from,
        date_to=date_to,
        has_gps=has_gps,
        limit=per_page + 1,
        offset=cursor,
    )
```

- [ ] **Step 3: Run tests to verify no regressions**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_search.py tests/test_photo_search.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/api/services/query/search.py apps/api/api/routers/search.py
git commit -m "feat(api): add photo type to search_all() and GET /search router (S08-002)"
```

---

## Task 8: Deterministic Query Patterns + Router Handlers

**Files:**
- Modify: `apps/api/api/services/query/patterns.py`
- Modify: `apps/api/api/services/query/router.py`

- [ ] **Step 1: Add photo IntentTypes and patterns to patterns.py**

In `apps/api/api/services/query/patterns.py`:

1. Add three new values to the `IntentType` Literal (append to the existing list):
```python
IntentType = Literal[
    "calendar_range",
    "calendar_with_person",
    "calendar_at_location",
    "reminders_range",
    "reminders_by_priority",
    "reminders_by_list",
    "contact_search",
    "contact_by_org",
    "contact_field",
    "count_query",
    "recent_query",
    "photo_date",        # NEW
    "photo_location",    # NEW
    "photo_camera",      # NEW
]
```

2. Add three extractor functions near the existing extractors:
```python
def _photo_date(m: re.Match) -> dict[str, str]:
    return {"date_ref": m.group("date_ref").strip()}

def _photo_location(m: re.Match) -> dict[str, str]:
    return {"location": m.group("location").strip()}

def _photo_camera(m: re.Match) -> dict[str, str]:
    return {"camera": m.group("camera").strip()}
```

3. Add three patterns to `_PATTERNS` (append after pattern 53):
```python
    # ══════════════════════════════════════════════════════════════════════
    # PHOTOS
    # ══════════════════════════════════════════════════════════════════════

    # 54. "photos from last week" / "photos from 2024" / "photo from yesterday"
    (re.compile(
        r"photos?\s+from\s+(?P<date_ref>"
        r"yesterday|today|last week|last month|this week|this month|\d{4})",
        re.I,
    ), "photo_date", _photo_date),

    # 55. "photos in Paris" / "photos near home" / "photos from Tokyo"
    (re.compile(r"photos?\s+(?:in|from|near|at)\s+(?P<location>.+)", re.I),
     "photo_location", _photo_location),

    # 56. "photos with iPhone" / "photos taken with Canon" / "photos from Nikon camera"
    (re.compile(
        r"photos?\s+(?:with|taken with|from|shot with)\s+(?P<camera>.+?)(?:\s+camera|\s+phone|\s+iphone)?\s*$",
        re.I,
    ), "photo_camera", _photo_camera),
```

- [ ] **Step 2: Add photo handlers to router.py**

In `apps/api/api/services/query/router.py`:

1. Add imports for PhotoAsset and photo_search at top:
```python
from api.services.search.photo_search import PhotoFilters, search_photos
from api.services.query.date_parser import parse_date_reference
```
(Note: `parse_date_reference` is already imported — do not duplicate it.)

2. Add three handler functions before `_HANDLERS`:
```python
async def _handle_photo_date(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    date_ref = params.get("date_ref", "today")
    date_range = parse_date_reference(date_ref)
    date_from = date_range.start if date_range else None
    date_to = date_range.end if date_range else None

    cards, _ = await search_photos(
        workspace_ids=[workspace_id],
        query="",
        filters=PhotoFilters(date_from=date_from, date_to=date_to),
        limit=20,
        offset=0,
        db=db,
    )
    return cards


async def _handle_photo_location(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    location = params.get("location", "")
    cards, _ = await search_photos(
        workspace_ids=[workspace_id],
        query="",
        filters=PhotoFilters(location_contains=location),
        limit=20,
        offset=0,
        db=db,
    )
    return cards


async def _handle_photo_camera(
    params: dict[str, str],
    workspace_id: UUID,
    db: AsyncSession,
) -> list[Card]:
    camera = params.get("camera", "")
    cards, _ = await search_photos(
        workspace_ids=[workspace_id],
        query="",
        filters=PhotoFilters(camera=camera),
        limit=20,
        offset=0,
        db=db,
    )
    return cards
```

3. Add entries to `_HANDLERS`:
```python
_HANDLERS = {
    ...existing entries...,
    "photo_date": _handle_photo_date,
    "photo_location": _handle_photo_location,
    "photo_camera": _handle_photo_camera,
}
```

- [ ] **Step 3: Add pattern tests to test_photo_search.py**

Append to `apps/api/tests/test_photo_search.py`:

```python
# ── Pattern classification tests ──────────────────────────────────────────────

from api.services.query.patterns import classify_query


def test_pattern_photo_date_last_week():
    intent = classify_query("photos from last week")
    assert intent is not None
    assert intent.intent_type == "photo_date"
    assert intent.params["date_ref"] == "last week"


def test_pattern_photo_date_year():
    intent = classify_query("photos from 2024")
    assert intent is not None
    assert intent.intent_type == "photo_date"
    assert intent.params["date_ref"] == "2024"


def test_pattern_photo_location():
    intent = classify_query("photos in Paris")
    assert intent is not None
    assert intent.intent_type == "photo_location"
    assert intent.params["location"] == "Paris"


def test_pattern_photo_location_near():
    intent = classify_query("photos near home")
    assert intent is not None
    assert intent.intent_type == "photo_location"
    assert intent.params["location"] == "home"


def test_pattern_photo_camera():
    intent = classify_query("photos with iPhone")
    assert intent is not None
    assert intent.intent_type == "photo_camera"
    assert "iphone" in intent.params["camera"].lower()


def test_pattern_photo_camera_brand():
    intent = classify_query("photos taken with Canon")
    assert intent is not None
    assert intent.intent_type == "photo_camera"
    assert "canon" in intent.params["camera"].lower()
```

- [ ] **Step 4: Run all photo tests**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/test_photo_search.py tests/test_photo_extractor.py tests/test_photo_pipeline.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add apps/api/api/services/query/patterns.py apps/api/api/services/query/router.py apps/api/tests/test_photo_search.py
git commit -m "feat(api): add photo deterministic query patterns and router handlers (S08-002)"
```

---

## Task 9: Full Test Suite + Final Commit

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/arpankorat/Desktop/EkamCore/apps/api
poetry run pytest tests/ --ignore=tests/integration -q 2>&1 | tail -15
```

Expected: no new failures beyond the pre-existing `test_calendar_query_returns_matching_events` failure.

- [ ] **Step 2: Verify feature flags**

Confirm `photos_enabled: true` in `config/feature-flags.json` and `"photos_enabled"` is in `_ENABLED_FLAGS` in `middleware/feature_gate.py`.

- [ ] **Step 3: Final commit message per user spec**

```bash
cd /Users/arpankorat/Desktop/EkamCore
git add -A
git commit -m "feat(api): implement photo metadata extraction with EXIF, GPS, thumbnails (S08-001)

feat(api): implement photo search by date, location, and metadata (S08-002)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Note: if all changes were already committed in tasks 1-8, skip this step.

---

## Self-Review

**Spec coverage check:**
- ✅ photo_assets migration (Task 2)
- ✅ PhotoAsset ORM model (Task 2)
- ✅ extract_metadata / generate_thumbnail / compute_perceptual_hash (Task 3)
- ✅ EXIF GPS DMS→decimal conversion (Task 3)
- ✅ reverse_geocoder offline lookup (Task 3)
- ✅ Photo pipeline DISCOVERED→COMPLETED skipping text/embedding stages (Task 4)
- ✅ POST /internal/ingest/photo (Task 5)
- ✅ GET /photos/{id} and GET /photos/{id}/thumbnail with Cache-Control (Task 5)
- ✅ search_photos() with PhotoFilters (Task 6)
- ✅ PhotoCard payload with thumbnail_url, taken_at, location_name, camera, dimensions (Task 6)
- ✅ type='photo' in GET /search (Task 7)
- ✅ has_gps query param (Task 7)
- ✅ photo_date, photo_location, photo_camera patterns (Task 8)
- ✅ Deterministic router handlers for three photo intents (Task 8)
- ✅ All golden rules: workspace isolation, soft-delete filters, no PII in logs, feature flags

**Type consistency:** `PhotoFilters` defined in Task 6, imported in Tasks 7 and 8. `PhotoMetadata` defined in Task 3, used in Task 4. `search_photos()` signature is consistent across all usages.

**No placeholders:** All code blocks are complete and runnable.

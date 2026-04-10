"""Photo metadata extraction: EXIF, GPS, thumbnails, perceptual hash (S08-001).

All three public functions are synchronous (CPU-bound Pillow operations).
Call them via asyncio.to_thread() inside async pipeline code.

Supported formats: JPEG, PNG, TIFF, WebP, HEIC (via pillow-heif).
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

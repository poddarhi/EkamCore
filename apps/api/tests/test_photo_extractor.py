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


def test_dms_to_decimal_zero_denominator_safe():
    # Seconds denominator=0 is legal EXIF for unknown; must not raise
    result = _dms_to_decimal(((48, 1), (51, 1), (0, 0)), "N")
    assert result == pytest.approx(48.85, abs=0.01)


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
    from unittest.mock import patch
    jpeg_bytes = _make_test_jpeg(gps_lat=48.8566, gps_lon=2.3522)
    p = tmp_path / "test.jpg"
    p.write_bytes(jpeg_bytes)

    with patch("api.services.ingestion.photo_extractor._reverse_geocode", return_value="Paris, Île-de-France, FR"):
        meta = extract_metadata(p)

    assert meta.location_name == "Paris, Île-de-France, FR"


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

    # Use structurally different images (gradient vs checkerboard pattern)
    # pHash is DCT-based so structurally distinct images produce different hashes
    import numpy as np

    arr_a = np.zeros((200, 200, 3), dtype=np.uint8)
    for i in range(200):
        arr_a[i, :, 0] = i  # horizontal gradient

    arr_b = np.zeros((200, 200, 3), dtype=np.uint8)
    for i in range(200):
        for j in range(200):
            arr_b[i, j] = 255 if (i // 25 + j // 25) % 2 == 0 else 0  # checkerboard

    img_a = Image.fromarray(arr_a)
    img_b = Image.fromarray(arr_b)
    buf_a, buf_b = io.BytesIO(), io.BytesIO()
    img_a.save(buf_a, "JPEG")
    img_b.save(buf_b, "JPEG")
    p1.write_bytes(buf_a.getvalue())
    p2.write_bytes(buf_b.getvalue())

    h1 = compute_perceptual_hash(p1)
    h2 = compute_perceptual_hash(p2)
    assert h1 != h2

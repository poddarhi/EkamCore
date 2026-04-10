"""Tests for photo_pipeline.py (S08-001).

All DB and filesystem calls are mocked — no network or real DB needed.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

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

    # Re-fetch after advance_stage("DISCOVERED"): returns state with FINGERPRINTED
    fingerprinted_state = MagicMock()
    fingerprinted_state.current_stage = "FINGERPRINTED"
    refetch_after_discovered = MagicMock()
    refetch_after_discovered.scalar_one_or_none.return_value = fingerprinted_state

    # Add a fallback for the no-op stage re-queries
    refreshed_state_mock = MagicMock()
    refreshed_state_mock.scalar_one_or_none.return_value = None  # state not found → no-op stages skipped
    db.execute = AsyncMock(
        side_effect=[source_result, file_result, state_result, refetch_after_discovered] + [refreshed_state_mock] * 10
    )
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
        # to_thread is called for: compute_hash, extract_metadata, generate_thumbnail, compute_perceptual_hash
        mock_thread.side_effect = ["abc123", meta, b"jpeg_thumb_bytes", "abcd1234abcd1234"]

        result = await ingest_photo(
            source_id=source.id,
            file_path=str(jpeg_path),
            db=db,
        )

    assert result["status"] in ("completed", "duplicate_skipped")
    assert db.add.call_count >= 3  # File + IngestionState + PhotoAsset added


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

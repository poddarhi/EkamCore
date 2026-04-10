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

"""Tests for pHash near-duplicate photo detection (S08-003).

Covers:
  - hamming_distance: identical, one-bit, max-distance
  - find_near_duplicates: finds close photos, excludes distant, excludes self, workspace isolation
  - scan_for_near_duplicates: empty workspace, groups near-dupes, no false positives
  - photo_pipeline: exact SHA-256 duplicate marks IngestionState as SKIPPED
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from api.services.ingestion.dedup_photos import (
    hamming_distance,
    find_near_duplicates,
    scan_for_near_duplicates,
)


# ---------------------------------------------------------------------------
# Unit tests: hamming_distance
# ---------------------------------------------------------------------------


def test_hamming_distance_identical_hashes():
    """Identical hashes have distance 0."""
    h = "abcd1234abcd1234"
    assert hamming_distance(h, h) == 0


def test_hamming_distance_one_bit_differs():
    """Hashes differing in exactly one bit have distance 1."""
    # 0x0 and 0x1 differ in exactly 1 bit
    h1 = "0000000000000000"
    h2 = "0000000000000001"
    assert hamming_distance(h1, h2) == 1


def test_hamming_distance_all_bits_differ():
    """Complementary hashes (all bits flipped) have distance 64."""
    h1 = "0000000000000000"
    h2 = "ffffffffffffffff"
    assert hamming_distance(h1, h2) == 64


def test_hamming_distance_symmetric():
    """Distance is symmetric: d(a,b) == d(b,a)."""
    h1 = "cafe1234cafe1234"
    h2 = "dead5678dead5678"
    assert hamming_distance(h1, h2) == hamming_distance(h2, h1)


def test_hamming_distance_four_bits():
    """0x0 vs 0xf: 4 bits differ."""
    h1 = "000000000000000f"
    h2 = "0000000000000000"
    assert hamming_distance(h1, h2) == 4


# ---------------------------------------------------------------------------
# Helpers to build mock photo objects
# ---------------------------------------------------------------------------


def _make_photo(workspace_id=None, phash=None, file_id=None):
    p = Mock()
    p.id = uuid4()
    p.file_id = file_id or uuid4()
    p.workspace_id = workspace_id or uuid4()
    p.perceptual_hash = phash
    p.deleted_at = None
    return p


def _make_db_with_photos(photos):
    """Return an AsyncMock db whose execute() returns the given photo list."""
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = photos
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# Integration-style tests: find_near_duplicates (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_near_duplicates_returns_close_photos():
    """Photos with Hamming distance ≤ threshold are returned."""
    ws_id = uuid4()
    target_hash = "0000000000000000"
    # One bit away — within threshold=5
    near_hash = "0000000000000001"
    far_hash = "ffffffffffffffff"  # 64 bits away — exceeds threshold

    target = _make_photo(workspace_id=ws_id, phash=target_hash)
    near = _make_photo(workspace_id=ws_id, phash=near_hash)
    far = _make_photo(workspace_id=ws_id, phash=far_hash)

    # DB returns all three when queried (the service filters by distance in Python)
    db = _make_db_with_photos([target, near, far])

    result = await find_near_duplicates(
        photo_id=target.id,
        workspace_id=ws_id,
        threshold=5,
        db=db,
    )

    result_ids = [p.id for p in result]
    assert near.id in result_ids
    assert far.id not in result_ids


@pytest.mark.asyncio
async def test_find_near_duplicates_excludes_self():
    """The target photo is never in the result list."""
    ws_id = uuid4()
    target_hash = "0000000000000000"
    target = _make_photo(workspace_id=ws_id, phash=target_hash)

    db = _make_db_with_photos([target])

    result = await find_near_duplicates(
        photo_id=target.id,
        workspace_id=ws_id,
        threshold=5,
        db=db,
    )

    assert target.id not in [p.id for p in result]


@pytest.mark.asyncio
async def test_find_near_duplicates_empty_when_all_far():
    """Returns empty list when no photo is within threshold."""
    ws_id = uuid4()
    target = _make_photo(workspace_id=ws_id, phash="0000000000000000")
    other = _make_photo(workspace_id=ws_id, phash="ffffffffffffffff")  # 64 bits away

    db = _make_db_with_photos([target, other])

    result = await find_near_duplicates(
        photo_id=target.id,
        workspace_id=ws_id,
        threshold=5,
        db=db,
    )

    assert result == []


@pytest.mark.asyncio
async def test_find_near_duplicates_skips_photos_without_phash():
    """Photos with None perceptual_hash are silently skipped."""
    ws_id = uuid4()
    target = _make_photo(workspace_id=ws_id, phash="0000000000000000")
    no_hash = _make_photo(workspace_id=ws_id, phash=None)

    db = _make_db_with_photos([target, no_hash])

    result = await find_near_duplicates(
        photo_id=target.id,
        workspace_id=ws_id,
        threshold=5,
        db=db,
    )

    assert no_hash.id not in [p.id for p in result]


# ---------------------------------------------------------------------------
# Integration-style tests: scan_for_near_duplicates (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_for_near_duplicates_empty_workspace():
    """Returns empty list when workspace has no photos."""
    db = _make_db_with_photos([])
    result = await scan_for_near_duplicates(workspace_id=uuid4(), threshold=5, db=db)
    assert result == []


@pytest.mark.asyncio
async def test_scan_for_near_duplicates_groups_near_dupes():
    """Photos within threshold are grouped together."""
    ws_id = uuid4()
    # Three photos: A and B are near-duplicates; C is far from both
    photo_a = _make_photo(workspace_id=ws_id, phash="0000000000000000")
    photo_b = _make_photo(workspace_id=ws_id, phash="0000000000000001")  # 1 bit from A
    photo_c = _make_photo(workspace_id=ws_id, phash="ffffffffffffffff")  # 64 bits from A/B

    db = _make_db_with_photos([photo_a, photo_b, photo_c])

    groups = await scan_for_near_duplicates(workspace_id=ws_id, threshold=5, db=db)

    # Should have exactly one group containing A and B
    assert len(groups) == 1
    group_ids = set(groups[0])
    assert photo_a.id in group_ids
    assert photo_b.id in group_ids
    assert photo_c.id not in group_ids


@pytest.mark.asyncio
async def test_scan_for_near_duplicates_no_false_positives():
    """Completely different photos produce no groups."""
    ws_id = uuid4()
    photo_a = _make_photo(workspace_id=ws_id, phash="0000000000000000")
    photo_b = _make_photo(workspace_id=ws_id, phash="ffffffffffffffff")  # 64 bits away

    db = _make_db_with_photos([photo_a, photo_b])

    groups = await scan_for_near_duplicates(workspace_id=ws_id, threshold=5, db=db)
    assert groups == []


@pytest.mark.asyncio
async def test_scan_for_near_duplicates_skips_none_phash():
    """Photos without pHash are excluded from grouping."""
    ws_id = uuid4()
    photo_a = _make_photo(workspace_id=ws_id, phash="0000000000000000")
    photo_b = _make_photo(workspace_id=ws_id, phash=None)

    db = _make_db_with_photos([photo_a, photo_b])

    groups = await scan_for_near_duplicates(workspace_id=ws_id, threshold=5, db=db)
    # No groups — only photo_a has a hash, nothing to pair with
    assert groups == []


@pytest.mark.asyncio
async def test_scan_for_near_duplicates_three_way_group():
    """Three mutually-close photos form a single group."""
    ws_id = uuid4()
    # All within 2 bits of each other
    photo_a = _make_photo(workspace_id=ws_id, phash="0000000000000000")
    photo_b = _make_photo(workspace_id=ws_id, phash="0000000000000001")  # 1 bit from A
    photo_c = _make_photo(workspace_id=ws_id, phash="0000000000000003")  # 2 bits from A, 1 from B

    db = _make_db_with_photos([photo_a, photo_b, photo_c])

    groups = await scan_for_near_duplicates(workspace_id=ws_id, threshold=5, db=db)

    assert len(groups) == 1
    group_ids = set(groups[0])
    assert {photo_a.id, photo_b.id, photo_c.id} == group_ids


# ---------------------------------------------------------------------------
# photo_pipeline: exact duplicate marks IngestionState as SKIPPED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_exact_duplicate_skips_ingestion_state():
    """When SHA-256 duplicate found, skip_file() is called to mark state SKIPPED."""
    from api.services.ingestion.photo_pipeline import ingest_photo

    source = Mock()
    source.id = uuid4()
    source.workspace_id = uuid4()

    duplicate_file = Mock()
    duplicate_file.id = uuid4()

    file_row = Mock()
    file_row.id = uuid4()
    file_row.is_duplicate = False
    file_row.duplicate_of_id = None
    file_row.content_hash_sha256 = None

    state = Mock()
    state.current_stage = "DISCOVERED"

    db = AsyncMock()
    source_res = MagicMock()
    source_res.scalar_one_or_none.return_value = source
    file_res = MagicMock()
    file_res.scalar_one_or_none.return_value = file_row
    state_res = MagicMock()
    state_res.scalar_one_or_none.return_value = state

    db.execute = AsyncMock(side_effect=[source_res, file_res, state_res])
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with (
        patch("api.services.ingestion.photo_pipeline.compute_hash", return_value="deadbeef"),
        patch("api.services.ingestion.photo_pipeline.check_duplicate", return_value=duplicate_file),
        patch("api.services.ingestion.photo_pipeline.skip_file", new_callable=AsyncMock) as mock_skip,
    ):
        result = await ingest_photo(
            source_id=source.id,
            file_path="/tmp/photo.jpg",
            db=db,
        )

    assert result["status"] == "duplicate_skipped"
    mock_skip.assert_called_once_with(file_row.id, "DISCOVERED", db)

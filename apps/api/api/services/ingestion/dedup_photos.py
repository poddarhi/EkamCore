"""pHash-based near-duplicate photo detection (S08-003).

Exact SHA-256 duplicates are handled by dedup.py + photo_pipeline.py.
This module handles perceptual (near-duplicate) detection via Hamming distance
on the 64-bit perceptual hash stored in photo_assets.perceptual_hash (16 hex chars).

Algorithm:
  1. Load all photo_assets with a non-null perceptual_hash for the workspace.
  2. For each pair, compute Hamming distance on the 64-bit integer representation.
  3. Group photos where any two are within `threshold` bits (union-find).

Workspace isolation: every query filters on workspace_id.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models.photo_asset import PhotoAsset

logger = structlog.get_logger()


def hamming_distance(hash1: str, hash2: str) -> int:
    """Return the Hamming distance between two 16-hex-char pHash strings.

    Each hash is a 64-bit integer encoded as 16 lowercase hex characters.
    Distance = number of bit positions that differ.
    """
    return bin(int(hash1, 16) ^ int(hash2, 16)).count("1")


async def _load_workspace_photos(
    workspace_id: UUID,
    db: AsyncSession,
) -> list[PhotoAsset]:
    """Load all non-deleted photo_assets with a perceptual_hash for a workspace."""
    stmt = select(PhotoAsset).where(
        and_(
            PhotoAsset.workspace_id == workspace_id,
            PhotoAsset.deleted_at.is_(None),
            PhotoAsset.perceptual_hash.isnot(None),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def find_near_duplicates(
    photo_id: UUID,
    workspace_id: UUID,
    threshold: int = 5,
    db: AsyncSession = None,
) -> list[PhotoAsset]:
    """Return photos in the workspace that are near-duplicates of photo_id.

    A near-duplicate is any photo whose pHash differs by ≤ threshold bits
    from the target photo's pHash. The target photo itself is excluded.

    Photos without a perceptual_hash are silently skipped.
    """
    photos = await _load_workspace_photos(workspace_id, db)

    target = next((p for p in photos if p.id == photo_id), None)
    if target is None or target.perceptual_hash is None:
        return []

    candidates: list[PhotoAsset] = []
    for photo in photos:
        if photo.id == photo_id:
            continue
        if photo.perceptual_hash is None:
            continue
        dist = hamming_distance(target.perceptual_hash, photo.perceptual_hash)
        if dist <= threshold:
            candidates.append(photo)

    return candidates


async def scan_for_near_duplicates(
    workspace_id: UUID,
    threshold: int = 5,
    db: AsyncSession = None,
) -> list[list[UUID]]:
    """Scan all photos in the workspace and return groups of near-duplicates.

    Uses union-find to cluster photos where any two are within `threshold`
    Hamming bits. Returns a list of groups; each group contains ≥ 2 photo IDs.
    Photos without a perceptual_hash are excluded.
    """
    photos = await _load_workspace_photos(workspace_id, db)
    hashable = [p for p in photos if p.perceptual_hash is not None]

    if len(hashable) < 2:
        return []

    # Union-find
    parent: dict[UUID, UUID] = {p.id: p.id for p in hashable}

    def find(x: UUID) -> UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: UUID, y: UUID) -> None:
        parent[find(x)] = find(y)

    # O(n²) pair comparison — acceptable for workspace-scale photo counts
    for i, pa in enumerate(hashable):
        for pb in hashable[i + 1 :]:
            dist = hamming_distance(pa.perceptual_hash, pb.perceptual_hash)
            if dist <= threshold:
                union(pa.id, pb.id)

    # Collect groups with ≥ 2 members
    groups: dict[UUID, list[UUID]] = {}
    for p in hashable:
        root = find(p.id)
        groups.setdefault(root, []).append(p.id)

    result = [members for members in groups.values() if len(members) >= 2]

    if result:
        logger.info(
            "near_duplicate_groups_found",
            workspace_id=str(workspace_id),
            group_count=len(result),
        )

    return result

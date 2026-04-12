"""Idempotent Qdrant collection initialization.

Creates required vector collections on startup if they don't already exist.
Called from the FastAPI lifespan handler.

S11-001 note: The face_embeddings collection has a required payload index
on workspace_id (the mandatory isolation control per Golden Rule #1). If
the collection exists but its payload indexes are missing or stale, we
delete and recreate it. This is safe because S11-001 is the first story
to populate the collection — no production data is lost.
"""

import structlog
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    VectorParams,
)

from api.services.qdrant_client import get_qdrant

logger = structlog.get_logger()

# Required payload indexes per collection. workspace_id is MANDATORY on all
# collections — it is the #1 isolation control.
COLLECTIONS = {
    "document_embeddings": {
        "vectors": VectorParams(size=768, distance=Distance.COSINE),
        "payload_indexes": {
            "workspace_id": PayloadSchemaType.KEYWORD,
            "file_id": PayloadSchemaType.KEYWORD,
            "source_id": PayloadSchemaType.KEYWORD,
            "chunk_index": PayloadSchemaType.INTEGER,
        },
    },
    "photo_embeddings": {
        "vectors": VectorParams(size=512, distance=Distance.COSINE),
        "payload_indexes": {
            "workspace_id": PayloadSchemaType.KEYWORD,
            "photo_asset_id": PayloadSchemaType.KEYWORD,
            "taken_at": PayloadSchemaType.DATETIME,
        },
    },
    "face_embeddings": {
        "vectors": VectorParams(size=512, distance=Distance.COSINE),
        "payload_indexes": {
            # MANDATORY — workspace isolation is the #1 security control
            "workspace_id": PayloadSchemaType.KEYWORD,
            "photo_asset_id": PayloadSchemaType.KEYWORD,
            "face_detection_id": PayloadSchemaType.KEYWORD,
            "detector_version": PayloadSchemaType.KEYWORD,
        },
    },
}

# Collections that should be rebuilt (drop + recreate) if their payload
# indexes are missing the required fields. Only safe for collections that
# do not yet contain production data.
_REBUILD_IF_STALE = {"face_embeddings"}


async def _create_collection_with_indexes(client, name: str, spec: dict) -> None:
    """Create a collection and its payload indexes."""
    await client.create_collection(
        collection_name=name,
        vectors_config=spec["vectors"],
    )
    logger.info(
        "qdrant_collection_created",
        collection=name,
        vector_size=spec["vectors"].size,
    )

    for field, schema_type in spec["payload_indexes"].items():
        await client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=schema_type,
        )
    logger.info(
        "qdrant_indexes_created",
        collection=name,
        indexes=list(spec["payload_indexes"].keys()),
    )


async def _has_required_indexes(client, name: str, required: set[str]) -> bool:
    """Return True if the collection has all required payload indexes."""
    info = await client.get_collection(collection_name=name)
    existing_schema = info.payload_schema or {}
    existing_fields = set(existing_schema.keys())
    return required.issubset(existing_fields)


async def init_collections() -> None:
    """Create Qdrant collections if they don't exist. Rebuild stale ones.

    Idempotent: safe to re-run on every startup.
    """
    client = get_qdrant()
    existing = {c.name for c in (await client.get_collections()).collections}

    for name, spec in COLLECTIONS.items():
        required_indexes = set(spec["payload_indexes"].keys())

        if name not in existing:
            await _create_collection_with_indexes(client, name, spec)
            continue

        # Collection exists — check if its indexes match current spec
        if name in _REBUILD_IF_STALE:
            try:
                has_all = await _has_required_indexes(client, name, required_indexes)
            except Exception:
                logger.warning(
                    "qdrant_collection_index_check_failed",
                    collection=name,
                    exc_info=True,
                )
                has_all = False

            if not has_all:
                logger.info(
                    "qdrant_collection_rebuilding",
                    collection=name,
                    reason="missing_payload_indexes",
                )
                await client.delete_collection(collection_name=name)
                await _create_collection_with_indexes(client, name, spec)
                continue

        logger.info("qdrant_collection_exists", collection=name)

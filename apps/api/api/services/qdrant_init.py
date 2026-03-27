"""Idempotent Qdrant collection initialization.

Creates required vector collections on startup if they don't already exist.
Called from the FastAPI lifespan handler.
"""

import structlog
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    VectorParams,
)

from api.services.qdrant_client import get_qdrant

logger = structlog.get_logger()

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
            "workspace_id": PayloadSchemaType.KEYWORD,
            "face_detection_id": PayloadSchemaType.KEYWORD,
            "cluster_id": PayloadSchemaType.KEYWORD,
            "person_id": PayloadSchemaType.KEYWORD,
        },
    },
}


async def init_collections() -> None:
    """Create Qdrant collections if they don't exist. Idempotent."""
    client = get_qdrant()
    existing = {c.name for c in (await client.get_collections()).collections}

    for name, spec in COLLECTIONS.items():
        if name in existing:
            logger.info("qdrant_collection_exists", collection=name)
            continue

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

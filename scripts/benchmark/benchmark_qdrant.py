#!/usr/bin/env python3
"""Qdrant vector search latency benchmark (P50/P95, 1000 random vectors)."""

import json
import time
import uuid

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

ITERATIONS = 1000
VECTOR_DIM = 768
COLLECTION = "_bench_vectors"
QDRANT_URL = "http://localhost:6333"
QDRANT_API_KEY = "ekamcore_qdrant_dev"


def run() -> dict:
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Setup: create collection and insert vectors
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )

    # Insert 500 vectors for search targets
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=np.random.randn(VECTOR_DIM).tolist(),
            payload={"index": i},
        )
        for i in range(500)
    ]
    client.upsert(collection_name=COLLECTION, points=points)

    # Benchmark: search with random query vectors
    search_times: list[float] = []
    for _ in range(ITERATIONS):
        query_vector = np.random.randn(VECTOR_DIM).tolist()

        t0 = time.perf_counter()
        client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            limit=10,
        )
        search_times.append((time.perf_counter() - t0) * 1000)

    # Cleanup
    client.delete_collection(COLLECTION)

    s = np.array(search_times)

    result = {
        "benchmark": "qdrant",
        "iterations": ITERATIONS,
        "vector_dim": VECTOR_DIM,
        "corpus_size": 500,
        "metrics": {
            "search_p50_ms": round(float(np.percentile(s, 50)), 3),
            "search_p95_ms": round(float(np.percentile(s, 95)), 3),
            "search_p99_ms": round(float(np.percentile(s, 99)), 3),
        },
    }

    print(f"Qdrant ({ITERATIONS} searches, {VECTOR_DIM}d, 500 corpus):")
    print(f"  Search — P50: {result['metrics']['search_p50_ms']}ms  P95: {result['metrics']['search_p95_ms']}ms  P99: {result['metrics']['search_p99_ms']}ms")

    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

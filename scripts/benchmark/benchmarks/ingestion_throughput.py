"""Ingestion throughput benchmarks (G-06 / ART-16).

Measures text chunking, hashing, and embedding generation rates.
Uses local operations where possible; embedding requires Ollama running.
"""

from __future__ import annotations

import hashlib
import os
import time

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Suppress SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _bench_sha256_hash() -> float:
    """Time hashing a 100KB text block (simulates file fingerprinting)."""
    data = b"Lorem ipsum dolor sit amet. " * 4000  # ~100KB
    start = time.perf_counter()
    hashlib.sha256(data).hexdigest()
    return (time.perf_counter() - start) * 1000


def _bench_text_chunking() -> float:
    """Time splitting 10KB text into 512-char chunks."""
    text = "This is a test sentence for chunking. " * 300  # ~11KB
    chunk_size = 512
    start = time.perf_counter()
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    _ = len(chunks)
    return (time.perf_counter() - start) * 1000


def _bench_embedding_generation() -> float:
    """Time one embedding generation via Ollama (requires Ollama running)."""
    text = "This is a test sentence for embedding generation benchmark."
    start = time.perf_counter()
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": "nomic-embed-text", "input": text},
        timeout=10,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama embed returned {resp.status_code}")
    return elapsed_ms


def get_benchmarks() -> list[dict]:
    return [
        {
            "name": "ingestion/sha256_hash_100kb",
            "target_p50_ms": 1,
            "target_p95_ms": 5,
            "fn": _bench_sha256_hash,
        },
        {
            "name": "ingestion/text_chunking_10kb",
            "target_p50_ms": 1,
            "target_p95_ms": 5,
            "fn": _bench_text_chunking,
        },
        {
            "name": "ingestion/embedding_single_chunk",
            "target_p50_ms": 200,
            "target_p95_ms": 500,
            "fn": _bench_embedding_generation,
        },
    ]

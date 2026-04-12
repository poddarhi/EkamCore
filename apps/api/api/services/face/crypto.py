"""Application-side encryption for face embeddings (S11-001 / ART-11).

Uses Fernet (AES-128-CBC + HMAC-SHA256 + PKCS7 padding) from the
`cryptography` library for symmetric authenticated encryption.

Why Fernet and not pgcrypto's pgp_sym_encrypt?
  - Stateless: encryption happens in the API process, no DB round-trip per call
  - Well-audited: Fernet spec is minimal and widely reviewed
  - Simpler key management: one base64 key in env, no coupling to SQL layer
  - The BYTEA column still lives in the pgcrypto-enabled database;
    the ciphertext is opaque to Postgres, so the semantic is identical.

Key is loaded from settings.FACE_EMBED_KEY (env: FACE_EMBED_KEY).
Generate a fresh key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

SECURITY RULES (Golden Rule #4):
  - The key is NEVER logged.
  - Raw embeddings are NEVER returned from an API response.
  - Decryption failures are logged WITHOUT the ciphertext content.
"""

from __future__ import annotations

import struct
from typing import Sequence

import structlog
from cryptography.fernet import Fernet, InvalidToken

from api.config import settings
from api.errors import ServiceUnavailableError

logger = structlog.get_logger()

# Cached Fernet instance. Rebuilt only when the key changes (tests).
_cached_fernet: Fernet | None = None
_cached_key: str | None = None


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance built from settings.FACE_EMBED_KEY.

    Raises:
        ServiceUnavailableError: if FACE_EMBED_KEY is empty or malformed.
    """
    global _cached_fernet, _cached_key

    key = settings.FACE_EMBED_KEY
    if not key:
        raise ServiceUnavailableError(
            error_code="FACE_ENCRYPTION_KEY_MISSING",
            message=(
                "FACE_EMBED_KEY is not configured. Face pipeline cannot "
                "encrypt or decrypt embeddings."
            ),
        )

    if _cached_fernet is not None and _cached_key == key:
        return _cached_fernet

    try:
        # Fernet.__init__ accepts base64-encoded 32-byte keys as str or bytes
        fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError):
        # Don't log the key itself
        logger.error("face_encryption_key_invalid_format")
        raise ServiceUnavailableError(
            error_code="FACE_ENCRYPTION_KEY_INVALID",
            message=(
                "FACE_EMBED_KEY is not a valid Fernet key. "
                "Generate one with: python -c 'from cryptography.fernet "
                "import Fernet; print(Fernet.generate_key().decode())'"
            ),
        )

    _cached_fernet = fernet
    _cached_key = key
    return fernet


def _reset_cache() -> None:
    """Test helper: force rebuild of the Fernet cache on next call."""
    global _cached_fernet, _cached_key
    _cached_fernet = None
    _cached_key = None


def encrypt_embedding(vec: Sequence[float]) -> bytes:
    """Pack a float vector as little-endian float32 and encrypt with Fernet.

    Args:
        vec: Sequence of floats (e.g., a 512-dim ArcFace embedding).

    Returns:
        Opaque ciphertext bytes suitable for storage in a BYTEA column.

    Raises:
        ServiceUnavailableError: if FACE_EMBED_KEY is missing or invalid.
    """
    fernet = _get_fernet()
    # Pack as little-endian float32 array: "<{n}f"
    packed = struct.pack(f"<{len(vec)}f", *vec)
    return fernet.encrypt(packed)


def decrypt_embedding(blob: bytes) -> list[float]:
    """Decrypt and unpack an embedding previously produced by encrypt_embedding.

    Args:
        blob: Ciphertext bytes from a BYTEA column.

    Returns:
        List of floats (length = original vector length).

    Raises:
        ServiceUnavailableError: if FACE_EMBED_KEY is missing, invalid, or
            the ciphertext fails authentication (wrong key or tampered).
    """
    fernet = _get_fernet()
    try:
        packed = fernet.decrypt(blob)
    except InvalidToken:
        logger.warning("face_embedding_decrypt_failed", reason="invalid_token")
        raise ServiceUnavailableError(
            error_code="FACE_EMBEDDING_DECRYPT_FAILED",
            message=(
                "Face embedding could not be decrypted. "
                "Key may have changed or ciphertext was tampered with."
            ),
        )

    # Unpack as little-endian float32: length must be a multiple of 4
    if len(packed) % 4 != 0:
        logger.error("face_embedding_length_invalid", length=len(packed))
        raise ServiceUnavailableError(
            error_code="FACE_EMBEDDING_CORRUPT",
            message="Decrypted embedding has invalid length.",
        )

    count = len(packed) // 4
    return list(struct.unpack(f"<{count}f", packed))

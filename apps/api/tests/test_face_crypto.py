"""Tests for face embedding encryption (S11-001)."""

from __future__ import annotations

import struct
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from api.errors import ServiceUnavailableError
from api.services.face import crypto


@pytest.fixture(autouse=True)
def _reset_crypto_cache():
    """Ensure each test starts with a fresh Fernet cache."""
    crypto._reset_cache()
    yield
    crypto._reset_cache()


@pytest.fixture
def test_key() -> str:
    """A fresh Fernet key for each test."""
    return Fernet.generate_key().decode()


@pytest.fixture
def sample_embedding() -> list[float]:
    """A 512-dim vector with varied values near float32 representable range."""
    return [float(i) * 0.001 - 0.25 for i in range(512)]


class TestEncryptDecryptRoundTrip:
    def test_roundtrip_preserves_float32_values(self, test_key, sample_embedding):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            ciphertext = crypto.encrypt_embedding(sample_embedding)
            plaintext = crypto.decrypt_embedding(ciphertext)

        assert len(plaintext) == len(sample_embedding)
        for original, recovered in zip(sample_embedding, plaintext):
            # float32 precision: ~1e-7 relative, but our values are small
            # so we use absolute tolerance
            assert abs(original - recovered) < 1e-5

    def test_ciphertext_is_opaque_bytes(self, test_key, sample_embedding):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            ciphertext = crypto.encrypt_embedding(sample_embedding)

        assert isinstance(ciphertext, bytes)
        # Fernet tokens are base64 URL-safe and substantially longer than plain
        assert len(ciphertext) > len(sample_embedding) * 4

    def test_small_vector_roundtrip(self, test_key):
        vec = [1.0, 2.5, -3.14, 0.0]
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            blob = crypto.encrypt_embedding(vec)
            out = crypto.decrypt_embedding(blob)
        assert len(out) == 4
        for a, b in zip(vec, out):
            assert abs(a - b) < 1e-6

    def test_empty_vector_roundtrip(self, test_key):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            blob = crypto.encrypt_embedding([])
            out = crypto.decrypt_embedding(blob)
        assert out == []

    def test_different_ciphertexts_for_same_input(self, test_key, sample_embedding):
        """Fernet uses a random IV, so two encrypts of the same input differ."""
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            c1 = crypto.encrypt_embedding(sample_embedding)
            c2 = crypto.encrypt_embedding(sample_embedding)
        assert c1 != c2
        # But both decrypt to the same plaintext
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            p1 = crypto.decrypt_embedding(c1)
            p2 = crypto.decrypt_embedding(c2)
        assert p1 == p2


class TestKeyErrors:
    def test_missing_key_raises_on_encrypt(self, sample_embedding):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", ""):
            crypto._reset_cache()
            with pytest.raises(ServiceUnavailableError) as exc_info:
                crypto.encrypt_embedding(sample_embedding)
        assert exc_info.value.error_code == "FACE_ENCRYPTION_KEY_MISSING"

    def test_missing_key_raises_on_decrypt(self):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", ""):
            crypto._reset_cache()
            with pytest.raises(ServiceUnavailableError) as exc_info:
                crypto.decrypt_embedding(b"any bytes")
        assert exc_info.value.error_code == "FACE_ENCRYPTION_KEY_MISSING"

    def test_invalid_key_format_raises(self, sample_embedding):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", "not-a-real-fernet-key"):
            crypto._reset_cache()
            with pytest.raises(ServiceUnavailableError) as exc_info:
                crypto.encrypt_embedding(sample_embedding)
        assert exc_info.value.error_code == "FACE_ENCRYPTION_KEY_INVALID"


class TestKeyRotation:
    def test_wrong_key_fails_authentication(self, sample_embedding):
        key_a = Fernet.generate_key().decode()
        key_b = Fernet.generate_key().decode()

        # Encrypt with key A
        with patch.object(crypto.settings, "FACE_EMBED_KEY", key_a):
            crypto._reset_cache()
            ciphertext = crypto.encrypt_embedding(sample_embedding)

        # Try to decrypt with key B
        with patch.object(crypto.settings, "FACE_EMBED_KEY", key_b):
            crypto._reset_cache()
            with pytest.raises(ServiceUnavailableError) as exc_info:
                crypto.decrypt_embedding(ciphertext)
        assert exc_info.value.error_code == "FACE_EMBEDDING_DECRYPT_FAILED"

    def test_tampered_ciphertext_fails(self, test_key, sample_embedding):
        with patch.object(crypto.settings, "FACE_EMBED_KEY", test_key):
            crypto._reset_cache()
            ciphertext = crypto.encrypt_embedding(sample_embedding)
            # Flip a byte in the middle of the ciphertext
            tampered = bytearray(ciphertext)
            mid = len(tampered) // 2
            tampered[mid] ^= 0x01
            with pytest.raises(ServiceUnavailableError) as exc_info:
                crypto.decrypt_embedding(bytes(tampered))
        assert exc_info.value.error_code == "FACE_EMBEDDING_DECRYPT_FAILED"


class TestPackingFormat:
    def test_packed_format_is_little_endian_float32(self, test_key):
        """Sanity check: the unencrypted packed form is <f32."""
        vec = [1.5, -2.25, 3.75]
        packed = struct.pack(f"<{len(vec)}f", *vec)
        unpacked = struct.unpack(f"<{len(vec)}f", packed)
        for a, b in zip(vec, unpacked):
            assert abs(a - b) < 1e-6

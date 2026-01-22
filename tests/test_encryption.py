"""Tests for encryption utilities."""

import pytest

from gmail_mcp.utils.encryption import (
    decrypt_data,
    encrypt_data,
    generate_key,
    key_from_hex,
)
from gmail_mcp.utils.errors import TokenError, ValidationError


class TestGenerateKey:
    """Tests for generate_key function."""

    def test_generates_32_byte_key(self) -> None:
        """Key should be 32 bytes (256 bits)."""
        key = generate_key()
        assert len(key) == 32

    def test_generates_unique_keys(self) -> None:
        """Each call should generate a unique key."""
        keys = [generate_key() for _ in range(10)]
        # All keys should be unique
        assert len(set(keys)) == 10


class TestKeyFromHex:
    """Tests for key_from_hex function."""

    def test_converts_valid_hex_to_bytes(self) -> None:
        """Valid 64-char hex should convert to 32-byte key."""
        hex_key = "a" * 64
        key = key_from_hex(hex_key)
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_strips_whitespace(self) -> None:
        """Should strip leading/trailing whitespace."""
        hex_key = "  " + "b" * 64 + "  \n"
        key = key_from_hex(hex_key)
        assert len(key) == 32

    def test_raises_on_invalid_length(self) -> None:
        """Should raise ValidationError for wrong length hex string."""
        with pytest.raises(ValidationError) as exc_info:
            key_from_hex("ab" * 16)  # 32 chars, not 64
        assert "64" in str(exc_info.value)

    def test_raises_on_invalid_hex_chars(self) -> None:
        """Should raise ValidationError for non-hex characters."""
        with pytest.raises(ValidationError) as exc_info:
            key_from_hex("g" * 64)  # 'g' is not hex
        assert "hex" in str(exc_info.value).lower()


class TestEncryptDecrypt:
    """Tests for encrypt_data and decrypt_data functions."""

    @pytest.fixture
    def key(self) -> bytes:
        """Generate a test encryption key."""
        return generate_key()

    def test_encrypt_returns_iv_and_ciphertext(self, key: bytes) -> None:
        """Encrypted result should contain iv and ciphertext."""
        plaintext = b"Hello, World!"
        result = encrypt_data(plaintext, key)

        assert "iv" in result
        assert "ciphertext" in result
        assert len(result["iv"]) == 12  # 96-bit IV
        assert len(result["ciphertext"]) > len(plaintext)  # Includes auth tag

    def test_decrypt_recovers_plaintext(self, key: bytes) -> None:
        """Decryption should recover original plaintext."""
        plaintext = b"Secret message for testing"
        encrypted = encrypt_data(plaintext, key)

        decrypted = decrypt_data(encrypted["iv"], encrypted["ciphertext"], key)
        assert decrypted == plaintext

    def test_roundtrip_with_empty_data(self, key: bytes) -> None:
        """Should handle empty plaintext."""
        plaintext = b""
        encrypted = encrypt_data(plaintext, key)
        decrypted = decrypt_data(encrypted["iv"], encrypted["ciphertext"], key)
        assert decrypted == plaintext

    def test_roundtrip_with_large_data(self, key: bytes) -> None:
        """Should handle large data."""
        plaintext = b"x" * 100000  # 100KB
        encrypted = encrypt_data(plaintext, key)
        decrypted = decrypt_data(encrypted["iv"], encrypted["ciphertext"], key)
        assert decrypted == plaintext

    def test_roundtrip_with_unicode(self, key: bytes) -> None:
        """Should handle unicode when encoded."""
        plaintext = "Hello, 世界! 🔐".encode()
        encrypted = encrypt_data(plaintext, key)
        decrypted = decrypt_data(encrypted["iv"], encrypted["ciphertext"], key)
        assert decrypted == plaintext

    def test_unique_iv_per_encryption(self, key: bytes) -> None:
        """Each encryption should use a unique IV."""
        plaintext = b"Same message"
        encryptions = [encrypt_data(plaintext, key) for _ in range(10)]
        ivs = [e["iv"] for e in encryptions]
        # All IVs should be unique
        assert len(set(ivs)) == 10

    def test_same_plaintext_produces_different_ciphertext(self, key: bytes) -> None:
        """Same plaintext should produce different ciphertext due to unique IV."""
        plaintext = b"Same message"
        encryptions = [encrypt_data(plaintext, key) for _ in range(10)]
        ciphertexts = [e["ciphertext"] for e in encryptions]
        # All ciphertexts should be unique
        assert len(set(ciphertexts)) == 10

    def test_decrypt_with_wrong_key_fails(self, key: bytes) -> None:
        """Decryption with wrong key should fail."""
        plaintext = b"Secret"
        encrypted = encrypt_data(plaintext, key)

        wrong_key = generate_key()
        with pytest.raises(TokenError) as exc_info:
            decrypt_data(encrypted["iv"], encrypted["ciphertext"], wrong_key)
        assert "decrypt" in str(exc_info.value).lower()

    def test_decrypt_with_tampered_ciphertext_fails(self, key: bytes) -> None:
        """Decryption with tampered ciphertext should fail (auth tag check)."""
        plaintext = b"Secret"
        encrypted = encrypt_data(plaintext, key)

        # Tamper with ciphertext
        tampered = bytearray(encrypted["ciphertext"])
        tampered[0] ^= 0xFF  # Flip bits

        with pytest.raises(TokenError) as exc_info:
            decrypt_data(encrypted["iv"], bytes(tampered), key)
        assert "decrypt" in str(exc_info.value).lower()

    def test_decrypt_with_wrong_iv_fails(self, key: bytes) -> None:
        """Decryption with wrong IV should fail."""
        plaintext = b"Secret"
        encrypted = encrypt_data(plaintext, key)

        import os

        wrong_iv = os.urandom(12)

        with pytest.raises(TokenError) as exc_info:
            decrypt_data(wrong_iv, encrypted["ciphertext"], key)
        assert "decrypt" in str(exc_info.value).lower()


class TestEncryptionValidation:
    """Tests for input validation in encryption functions."""

    def test_encrypt_with_invalid_key_length(self) -> None:
        """Should raise ValidationError for invalid key length."""
        short_key = b"short"
        with pytest.raises(ValidationError) as exc_info:
            encrypt_data(b"data", short_key)
        assert "32" in str(exc_info.value)

    def test_decrypt_with_invalid_key_length(self) -> None:
        """Should raise ValidationError for invalid key length."""
        short_key = b"short"
        with pytest.raises(ValidationError) as exc_info:
            decrypt_data(b"iv" * 6, b"ciphertext", short_key)
        assert "32" in str(exc_info.value)

    def test_decrypt_with_invalid_iv_length(self) -> None:
        """Should raise ValidationError for invalid IV length."""
        key = generate_key()
        with pytest.raises(ValidationError) as exc_info:
            decrypt_data(b"short", b"ciphertext", key)
        assert "12" in str(exc_info.value)

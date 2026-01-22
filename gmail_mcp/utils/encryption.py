"""AES-256-GCM encryption utilities for secure token storage.

This module provides cryptographic functions for encrypting and decrypting
sensitive data (primarily OAuth tokens) using AES-256-GCM authenticated
encryption. GCM mode provides both confidentiality and integrity protection.

Security considerations:
- Keys must be 256 bits (32 bytes) for AES-256
- IVs are 96 bits (12 bytes) and must be unique per encryption
- Never reuse an IV with the same key
- Store keys securely (environment variables, secrets manager)
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from gmail_mcp.utils.errors import TokenError, ValidationError

# Constants
KEY_SIZE_BITS = 256
KEY_SIZE_BYTES = KEY_SIZE_BITS // 8  # 32 bytes
IV_SIZE_BYTES = 12  # 96 bits, recommended for GCM
HEX_KEY_LENGTH = KEY_SIZE_BYTES * 2  # 64 hex characters


def generate_key() -> bytes:
    """Generate a cryptographically secure 256-bit encryption key.

    Uses the cryptography library's AESGCM.generate_key() which internally
    uses os.urandom() for secure random number generation.

    Returns:
        A 32-byte (256-bit) key suitable for AES-256-GCM encryption.

    Example:
        >>> key = generate_key()
        >>> len(key)
        32
        >>> key.hex()  # 64-character hex string
        'a1b2c3d4...'
    """
    return AESGCM.generate_key(bit_length=KEY_SIZE_BITS)


def encrypt_data(plaintext: bytes, key: bytes) -> dict[str, bytes]:
    """Encrypt data using AES-256-GCM authenticated encryption.

    Generates a unique 12-byte IV for each encryption operation to ensure
    security. The IV must be stored alongside the ciphertext for decryption.

    Args:
        plaintext: The data to encrypt.
        key: A 32-byte (256-bit) encryption key.

    Returns:
        A dictionary containing:
            - "iv": The 12-byte initialization vector (nonce)
            - "ciphertext": The encrypted data with authentication tag

    Raises:
        ValidationError: If the key is not exactly 32 bytes.
        TokenError: If encryption fails for any reason.

    Example:
        >>> key = generate_key()
        >>> data = b"secret token data"
        >>> encrypted = encrypt_data(data, key)
        >>> encrypted.keys()
        dict_keys(['iv', 'ciphertext'])
    """
    _validate_key(key)

    try:
        iv = os.urandom(IV_SIZE_BYTES)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        return {"iv": iv, "ciphertext": ciphertext}
    except Exception as e:
        raise TokenError(
            "Failed to encrypt data",
            details={"error_type": type(e).__name__, "error_message": str(e)},
        ) from e


def decrypt_data(iv: bytes, ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt data using AES-256-GCM authenticated decryption.

    Decrypts and verifies the authentication tag in a single operation.
    If the ciphertext has been tampered with, decryption will fail.

    Args:
        iv: The 12-byte initialization vector used during encryption.
        ciphertext: The encrypted data with authentication tag.
        key: The 32-byte (256-bit) encryption key used for encryption.

    Returns:
        The decrypted plaintext data.

    Raises:
        ValidationError: If the key or IV has invalid length.
        TokenError: If decryption fails (invalid key, corrupted data, or
            tampered ciphertext).

    Example:
        >>> key = generate_key()
        >>> data = b"secret token data"
        >>> encrypted = encrypt_data(data, key)
        >>> decrypted = decrypt_data(encrypted["iv"], encrypted["ciphertext"], key)
        >>> decrypted == data
        True
    """
    _validate_key(key)
    _validate_iv(iv)

    try:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(iv, ciphertext, None)
    except Exception as e:
        raise TokenError(
            "Failed to decrypt data - invalid key or corrupted ciphertext",
            details={"error_type": type(e).__name__, "error_message": str(e)},
        ) from e


def key_from_hex(hex_key: str) -> bytes:
    """Convert a hexadecimal string to an encryption key.

    This function is useful for loading keys from environment variables
    or configuration files where they are stored as hex strings.

    Args:
        hex_key: A 64-character hexadecimal string representing a 256-bit key.

    Returns:
        A 32-byte encryption key.

    Raises:
        ValidationError: If the hex string is not exactly 64 characters or
            contains invalid hex characters.

    Example:
        >>> hex_str = "a" * 64  # 64 hex characters
        >>> key = key_from_hex(hex_str)
        >>> len(key)
        32
    """
    # Strip whitespace for convenience
    hex_key = hex_key.strip()

    if len(hex_key) != HEX_KEY_LENGTH:
        raise ValidationError(
            f"Invalid hex key length: expected {HEX_KEY_LENGTH} characters, "
            f"got {len(hex_key)}",
            field="hex_key",
            details={"expected_length": HEX_KEY_LENGTH, "actual_length": len(hex_key)},
        )

    try:
        return bytes.fromhex(hex_key)
    except ValueError as e:
        raise ValidationError(
            "Invalid hex key: contains non-hexadecimal characters",
            field="hex_key",
            details={"error_message": str(e)},
        ) from e


def _validate_key(key: bytes) -> None:
    """Validate that the key is the correct length for AES-256.

    Args:
        key: The encryption key to validate.

    Raises:
        ValidationError: If the key is not exactly 32 bytes.
    """
    if len(key) != KEY_SIZE_BYTES:
        raise ValidationError(
            f"Invalid key length: expected {KEY_SIZE_BYTES} bytes, got {len(key)}",
            field="key",
            details={"expected_length": KEY_SIZE_BYTES, "actual_length": len(key)},
        )


def _validate_iv(iv: bytes) -> None:
    """Validate that the IV is the correct length for GCM.

    Args:
        iv: The initialization vector to validate.

    Raises:
        ValidationError: If the IV is not exactly 12 bytes.
    """
    if len(iv) != IV_SIZE_BYTES:
        raise ValidationError(
            f"Invalid IV length: expected {IV_SIZE_BYTES} bytes, got {len(iv)}",
            field="iv",
            details={"expected_length": IV_SIZE_BYTES, "actual_length": len(iv)},
        )


__all__ = [
    "generate_key",
    "encrypt_data",
    "decrypt_data",
    "key_from_hex",
]

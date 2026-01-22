"""Token encryption utilities for secure OAuth token storage.

This module provides functions for encrypting and decrypting OAuth tokens
using AES-256-GCM authenticated encryption. Tokens are serialized as JSON
and encrypted before storage.

Security considerations:
- Encryption key must be set via TOKEN_ENCRYPTION_KEY environment variable
- Key must be a 64-character hex string (256 bits)
- Each encryption generates a unique IV to prevent replay attacks
"""

from __future__ import annotations

import json
import logging
import os

from gmail_mcp.utils.encryption import decrypt_data, encrypt_data, key_from_hex
from gmail_mcp.utils.errors import TokenError

logger = logging.getLogger(__name__)


def get_encryption_key() -> bytes:
    """Get encryption key from environment variable.

    Retrieves and validates the TOKEN_ENCRYPTION_KEY environment variable,
    converting it from a 64-character hex string to a 32-byte key.

    Returns:
        A 32-byte (256-bit) encryption key.

    Raises:
        TokenError: If TOKEN_ENCRYPTION_KEY is not set or invalid.

    Example:
        >>> os.environ["TOKEN_ENCRYPTION_KEY"] = "a" * 64
        >>> key = get_encryption_key()
        >>> len(key)
        32
    """
    hex_key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not hex_key:
        logger.error("TOKEN_ENCRYPTION_KEY environment variable not set")
        raise TokenError(
            "TOKEN_ENCRYPTION_KEY environment variable not set",
            details={"hint": "Set TOKEN_ENCRYPTION_KEY to a 64-character hex string"},
        )

    try:
        return key_from_hex(hex_key)
    except Exception as e:
        logger.error("Invalid TOKEN_ENCRYPTION_KEY: %s", e)
        raise TokenError(
            "Invalid TOKEN_ENCRYPTION_KEY format",
            details={"error": str(e)},
        ) from e


def encrypt_token(token_data: dict[str, object]) -> dict[str, str]:
    """Encrypt token data for secure storage.

    Serializes the token data as JSON, encrypts it using AES-256-GCM,
    and returns the IV and ciphertext as hex strings for easy storage.

    Args:
        token_data: Dictionary containing OAuth token fields
            (access_token, refresh_token, etc.).

    Returns:
        A dictionary containing:
            - "iv": Hex-encoded initialization vector
            - "ciphertext": Hex-encoded encrypted token data

    Raises:
        TokenError: If encryption fails or key is unavailable.

    Example:
        >>> token = {"access_token": "ya29...", "refresh_token": "1//..."}
        >>> encrypted = encrypt_token(token)
        >>> encrypted.keys()
        dict_keys(['iv', 'ciphertext'])
    """
    key = get_encryption_key()

    try:
        plaintext = json.dumps(token_data).encode("utf-8")
        encrypted = encrypt_data(plaintext, key)

        result = {
            "iv": encrypted["iv"].hex(),
            "ciphertext": encrypted["ciphertext"].hex(),
        }
        logger.debug("Token encrypted successfully")
        return result

    except TokenError:
        raise
    except Exception as e:
        logger.error("Failed to encrypt token: %s", e)
        raise TokenError(
            "Failed to encrypt token data",
            details={"error_type": type(e).__name__, "error_message": str(e)},
        ) from e


def decrypt_token(encrypted: dict[str, str]) -> dict[str, object]:
    """Decrypt token data from encrypted storage format.

    Takes hex-encoded IV and ciphertext, decrypts using AES-256-GCM,
    and deserializes the JSON token data.

    Args:
        encrypted: Dictionary containing:
            - "iv": Hex-encoded initialization vector
            - "ciphertext": Hex-encoded encrypted token data

    Returns:
        The decrypted token data dictionary.

    Raises:
        TokenError: If decryption fails, data is corrupted, or key is invalid.

    Example:
        >>> encrypted = encrypt_token({"access_token": "ya29..."})
        >>> token = decrypt_token(encrypted)
        >>> token["access_token"]
        'ya29...'
    """
    key = get_encryption_key()

    try:
        iv = bytes.fromhex(encrypted["iv"])
        ciphertext = bytes.fromhex(encrypted["ciphertext"])

        plaintext = decrypt_data(iv, ciphertext, key)
        token_data: dict[str, object] = json.loads(plaintext.decode("utf-8"))

        logger.debug("Token decrypted successfully")
        return token_data

    except KeyError as e:
        logger.error("Missing required field in encrypted data: %s", e)
        raise TokenError(
            "Invalid encrypted token format - missing required field",
            details={"missing_field": str(e)},
        ) from e
    except ValueError as e:
        logger.error("Invalid hex encoding in encrypted data: %s", e)
        raise TokenError(
            "Invalid encrypted token format - invalid hex encoding",
            details={"error_message": str(e)},
        ) from e
    except json.JSONDecodeError as e:
        logger.error("Failed to parse decrypted token as JSON: %s", e)
        raise TokenError(
            "Decrypted data is not valid JSON",
            details={"error_message": str(e)},
        ) from e
    except TokenError:
        raise
    except Exception as e:
        logger.error("Failed to decrypt token: %s", e)
        raise TokenError(
            "Failed to decrypt token data",
            details={"error_type": type(e).__name__, "error_message": str(e)},
        ) from e


__all__ = [
    "get_encryption_key",
    "encrypt_token",
    "decrypt_token",
]

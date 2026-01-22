"""Secure token storage with file-based persistence.

This module provides encrypted file-based storage for OAuth tokens.
Tokens are encrypted using AES-256-GCM before being written to disk,
and file permissions are restricted to owner-only access.

Storage location: ~/.gmail-mcp/tokens/{user_id}.token.enc

Security considerations:
- Tokens are encrypted at rest using AES-256-GCM
- File permissions are set to 0600 (owner read/write only)
- User IDs are sanitized to prevent path traversal attacks
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from gmail_mcp.auth.tokens import decrypt_token, encrypt_token
from gmail_mcp.utils.errors import TokenError

logger = logging.getLogger(__name__)


class TokenStorage:
    """File-based encrypted token storage.

    Stores OAuth tokens encrypted at rest in user-specific files.
    Each token file is encrypted with AES-256-GCM and has restricted
    file permissions.

    Attributes:
        _base_dir: Directory where encrypted token files are stored.

    Example:
        >>> storage = TokenStorage()
        >>> storage.save("user@example.com", {"access_token": "ya29..."})
        >>> token = storage.load("user@example.com")
        >>> token["access_token"]
        'ya29...'
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize token storage with optional custom directory.

        Args:
            base_dir: Directory for storing token files. If not provided,
                defaults to ~/.gmail-mcp/tokens/
        """
        if base_dir is None:
            base_dir = Path.home() / ".gmail-mcp" / "tokens"

        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.info("TokenStorage initialized at %s", self._base_dir)

    def _token_path(self, user_id: str) -> Path:
        """Get the file path for a user's encrypted token.

        Sanitizes the user_id to prevent path traversal attacks by
        only allowing alphanumeric characters, hyphens, underscores,
        and periods (for email addresses).

        Args:
            user_id: User identifier (typically email address).

        Returns:
            Path to the user's encrypted token file.
        """
        # Sanitize user_id to prevent path traversal
        # Allow alphanumeric, hyphen, underscore, dot, and @ for email addresses
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_.@")

        # Additional safety: replace @ with _at_ to avoid confusion
        safe_id = safe_id.replace("@", "_at_")

        if not safe_id:
            raise TokenError(
                "Invalid user_id - contains no valid characters",
                details={"original_user_id": user_id[:50]},  # Truncate for safety
            )

        return self._base_dir / f"{safe_id}.token.enc"

    def save(self, user_id: str, token_data: dict[str, object]) -> None:
        """Save encrypted token for a user.

        Encrypts the token data and writes it to a file with restricted
        permissions (owner read/write only).

        Args:
            user_id: User identifier (typically email address).
            token_data: Dictionary containing OAuth token fields.

        Raises:
            TokenError: If encryption or file writing fails.
        """
        path = self._token_path(user_id)

        try:
            encrypted = encrypt_token(token_data)
            path.write_text(json.dumps(encrypted, indent=2))

            # Restrict permissions to owner read/write only (0600)
            path.chmod(0o600)

            logger.info("Saved encrypted token for user %s", user_id)

        except TokenError:
            raise
        except PermissionError as e:
            logger.error("Permission denied writing token file: %s", e)
            raise TokenError(
                "Permission denied writing token file",
                details={"path": str(path), "error": str(e)},
            ) from e
        except Exception as e:
            logger.error("Failed to save token for %s: %s", user_id, e)
            raise TokenError(
                f"Failed to save token: {e}",
                details={"user_id": user_id, "error_type": type(e).__name__},
            ) from e

    def load(self, user_id: str) -> dict[str, object] | None:
        """Load and decrypt token for a user.

        Args:
            user_id: User identifier (typically email address).

        Returns:
            The decrypted token data dictionary, or None if no token exists.

        Raises:
            TokenError: If decryption or file reading fails (but not if
                the file simply doesn't exist).
        """
        path = self._token_path(user_id)

        if not path.exists():
            logger.debug("No token found for user %s", user_id)
            return None

        try:
            encrypted = json.loads(path.read_text())
            token_data = decrypt_token(encrypted)
            logger.debug("Loaded token for user %s", user_id)
            return token_data

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in token file for %s: %s", user_id, e)
            raise TokenError(
                "Token file contains invalid JSON",
                details={"user_id": user_id, "error": str(e)},
            ) from e
        except TokenError:
            raise
        except Exception as e:
            logger.error("Failed to load token for %s: %s", user_id, e)
            raise TokenError(
                f"Failed to load token: {e}",
                details={"user_id": user_id, "error_type": type(e).__name__},
            ) from e

    def delete(self, user_id: str) -> bool:
        """Delete token for a user.

        Args:
            user_id: User identifier (typically email address).

        Returns:
            True if a token was deleted, False if no token existed.

        Raises:
            TokenError: If file deletion fails due to permissions.
        """
        path = self._token_path(user_id)

        if not path.exists():
            logger.debug("No token to delete for user %s", user_id)
            return False

        try:
            path.unlink()
            logger.info("Deleted token for user %s", user_id)
            return True

        except PermissionError as e:
            logger.error("Permission denied deleting token file: %s", e)
            raise TokenError(
                "Permission denied deleting token file",
                details={"path": str(path), "error": str(e)},
            ) from e
        except Exception as e:
            logger.error("Failed to delete token for %s: %s", user_id, e)
            raise TokenError(
                f"Failed to delete token: {e}",
                details={"user_id": user_id, "error_type": type(e).__name__},
            ) from e

    def exists(self, user_id: str) -> bool:
        """Check if a token exists for a user.

        Args:
            user_id: User identifier (typically email address).

        Returns:
            True if a token file exists, False otherwise.
        """
        return self._token_path(user_id).exists()

    def list_users(self) -> list[str]:
        """List all users with stored tokens.

        Returns:
            List of user IDs that have stored tokens.
        """
        users = []
        for path in self._base_dir.glob("*.token.enc"):
            # Reverse the sanitization to get approximate user_id
            user_id = path.stem.replace("_at_", "@")
            users.append(user_id)
        return users


# Global singleton instance
token_storage = TokenStorage()


__all__ = [
    "TokenStorage",
    "token_storage",
]

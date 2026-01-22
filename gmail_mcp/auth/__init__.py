"""Authentication module for Gmail MCP server.

This module provides OAuth 2.0 authentication for the Gmail API, including:

- Token encryption/decryption for secure storage (AES-256-GCM)
- File-based encrypted token persistence
- OAuth flows: local server (desktop) and device flow (mobile/headless)
- Credential management and token refresh

Usage:
    >>> from gmail_mcp.auth import oauth_manager, token_storage
    >>>
    >>> # Authenticate user (opens browser)
    >>> token_data = oauth_manager.run_local_server()
    >>>
    >>> # Store tokens securely
    >>> token_storage.save("user@example.com", token_data)
    >>>
    >>> # Later, load and use tokens
    >>> token_data = token_storage.load("user@example.com")
    >>> credentials = oauth_manager.get_credentials(token_data)
"""

from gmail_mcp.auth.oauth import (
    GMAIL_SCOPES,
    GOOGLE_AUTH_URI,
    GOOGLE_DEVICE_AUTH_URI,
    GOOGLE_TOKEN_URI,
    OAuthManager,
    oauth_manager,
)
from gmail_mcp.auth.storage import TokenStorage, token_storage
from gmail_mcp.auth.tokens import decrypt_token, encrypt_token, get_encryption_key

__all__ = [
    # OAuth
    "OAuthManager",
    "oauth_manager",
    "GMAIL_SCOPES",
    "GOOGLE_AUTH_URI",
    "GOOGLE_TOKEN_URI",
    "GOOGLE_DEVICE_AUTH_URI",
    # Token Storage
    "TokenStorage",
    "token_storage",
    # Token Encryption
    "encrypt_token",
    "decrypt_token",
    "get_encryption_key",
]

"""Utility functions and helpers for Gmail MCP Server.

This module provides common utilities including custom exceptions,
encryption helpers, and other shared functionality.
"""

from gmail_mcp.utils.encryption import (
    decrypt_data,
    encrypt_data,
    generate_key,
    key_from_hex,
)
from gmail_mcp.utils.errors import (
    ApprovalError,
    AuthenticationError,
    GmailAPIError,
    GmailMCPError,
    RateLimitError,
    TokenError,
    ValidationError,
)

__all__ = [
    # Encryption utilities
    "generate_key",
    "encrypt_data",
    "decrypt_data",
    "key_from_hex",
    # Exception hierarchy
    "GmailMCPError",
    "AuthenticationError",
    "TokenError",
    "ApprovalError",
    "RateLimitError",
    "GmailAPIError",
    "ValidationError",
]

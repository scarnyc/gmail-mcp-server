"""Gmail auth status tool - Check authentication state.

This tool checks whether the user is authenticated and returns
their email address, current mode, and scope information.
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.auth.oauth import get_gmail_scopes, is_read_only, scope_labels
from gmail_mcp.auth.storage import token_storage
from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.tools.base import build_error_response, build_success_response
from gmail_mcp.utils.errors import AuthenticationError

logger = logging.getLogger(__name__)


async def gmail_get_auth_status() -> dict[str, Any]:
    """Check if the user is authenticated with Gmail.

    Returns the authentication status, user email, server mode,
    and scope information (expected vs stored token scopes).

    Returns:
        Success response with authentication status:
        - authenticated: True/False
        - email: User's email if authenticated, None otherwise
        - mode: "read_only" or "full_access"
        - expected_scopes: Scopes the current mode expects
        - token_scopes: Scopes stored in the token (if authenticated)
        - scope_mismatch: True if token scopes don't match expected
    """
    user_id = "default"  # Single-user mode
    read_only = is_read_only()
    mode = "read_only" if read_only else "full_access"
    expected_scopes = get_gmail_scopes()

    # Check if credentials exist
    if not gmail_client.is_authenticated(user_id):
        return build_success_response(
            data={
                "authenticated": False,
                "email": None,
                "mode": mode,
                "expected_scopes": scope_labels(expected_scopes),
            },
            message="Not authenticated. Use gmail_login to sign in.",
        )

    # Safe defaults in case token loading fails
    token_scopes: list[str] = []
    scope_mismatch = False

    try:
        # Load stored token to check scopes
        token_data = token_storage.load(user_id)
        if token_data:
            raw_scopes = token_data.get("scopes")
            if isinstance(raw_scopes, list):
                token_scopes = [str(s) for s in raw_scopes]

        # Order-independent comparison — Google doesn't guarantee scope order
        scope_mismatch = set(token_scopes) != set(expected_scopes)

        # Try to get service and fetch profile to verify credentials work
        service = gmail_client.get_service(user_id)
        profile = service.users().getProfile(userId="me").execute()
        user_email = profile["emailAddress"]

        message = f"Authenticated as {user_email}"
        if scope_mismatch:
            message += (
                ". WARNING: Token scopes do not match current mode. "
                "Run gmail_login to re-authenticate with correct scopes."
            )

        return build_success_response(
            data={
                "authenticated": True,
                "email": user_email,
                "mode": mode,
                "expected_scopes": scope_labels(expected_scopes),
                "token_scopes": scope_labels(token_scopes),
                "scope_mismatch": scope_mismatch,
            },
            message=message,
        )

    except AuthenticationError as e:
        # Credentials exist but are invalid/expired
        logger.warning("Stored credentials are invalid: %s", e)
        return build_success_response(
            data={
                "authenticated": False,
                "email": None,
                "mode": mode,
                "expected_scopes": scope_labels(expected_scopes),
                "token_scopes": scope_labels(token_scopes),
                "scope_mismatch": scope_mismatch,
            },
            message=(
                "Credentials are invalid or expired. "
                "Use gmail_login to re-authenticate."
            ),
        )
    except Exception as e:
        logger.error("Error checking auth status: %s", e)
        return build_error_response(
            error=f"Failed to check authentication status: {e}",
            error_code="StatusCheckError",
        )

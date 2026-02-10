"""Gmail logout tool - Clear stored credentials.

This tool removes stored OAuth tokens and invalidates any cached
Gmail API service instances.
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.auth.oauth import oauth_manager
from gmail_mcp.auth.storage import token_storage
from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.tools.base import build_success_response
from gmail_mcp.utils.errors import TokenError

logger = logging.getLogger(__name__)


async def gmail_logout() -> dict[str, Any]:
    """Sign out of Gmail by clearing stored credentials.

    Removes the stored OAuth token and invalidates any cached Gmail API
    service. The user will need to re-authenticate using gmail_login
    to use other Gmail tools.

    Returns:
        Success response with logout confirmation.
    """
    user_id = "default"  # Single-user mode

    # Invalidate cached service first
    gmail_client.invalidate(user_id)

    # Revoke token with Google before deleting locally.
    # This removes the app's granted scopes from the user's Google account,
    # so re-authentication will only show newly-requested scopes.
    try:
        existing_token = token_storage.load(user_id)
        if existing_token is not None:
            access_token = existing_token.get("access_token")
            if isinstance(access_token, str) and access_token:
                oauth_manager.revoke_token(access_token)
    except TokenError as e:
        logger.warning("Could not load token for revocation: %s", e)

    # Delete stored token
    try:
        had_credentials = token_storage.delete(user_id)
    except TokenError as e:
        logger.warning("Error deleting token during logout: %s", e)
        had_credentials = False

    if had_credentials:
        logger.info("User logged out successfully")
        return build_success_response(
            data={"logged_out": True},
            message="Successfully logged out. You will need to re-authenticate.",
        )
    else:
        logger.debug("Logout called but no credentials were stored")
        return build_success_response(
            data={"logged_out": False},
            message="No credentials were stored. Already logged out.",
        )

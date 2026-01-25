"""Gmail auth status tool - Check authentication state.

This tool checks whether the user is authenticated and returns
their email address if so.
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.tools.base import build_error_response, build_success_response
from gmail_mcp.utils.errors import AuthenticationError

logger = logging.getLogger(__name__)


async def gmail_get_auth_status() -> dict[str, Any]:
    """Check if the user is authenticated with Gmail.

    Returns the authentication status and user email if authenticated.

    Returns:
        Success response with authentication status:
        - authenticated: True/False
        - email: User's email if authenticated, None otherwise
    """
    user_id = "default"  # Single-user mode

    # Check if credentials exist
    if not gmail_client.is_authenticated(user_id):
        return build_success_response(
            data={
                "authenticated": False,
                "email": None,
            },
            message="Not authenticated. Use gmail_login to sign in.",
        )

    try:
        # Try to get service and fetch profile to verify credentials work
        service = gmail_client.get_service(user_id)
        profile = service.users().getProfile(userId="me").execute()
        user_email = profile["emailAddress"]

        return build_success_response(
            data={
                "authenticated": True,
                "email": user_email,
            },
            message=f"Authenticated as {user_email}",
        )

    except AuthenticationError as e:
        # Credentials exist but are invalid/expired
        logger.warning("Stored credentials are invalid: %s", e)
        return build_success_response(
            data={
                "authenticated": False,
                "email": None,
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

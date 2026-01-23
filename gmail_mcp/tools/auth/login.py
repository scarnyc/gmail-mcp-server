"""Gmail login tool - Two-step device flow authentication.

This tool implements Google's device authorization flow, which is ideal for
MCP servers where browser access cannot be guaranteed.

Flow:
1. User calls gmail_login() without device_code
   → Returns verification URL + user code
   → User visits URL and enters code manually

2. User calls gmail_login(device_code="...") with the device_code
   → Server polls Google until user completes authentication
   → Tokens are stored encrypted
   → Returns success with user email
"""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import build

from gmail_mcp.auth.oauth import oauth_manager
from gmail_mcp.auth.storage import token_storage
from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.tools.base import build_error_response, build_success_response
from gmail_mcp.utils.errors import AuthenticationError

logger = logging.getLogger(__name__)


async def gmail_login(device_code: str | None = None) -> dict[str, Any]:
    """Sign in to Gmail using Google device flow.

    Two-step HITL-like flow:
    1. First call (no device_code): Returns verification URL and user code
    2. Second call (with device_code): Polls for completion, stores tokens

    Args:
        device_code: Device code from step 1 (required for step 2).

    Returns:
        Step 1: {status, verification_uri, user_code, device_code, message}
        Step 2: {status, email, message}
    """
    # Check if OAuth is configured
    if not oauth_manager.is_configured:
        return build_error_response(
            error="OAuth not configured",
            error_code="ConfigurationError",
            details={
                "hint": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                "environment variables"
            },
        )

    try:
        if not device_code:
            # Step 1: Start device flow
            result = oauth_manager.start_device_flow()
            return {
                "status": "awaiting_user_action",
                "verification_uri": result.get("verification_uri"),
                "user_code": result.get("user_code"),
                "device_code": result.get("device_code"),
                "expires_in": result.get("expires_in"),
                "message": (
                    "Visit the verification URL above and enter the user code. "
                    "Then call this tool again with the device_code parameter."
                ),
            }

        # Step 2: Poll for completion
        logger.info("Polling device flow for completion...")
        token_data = oauth_manager.poll_device_flow(device_code)

        # Get user email from Gmail profile
        creds = oauth_manager.get_credentials(token_data)
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        user_email = profile["emailAddress"]

        # Store token with "default" user_id (single-user mode)
        token_storage.save("default", token_data)

        # Invalidate any cached service to force reload with new credentials
        gmail_client.invalidate("default")

        logger.info("Successfully authenticated user: %s", user_email)

        return build_success_response(
            data={"email": user_email},
            message=f"Successfully authenticated as {user_email}",
        )

    except AuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code="AuthenticationError",
        )
    except Exception as e:
        logger.error("Unexpected error during login: %s", e)
        return build_error_response(
            error=f"Login failed: {e}",
            error_code="LoginError",
        )

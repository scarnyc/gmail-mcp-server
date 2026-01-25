"""Gmail login tool - Local server OAuth authentication.

This tool implements Google's OAuth 2.0 local server flow, which opens a browser
for user consent and receives the callback on localhost.

Flow:
1. User calls gmail_login()
2. Browser opens to Google consent page
3. User approves access
4. Callback received on localhost:3000
5. Tokens stored encrypted
6. Returns success with user email

Note: Device flow CANNOT be used with Gmail scopes. Google explicitly blocks
restricted scopes (gmail.readonly, gmail.modify, etc.) from device flow.
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


async def gmail_login() -> dict[str, Any]:
    """Sign in to Gmail using local server OAuth flow.

    Opens a browser to the Google consent page. After the user approves,
    the callback is received on localhost and tokens are stored.

    Returns:
        Success: {status: "success", data: {email: "..."}, message: "..."}
        Error: {status: "error", error: "...", error_code: "..."}
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
        # Run local server flow - opens browser and waits for callback
        logger.info("Starting local server OAuth flow...")
        token_data = oauth_manager.run_local_server(port=3000, timeout=120)

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

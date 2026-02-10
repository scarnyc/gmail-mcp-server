"""Google OAuth 2.0 authentication for Gmail API access.

This module provides OAuth 2.0 authentication flows for obtaining and
managing Gmail API credentials. It supports two authentication flows:

1. Local Server Flow (Desktop): Opens a browser for user consent and runs
   a local HTTP server to receive the authorization callback.

2. Device Flow (Mobile/Headless): User visits a URL and enters a code,
   suitable for environments without browser access.

Security considerations:
- Uses PKCE-like state parameter for CSRF protection in local server flow
- Stores client credentials securely via environment variables
- Supports offline access for refresh token acquisition
"""

from __future__ import annotations

import errno
import logging
import os
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from gmail_mcp.utils.errors import AuthenticationError

logger = logging.getLogger(__name__)

# Gmail API scopes - full set for read-write operations
GMAIL_SCOPES_FULL = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.labels",
]

# Gmail API scopes - minimal set for read-only mode
GMAIL_SCOPES_READONLY = [
    "https://www.googleapis.com/auth/gmail.readonly",
]


def is_read_only() -> bool:
    """Check if server is running in read-only mode."""
    return os.getenv("READ_ONLY", "").lower() in ("true", "1", "yes")


def get_gmail_scopes() -> list[str]:
    """Get Gmail API scopes based on server mode.

    Returns read-only scope when READ_ONLY=true, full scopes otherwise.
    """
    if is_read_only():
        return GMAIL_SCOPES_READONLY
    return GMAIL_SCOPES_FULL


# Backward-compatible alias — prefer get_gmail_scopes() for mode-aware usage
GMAIL_SCOPES = GMAIL_SCOPES_FULL

# Google OAuth endpoints
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_DEVICE_AUTH_URI = "https://oauth2.googleapis.com/device/code"


class OAuthManager:
    """Manages Google OAuth 2.0 authentication flows.

    Supports two authentication flows for obtaining Gmail API credentials:

    1. Local Server Flow: For desktop environments with browser access.
       Opens browser to Google consent page and receives callback on
       a local HTTP server.

    2. Device Flow: For mobile or headless environments. User visits
       a URL and enters a code to complete authentication.

    Attributes:
        _client_id: Google OAuth client ID from environment.
        _client_secret: Google OAuth client secret from environment.
        _redirect_uri: OAuth callback URI for local server flow.

    Example:
        >>> manager = OAuthManager()
        >>> if manager.is_configured:
        ...     token = manager.run_local_server()
        ...     token_storage.save("user@example.com", token)
    """

    def __init__(self) -> None:
        """Initialize OAuth manager with credentials from environment."""
        self._client_id = os.getenv("GOOGLE_CLIENT_ID")
        self._client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self._oauth_port = int(os.getenv("OAUTH_PORT", "3000"))
        self._redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            f"http://localhost:{self._oauth_port}/oauth/callback",
        )

        if not self._client_id or not self._client_secret:
            logger.warning(
                "OAuth credentials not configured. Set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET environment variables."
            )

    @property
    def is_configured(self) -> bool:
        """Check if OAuth is properly configured.

        Returns:
            True if both client ID and secret are set, False otherwise.
        """
        return bool(self._client_id and self._client_secret)

    @property
    def oauth_port(self) -> int:
        """Get the configured OAuth callback port.

        Returns:
            Port number for OAuth callback server (default: 3000).
        """
        return self._oauth_port

    def _get_client_config(self) -> dict[str, Any]:
        """Build OAuth client configuration dictionary.

        Returns:
            Client configuration in the format expected by google-auth-oauthlib.
        """
        # "installed" = Desktop app client type (required by Google for
        # loopback OAuth flows). "web" client type causes Error 400:
        # "Loopback flow has been blocked" with Gmail scopes.
        return {
            "installed": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": GOOGLE_AUTH_URI,
                "token_uri": GOOGLE_TOKEN_URI,
                "redirect_uris": [self._redirect_uri],
            }
        }

    def create_auth_url(self, state: str | None = None) -> tuple[str, str]:
        """Create authorization URL for user consent.

        Generates a URL for the Google OAuth consent page. The state
        parameter is used for CSRF protection.

        Args:
            state: Optional state parameter for CSRF protection.
                If not provided, a random 32-byte state is generated.

        Returns:
            Tuple of (auth_url, state) where auth_url is the full
            authorization URL and state is the CSRF protection token.

        Raises:
            AuthenticationError: If OAuth is not configured.

        Example:
            >>> manager = OAuthManager()
            >>> url, state = manager.create_auth_url()
            >>> print(f"Visit: {url}")
        """
        if not self.is_configured:
            raise AuthenticationError(
                "OAuth not configured",
                details={
                    "hint": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                    "environment variables"
                },
            )

        if state is None:
            state = secrets.token_urlsafe(32)

        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": " ".join(get_gmail_scopes()),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
        }

        auth_url = f"{GOOGLE_AUTH_URI}?{urlencode(params)}"
        logger.debug("Created auth URL with state: %s", state[:8] + "...")
        return auth_url, state

    def exchange_code(self, code: str) -> dict[str, object]:
        """Exchange authorization code for tokens.

        Exchanges the authorization code received from the OAuth callback
        for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback.

        Returns:
            Token data dictionary containing:
                - access_token: Short-lived access token
                - refresh_token: Long-lived refresh token
                - token_uri: Token endpoint URL
                - client_id: OAuth client ID
                - client_secret: OAuth client secret
                - scopes: List of granted scopes
                - expiry: Token expiration timestamp (ISO format)

        Raises:
            AuthenticationError: If OAuth is not configured or
                code exchange fails.
        """
        if not self.is_configured:
            raise AuthenticationError(
                "OAuth not configured",
                details={
                    "hint": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                    "environment variables"
                },
            )

        flow = Flow.from_client_config(
            self._get_client_config(),
            scopes=get_gmail_scopes(),
            redirect_uri=self._redirect_uri,
        )

        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials

            # Note: client_secret is NOT stored in token_data for security.
            # It will be retrieved from environment variables at refresh time.
            token_data = {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "scopes": (
                    list(credentials.scopes)
                    if credentials.scopes
                    else get_gmail_scopes()
                ),
            }

            if credentials.expiry:
                token_data["expiry"] = credentials.expiry.isoformat()

            logger.info("Successfully exchanged authorization code for tokens")
            return token_data

        except Exception as e:
            logger.error("Failed to exchange authorization code: %s", e)
            raise AuthenticationError(
                f"Failed to exchange authorization code: {e}",
                details={"error_type": type(e).__name__},
            ) from e

    def refresh_credentials(self, token_data: dict[str, object]) -> dict[str, object]:
        """Refresh expired access token using refresh token.

        Uses the refresh token to obtain a new access token when the
        current one has expired.

        Args:
            token_data: Existing token data containing refresh_token.

        Returns:
            Updated token data dictionary with new access_token and
            updated expiry.

        Raises:
            AuthenticationError: If no refresh token is available or
                refresh fails.
        """
        if not token_data.get("refresh_token"):
            raise AuthenticationError(
                "No refresh token available",
                details={"hint": "User must re-authenticate to obtain a refresh token"},
            )

        credentials = Credentials(  # type: ignore[no-untyped-call]
            token=token_data.get("access_token"),
            refresh_token=token_data["refresh_token"],
            token_uri=token_data.get("token_uri", GOOGLE_TOKEN_URI),
            client_id=token_data.get("client_id", self._client_id),
            client_secret=token_data.get("client_secret", self._client_secret),
        )

        try:
            credentials.refresh(Request())

            updated = token_data.copy()
            updated["access_token"] = credentials.token
            if credentials.expiry:
                updated["expiry"] = credentials.expiry.isoformat()

            logger.info("Successfully refreshed access token")
            return updated

        except Exception as e:
            logger.error("Failed to refresh token: %s", e)
            raise AuthenticationError(
                f"Failed to refresh token: {e}",
                details={"error_type": type(e).__name__},
            ) from e

    def get_credentials(self, token_data: dict[str, object]) -> Credentials:
        """Build Credentials object from token data.

        Creates a google.oauth2.credentials.Credentials instance from
        stored token data, suitable for use with Google API clients.

        Args:
            token_data: Token data dictionary from storage.

        Returns:
            Credentials object for authenticating API requests.
        """
        return Credentials(  # type: ignore[no-untyped-call]
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", GOOGLE_TOKEN_URI),
            client_id=token_data.get("client_id", self._client_id),
            client_secret=token_data.get("client_secret", self._client_secret),
            scopes=token_data.get("scopes", get_gmail_scopes()),
        )

    # =========================================================================
    # Local Server Flow (Desktop)
    # =========================================================================

    def _create_server(
        self,
        handler_class: type[BaseHTTPRequestHandler],
        port: int,
        max_attempts: int = 3,
    ) -> tuple[HTTPServer, int]:
        """Create HTTP server with fallback ports.

        Attempts to bind to the specified port, falling back to subsequent
        ports if the primary port is in use.

        Args:
            handler_class: HTTP request handler class for the server.
            port: Primary port to attempt binding.
            max_attempts: Maximum number of ports to try (default: 3).

        Returns:
            Tuple of (HTTPServer instance, actual port bound).

        Raises:
            AuthenticationError: If all port attempts fail.
        """
        for attempt in range(max_attempts):
            try_port = port + attempt
            try:
                server = HTTPServer(("localhost", try_port), handler_class)
                if attempt > 0:
                    logger.info(
                        "Using fallback port %d (port %d was in use)",
                        try_port,
                        port,
                    )
                else:
                    logger.debug("OAuth callback server bound to port %d", try_port)
                return server, try_port
            except OSError as e:
                # Check for "Address already in use" error (cross-platform)
                if e.errno == errno.EADDRINUSE or "Address already in use" in str(e):
                    logger.warning(
                        "Port %d in use, trying %d...", try_port, try_port + 1
                    )
                    continue
                # Re-raise other OSError types
                raise

        raise AuthenticationError(
            f"Could not bind to ports {port}-{port + max_attempts - 1}. "
            "All ports are in use.",
            details={"attempted_ports": list(range(port, port + max_attempts))},
        )

    def run_local_server(
        self, port: int = 3000, timeout: int = 120
    ) -> dict[str, object]:
        """Run local OAuth flow with browser and callback server.

        Opens a browser to the Google consent page and runs a local HTTP
        server to receive the OAuth callback. This flow is suitable for
        desktop environments with browser access.

        Args:
            port: Port for the local callback server. Default 3000.
            timeout: Seconds to wait for user to complete auth. Default 120.

        Returns:
            Token data dictionary containing access and refresh tokens.

        Raises:
            AuthenticationError: If authentication fails, times out,
                or user denies access.

        Example:
            >>> manager = OAuthManager()
            >>> token = manager.run_local_server()
            >>> token_storage.save("user@example.com", token)
        """
        result: dict[str, Any] = {}
        error: Exception | None = None
        # state is set after the port is determined (below the handler class)
        state: str = ""

        class CallbackHandler(BaseHTTPRequestHandler):
            """HTTP request handler for OAuth callback."""

            def do_GET(handler_self) -> None:  # noqa: N802, N805
                nonlocal result, error
                parsed = urlparse(handler_self.path)

                if parsed.path == "/oauth/callback":
                    params = parse_qs(parsed.query)

                    # Check for error response
                    if "error" in params:
                        error_msg = params["error"][0]
                        error = AuthenticationError(
                            f"OAuth error: {error_msg}",
                            details={"oauth_error": error_msg},
                        )
                        handler_self.send_response(400)
                        handler_self.send_header("Content-type", "text/html")
                        handler_self.end_headers()
                        handler_self.wfile.write(
                            b"<html><body><h1>Authentication Failed</h1>"
                            b"<p>You can close this window.</p></body></html>"
                        )
                        return

                    # Verify state parameter (CSRF protection)
                    returned_state = params.get("state", [None])[0]
                    if returned_state != state:
                        error = AuthenticationError(
                            "State mismatch - possible CSRF attack",
                            # Note: Don't leak state values in error details
                            details={"hint": "Request may have been tampered with"},
                        )
                        handler_self.send_response(400)
                        handler_self.send_header("Content-type", "text/html")
                        handler_self.end_headers()
                        handler_self.wfile.write(
                            b"<html><body><h1>Security Error</h1>"
                            b"<p>State mismatch. You can close this window.</p>"
                            b"</body></html>"
                        )
                        return

                    # Extract authorization code
                    code = params.get("code", [None])[0]
                    if code:
                        result["code"] = code
                        handler_self.send_response(200)
                        handler_self.send_header("Content-type", "text/html")
                        handler_self.end_headers()
                        handler_self.wfile.write(
                            b"<html><body><h1>Authentication Successful!</h1>"
                            b"<p>You can close this window and return to the "
                            b"application.</p></body></html>"
                        )
                    else:
                        error = AuthenticationError(
                            "No authorization code received",
                            details={"params": list(params.keys())},
                        )
                        handler_self.send_response(400)
                        handler_self.send_header("Content-type", "text/html")
                        handler_self.end_headers()
                        handler_self.wfile.write(
                            b"<html><body><h1>Error</h1>"
                            b"<p>No authorization code received.</p></body></html>"
                        )
                else:
                    handler_self.send_response(404)
                    handler_self.end_headers()

            def log_message(handler_self, format: str, *args: object) -> None:  # noqa: N805
                logger.debug("OAuth callback server: %s", format % args)

        # Start local server with fallback port strategy
        server, actual_port = self._create_server(CallbackHandler, port)
        server.timeout = timeout

        # Generate auth URL ONCE, using the actual bound port.
        # This avoids generating the state parameter twice (which would
        # require the closure to track which state value is current).
        if actual_port != port:
            original_redirect = self._redirect_uri
            self._redirect_uri = f"http://localhost:{actual_port}/oauth/callback"
            auth_url, state = self.create_auth_url()
            self._redirect_uri = original_redirect
        else:
            auth_url, state = self.create_auth_url()

        # Open browser to authorization URL
        logger.info("Opening browser for authentication on port %d...", actual_port)
        webbrowser.open(auth_url)

        # Wait for callback (single request)
        server.handle_request()
        server.server_close()

        # Handle any errors from callback
        if error:
            raise error

        if "code" not in result:
            raise AuthenticationError(
                "Authentication timed out or was cancelled",
                details={"timeout_seconds": timeout},
            )

        # Exchange code for tokens
        return self.exchange_code(result["code"])

    # =========================================================================
    # Device Flow (Mobile/Headless)
    # =========================================================================

    def start_device_flow(self) -> dict[str, object]:
        """Start device authorization flow.

        Initiates the device flow by requesting a device code from Google.
        The user must visit the verification URL and enter the user code.

        Returns:
            Dictionary containing:
                - device_code: Code for polling (used by poll_device_flow)
                - user_code: Code user enters at verification URL
                - verification_uri: URL user visits to enter code
                - expires_in: Seconds until codes expire
                - interval: Minimum seconds between poll attempts

        Raises:
            AuthenticationError: If OAuth is not configured or
                device flow initiation fails.

        Example:
            >>> manager = OAuthManager()
            >>> device_info = manager.start_device_flow()
            >>> print(f"Visit {device_info['verification_uri']}")
            >>> print(f"Enter code: {device_info['user_code']}")
        """
        if not self.is_configured:
            raise AuthenticationError(
                "OAuth not configured",
                details={
                    "hint": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                    "environment variables"
                },
            )

        try:
            response = requests.post(
                GOOGLE_DEVICE_AUTH_URI,
                data={
                    "client_id": self._client_id,
                    "scope": " ".join(get_gmail_scopes()),
                },
                timeout=30,
            )

            if response.status_code != 200:
                raise AuthenticationError(
                    f"Device flow initiation failed: {response.text}",
                    details={"status_code": response.status_code},
                )

            data: dict[str, object] = response.json()
            logger.info(
                "Device flow started. Visit %s and enter code: %s",
                data.get("verification_uri"),
                data.get("user_code"),
            )
            return data

        except requests.RequestException as e:
            logger.error("Network error starting device flow: %s", e)
            raise AuthenticationError(
                f"Network error starting device flow: {e}",
                details={"error_type": type(e).__name__},
            ) from e

    def poll_device_flow(
        self, device_code: str, interval: int = 5, timeout: int = 300
    ) -> dict[str, object]:
        """Poll for device flow completion.

        Polls the token endpoint until the user completes authentication
        at the verification URL, or until timeout.

        Args:
            device_code: Device code from start_device_flow().
            interval: Initial seconds between poll attempts. Default 5.
            timeout: Maximum seconds to wait for completion. Default 300.

        Returns:
            Token data dictionary when user completes authentication.

        Raises:
            AuthenticationError: If user denies access, code expires,
                or polling times out.

        Example:
            >>> device_info = manager.start_device_flow()
            >>> # User completes authentication...
            >>> token = manager.poll_device_flow(device_info["device_code"])
        """
        import time

        if not self.is_configured:
            raise AuthenticationError(
                "OAuth not configured",
                details={
                    "hint": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET "
                    "environment variables"
                },
            )

        elapsed = 0
        current_interval = interval

        while elapsed < timeout:
            try:
                response = requests.post(
                    GOOGLE_TOKEN_URI,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    timeout=30,
                )

                data = response.json()

                # Success - user completed authentication
                # Note: client_secret NOT stored - retrieved from env at refresh
                if "access_token" in data:
                    logger.info("Device flow completed successfully")
                    return {
                        "access_token": data["access_token"],
                        "refresh_token": data.get("refresh_token"),
                        "token_uri": GOOGLE_TOKEN_URI,
                        "client_id": self._client_id,
                        "scopes": get_gmail_scopes(),
                    }

                # Handle various error conditions
                error = data.get("error")

                if error == "authorization_pending":
                    # User hasn't completed auth yet - keep polling
                    time.sleep(current_interval)
                    elapsed += current_interval

                elif error == "slow_down":
                    # Server requests slower polling
                    current_interval += 5
                    logger.debug(
                        "Device flow: slowing down polling to %ds", current_interval
                    )
                    time.sleep(current_interval)
                    elapsed += current_interval

                elif error == "access_denied":
                    raise AuthenticationError(
                        "User denied access",
                        details={"device_code": device_code[:8] + "..."},
                    )

                elif error == "expired_token":
                    raise AuthenticationError(
                        "Device code expired - please restart authentication",
                        details={"elapsed_seconds": elapsed},
                    )

                else:
                    raise AuthenticationError(
                        f"Device flow error: {error}",
                        details={"error": error, "response": data},
                    )

            except requests.RequestException as e:
                logger.warning("Network error during device flow poll: %s", e)
                time.sleep(current_interval)
                elapsed += current_interval

        raise AuthenticationError(
            "Device flow timed out - user did not complete authentication",
            details={"timeout_seconds": timeout},
        )


# Global singleton instance
oauth_manager = OAuthManager()


__all__ = [
    "OAuthManager",
    "oauth_manager",
    "GMAIL_SCOPES",
    "GMAIL_SCOPES_FULL",
    "GMAIL_SCOPES_READONLY",
    "get_gmail_scopes",
    "is_read_only",
    "GOOGLE_AUTH_URI",
    "GOOGLE_TOKEN_URI",
    "GOOGLE_DEVICE_AUTH_URI",
]

"""Integration tests for OAuth flow with mock server.

Tests the OAuth manager's ability to:
- Create callback servers with fallback ports
- Handle port binding failures
- Validate state parameters (CSRF protection)
"""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

import pytest

from gmail_mcp.auth.oauth import OAuthManager
from gmail_mcp.utils.errors import AuthenticationError


class TestOAuthPortFallback:
    """Tests for port binding and fallback behavior."""

    def test_create_server_binds_successfully(self):
        """Test server binds to a port (primary or fallback)."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()

            # Use a high port unlikely to be in use
            test_port = 59152

            class DummyHandler(BaseHTTPRequestHandler):
                pass

            server, actual_port = manager._create_server(DummyHandler, test_port)

            try:
                # Should bind to primary or fallback port
                assert actual_port >= test_port
                assert actual_port < test_port + 3  # Within fallback range
                assert server is not None
            finally:
                server.server_close()

    def test_create_server_falls_back_when_port_in_use(self):
        """Test server falls back to next port when primary is in use."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()
            test_port = 59153

            # Occupy the primary port
            blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("localhost", test_port))
            blocker.listen(1)

            class DummyHandler(BaseHTTPRequestHandler):
                pass

            try:
                server, actual_port = manager._create_server(DummyHandler, test_port)

                # Should have fallen back to next port
                assert actual_port == test_port + 1
                server.server_close()
            finally:
                blocker.close()

    def test_create_server_raises_when_all_ports_fail(self):
        """Test raises error when all fallback ports are in use."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()
            test_port = 59154

            # Occupy all fallback ports
            blockers = []
            for i in range(3):  # Default max_attempts is 3
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("localhost", test_port + i))
                sock.listen(1)
                blockers.append(sock)

            class DummyHandler(BaseHTTPRequestHandler):
                pass

            try:
                with pytest.raises(AuthenticationError) as exc_info:
                    manager._create_server(DummyHandler, test_port)

                assert "Could not bind to ports" in str(exc_info.value)
            finally:
                for sock in blockers:
                    sock.close()


class TestOAuthPortConfiguration:
    """Tests for OAuth port configuration via environment variable."""

    def test_default_port_is_3000(self):
        """Test default OAuth port is 3000."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
            clear=False,
        ):
            # Remove OAUTH_PORT if set
            import os

            os.environ.pop("OAUTH_PORT", None)

            manager = OAuthManager()
            assert manager.oauth_port == 3000

    def test_custom_port_from_env(self):
        """Test custom OAuth port from environment variable."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
                "OAUTH_PORT": "4000",
            },
        ):
            manager = OAuthManager()
            assert manager.oauth_port == 4000

    def test_redirect_uri_uses_configured_port(self):
        """Test redirect URI uses the configured port."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
                "OAUTH_PORT": "5000",
            },
        ):
            manager = OAuthManager()
            assert "localhost:5000" in manager._redirect_uri


class TestOAuthCallbackServer:
    """Tests for OAuth callback server behavior."""

    def test_callback_server_handles_request(self):
        """Test callback server can receive and handle a request."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()
            received_path = None

            class TestHandler(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    nonlocal received_path
                    received_path = self.path
                    self.send_response(200)
                    self.end_headers()

                def log_message(self, format: str, *args: object) -> None:
                    pass  # Suppress logging

            server, port = manager._create_server(TestHandler, 59160)
            server.timeout = 5

            def make_request() -> None:
                import urllib.request

                try:
                    urllib.request.urlopen(
                        f"http://localhost:{port}/oauth/callback?code=test"
                    )
                except Exception:
                    pass

            # Start request in thread
            thread = threading.Thread(target=make_request)
            thread.start()

            # Handle the request
            server.handle_request()
            server.server_close()

            thread.join(timeout=2)

            assert received_path == "/oauth/callback?code=test"


class TestOAuthStateValidation:
    """Tests for OAuth state parameter validation (CSRF protection)."""

    def test_state_parameter_is_generated(self):
        """Test state parameter is generated for auth URL."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()
            auth_url, state = manager.create_auth_url()

            assert state is not None
            assert len(state) > 0
            assert "state=" in auth_url

    def test_custom_state_is_used(self):
        """Test custom state parameter is used in auth URL."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()
            custom_state = "my_custom_state_value"
            auth_url, state = manager.create_auth_url(state=custom_state)

            assert state == custom_state
            assert f"state={custom_state}" in auth_url

    def test_state_validation_with_fallback_port(self):
        """Test run_local_server succeeds with correct state after port fallback.

        Blocks the primary port to force fallback, then simulates a browser
        callback with the correct state parameter. Verifies the full flow
        produces a valid authorization code exchange.
        """
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()

            # Occupy the primary port to force fallback
            test_port = 59161
            blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("localhost", test_port))
            blocker.listen(1)

            mock_token_data = {
                "access_token": "ya29.fallback_test",
                "refresh_token": "refresh_fallback",
                "token_uri": "https://oauth2.googleapis.com/token",
            }

            try:
                # Capture the auth URL opened in the browser to extract state
                opened_urls: list[str] = []

                def capture_url(url: str) -> bool:
                    opened_urls.append(url)
                    # Simulate browser callback: extract state from URL and
                    # POST back to the fallback port with code + state
                    from urllib.parse import parse_qs, urlparse

                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    callback_state = params["state"][0]
                    callback_port = test_port + 1  # Expected fallback port

                    def send_callback() -> None:
                        import time
                        import urllib.request

                        time.sleep(0.1)  # Let server start listening
                        try:
                            urllib.request.urlopen(
                                f"http://localhost:{callback_port}/oauth/callback"
                                f"?code=test_auth_code&state={callback_state}"
                            )
                        except Exception:
                            pass

                    t = threading.Thread(target=send_callback)
                    t.start()
                    return True

                with (
                    patch("webbrowser.open", side_effect=capture_url),
                    patch.object(
                        manager, "exchange_code", return_value=mock_token_data
                    ),
                ):
                    result = manager.run_local_server(
                        port=test_port, timeout=5
                    )

                # Verify fallback port was used (state in URL targets port+1)
                assert len(opened_urls) == 1
                assert f"localhost%3A{test_port + 1}" in opened_urls[0] or \
                    f"localhost:{test_port + 1}" in opened_urls[0]

                # Verify exchange_code was called (state matched successfully)
                assert result == mock_token_data

            finally:
                blocker.close()

    def test_state_mismatch_rejected_with_fallback_port(self):
        """Test callback with wrong state is rejected after port fallback.

        Blocks the primary port, then simulates a callback with a WRONG
        state parameter. Verifies the handler rejects the request.
        """
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_CLIENT_ID": "test_client_id",
                "GOOGLE_CLIENT_SECRET": "test_secret",
            },
        ):
            manager = OAuthManager()

            test_port = 59162
            blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            blocker.bind(("localhost", test_port))
            blocker.listen(1)

            try:

                def send_bad_callback(url: str) -> bool:
                    callback_port = test_port + 1

                    def send_callback() -> None:
                        import time
                        import urllib.request

                        time.sleep(0.1)
                        try:
                            urllib.request.urlopen(
                                f"http://localhost:{callback_port}/oauth/callback"
                                f"?code=test_code&state=WRONG_STATE"
                            )
                        except Exception:
                            pass

                    t = threading.Thread(target=send_callback)
                    t.start()
                    return True

                from gmail_mcp.utils.errors import AuthenticationError

                with patch("webbrowser.open", side_effect=send_bad_callback):
                    with pytest.raises(AuthenticationError, match="State mismatch"):
                        manager.run_local_server(port=test_port, timeout=5)

            finally:
                blocker.close()

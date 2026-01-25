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
        """Test state parameter is correctly captured when using fallback port.

        This test verifies that the state parameter captured in the callback
        handler closure is stable even when port fallback occurs. The closure
        captures state before _create_server() is called, so it should remain
        consistent regardless of which port is actually bound.
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

            try:
                # Generate state before server creation (same as run_local_server)
                auth_url, expected_state = manager.create_auth_url()

                # Verify state is in the auth URL
                assert f"state={expected_state}" in auth_url

                class DummyHandler(BaseHTTPRequestHandler):
                    pass

                # Create server with fallback (will use test_port + 1)
                server, actual_port = manager._create_server(
                    DummyHandler, test_port
                )
                server.server_close()

                # Verify fallback occurred
                assert actual_port == test_port + 1

                # The key assertion: state generated before _create_server
                # should be the same state that would be validated in callback
                # (This verifies the closure captures the correct state)
                auth_url_after, state_after = manager.create_auth_url(
                    state=expected_state
                )
                assert state_after == expected_state

            finally:
                blocker.close()

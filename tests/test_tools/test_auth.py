"""Tests for OAuth authentication tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.utils.errors import AuthenticationError


class TestGmailLogin:
    """Tests for gmail_login tool (local server OAuth flow)."""

    @pytest.mark.asyncio
    async def test_login_success_stores_token(self):
        """Test successful login stores tokens and returns email."""
        mock_token_data = {
            "access_token": "ya29.test_token",
            "refresh_token": "refresh_test",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        mock_profile = {"emailAddress": "user@gmail.com"}

        with (
            patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth,
            patch("gmail_mcp.tools.auth.login.token_storage") as mock_storage,
            patch("gmail_mcp.tools.auth.login.gmail_client") as mock_client,
            patch("gmail_mcp.tools.auth.login.build") as mock_build,
        ):
            mock_oauth.is_configured = True
            mock_oauth.oauth_port = 3000  # Default port
            mock_oauth.run_local_server.return_value = mock_token_data
            mock_oauth.get_credentials.return_value = MagicMock()

            mock_service = MagicMock()
            mock_users = mock_service.users.return_value
            mock_users.getProfile.return_value.execute.return_value = mock_profile
            mock_build.return_value = mock_service

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login()

            assert result["status"] == "success"
            assert result["data"]["email"] == "user@gmail.com"
            mock_oauth.run_local_server.assert_called_once_with(port=3000, timeout=120)
            mock_storage.save.assert_called_once_with("default", mock_token_data)
            mock_client.invalidate.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_login_not_configured_returns_error(self):
        """Test returns error when OAuth is not configured."""
        with patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth:
            mock_oauth.is_configured = False

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login()

            assert result["status"] == "error"
            assert "not configured" in result["error"].lower()
            assert result["error_code"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_login_uses_configured_port(self):
        """Test login uses the configured OAuth port."""
        mock_token_data = {
            "access_token": "ya29.test_token",
            "refresh_token": "refresh_test",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        mock_profile = {"emailAddress": "user@gmail.com"}

        with (
            patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth,
            patch("gmail_mcp.tools.auth.login.token_storage"),
            patch("gmail_mcp.tools.auth.login.gmail_client"),
            patch("gmail_mcp.tools.auth.login.build") as mock_build,
        ):
            mock_oauth.is_configured = True
            mock_oauth.oauth_port = 4000  # Custom port
            mock_oauth.run_local_server.return_value = mock_token_data
            mock_oauth.get_credentials.return_value = MagicMock()

            mock_service = MagicMock()
            mock_users = mock_service.users.return_value
            mock_users.getProfile.return_value.execute.return_value = mock_profile
            mock_build.return_value = mock_service

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login()

            assert result["status"] == "success"
            # Verify custom port was used
            mock_oauth.run_local_server.assert_called_once_with(port=4000, timeout=120)

    @pytest.mark.asyncio
    async def test_login_handles_auth_error(self):
        """Test handles AuthenticationError from OAuth flow."""
        with patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth:
            mock_oauth.is_configured = True
            mock_oauth.oauth_port = 3000
            mock_oauth.run_local_server.side_effect = AuthenticationError(
                "User denied access"
            )

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login()

            assert result["status"] == "error"
            assert result["error_code"] == "AuthenticationError"
            assert "User denied access" in result["error"]

    @pytest.mark.asyncio
    async def test_login_handles_timeout(self):
        """Test handles timeout waiting for OAuth callback."""
        with patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth:
            mock_oauth.is_configured = True
            mock_oauth.oauth_port = 3000
            mock_oauth.run_local_server.side_effect = AuthenticationError(
                "OAuth flow timed out"
            )

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login()

            assert result["status"] == "error"
            assert result["error_code"] == "AuthenticationError"


class TestGmailLogout:
    """Tests for gmail_logout tool."""

    @pytest.mark.asyncio
    async def test_logout_clears_credentials(self):
        """Test logout clears stored credentials."""
        with (
            patch("gmail_mcp.tools.auth.logout.gmail_client") as mock_client,
            patch("gmail_mcp.tools.auth.logout.token_storage") as mock_storage,
        ):
            mock_storage.delete.return_value = True

            from gmail_mcp.tools.auth.logout import gmail_logout

            result = await gmail_logout()

            assert result["status"] == "success"
            assert result["data"]["logged_out"] is True
            mock_client.invalidate.assert_called_once_with("default")
            mock_storage.delete.assert_called_once_with("default")

    @pytest.mark.asyncio
    async def test_logout_no_credentials(self):
        """Test logout when no credentials exist."""
        with (
            patch("gmail_mcp.tools.auth.logout.gmail_client") as mock_client,
            patch("gmail_mcp.tools.auth.logout.token_storage") as mock_storage,
        ):
            mock_storage.delete.return_value = False

            from gmail_mcp.tools.auth.logout import gmail_logout

            result = await gmail_logout()

            assert result["status"] == "success"
            assert result["data"]["logged_out"] is False
            assert "Already logged out" in result["message"]
            mock_client.invalidate.assert_called_once_with("default")


class TestGmailGetAuthStatus:
    """Tests for gmail_get_auth_status tool."""

    @pytest.mark.asyncio
    async def test_auth_status_authenticated(self):
        """Test returns authenticated status with email."""
        mock_profile = {"emailAddress": "user@gmail.com"}

        with patch("gmail_mcp.tools.auth.status.gmail_client") as mock_client:
            mock_client.is_authenticated.return_value = True
            mock_service = MagicMock()
            mock_users = mock_service.users.return_value
            mock_users.getProfile.return_value.execute.return_value = mock_profile
            mock_client.get_service.return_value = mock_service

            from gmail_mcp.tools.auth.status import gmail_get_auth_status

            result = await gmail_get_auth_status()

            assert result["status"] == "success"
            assert result["data"]["authenticated"] is True
            assert result["data"]["email"] == "user@gmail.com"

    @pytest.mark.asyncio
    async def test_auth_status_not_authenticated(self):
        """Test returns not authenticated status."""
        with patch("gmail_mcp.tools.auth.status.gmail_client") as mock_client:
            mock_client.is_authenticated.return_value = False

            from gmail_mcp.tools.auth.status import gmail_get_auth_status

            result = await gmail_get_auth_status()

            assert result["status"] == "success"
            assert result["data"]["authenticated"] is False
            assert result["data"]["email"] is None

    @pytest.mark.asyncio
    async def test_auth_status_invalid_credentials(self):
        """Test returns not authenticated when credentials are invalid."""
        with patch("gmail_mcp.tools.auth.status.gmail_client") as mock_client:
            mock_client.is_authenticated.return_value = True
            mock_client.get_service.side_effect = AuthenticationError("Token expired")

            from gmail_mcp.tools.auth.status import gmail_get_auth_status

            result = await gmail_get_auth_status()

            assert result["status"] == "success"
            assert result["data"]["authenticated"] is False
            assert "invalid or expired" in result["message"].lower()

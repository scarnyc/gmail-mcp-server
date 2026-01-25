"""Tests for OAuth authentication tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.utils.errors import AuthenticationError


class TestGmailLogin:
    """Tests for gmail_login tool."""

    @pytest.mark.asyncio
    async def test_login_step1_returns_device_info(self):
        """Test first call returns device flow info."""
        mock_device_info = {
            "verification_uri": "https://www.google.com/device",
            "user_code": "ABC-DEF",
            "device_code": "device_code_123",
            "expires_in": 1800,
        }

        with patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth:
            mock_oauth.is_configured = True
            mock_oauth.start_device_flow.return_value = mock_device_info

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login(device_code=None)

            assert result["status"] == "awaiting_user_action"
            assert result["verification_uri"] == "https://www.google.com/device"
            assert result["user_code"] == "ABC-DEF"
            assert result["device_code"] == "device_code_123"
            mock_oauth.start_device_flow.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_step2_polls_and_stores_token(self):
        """Test second call polls and stores tokens."""
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
            mock_oauth.poll_device_flow.return_value = mock_token_data
            mock_oauth.get_credentials.return_value = MagicMock()

            mock_service = MagicMock()
            mock_service.users.return_value.getProfile.return_value.execute.return_value = (
                mock_profile
            )
            mock_build.return_value = mock_service

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login(device_code="device_code_123")

            assert result["status"] == "success"
            assert result["data"]["email"] == "user@gmail.com"
            mock_oauth.poll_device_flow.assert_called_once_with("device_code_123")
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
    async def test_login_handles_auth_error(self):
        """Test handles AuthenticationError during polling."""
        with patch("gmail_mcp.tools.auth.login.oauth_manager") as mock_oauth:
            mock_oauth.is_configured = True
            mock_oauth.poll_device_flow.side_effect = AuthenticationError(
                "User denied access"
            )

            from gmail_mcp.tools.auth.login import gmail_login

            result = await gmail_login(device_code="device_code_123")

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
            mock_service.users.return_value.getProfile.return_value.execute.return_value = (
                mock_profile
            )
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
            mock_client.get_service.side_effect = AuthenticationError(
                "Token expired"
            )

            from gmail_mcp.tools.auth.status import gmail_get_auth_status

            result = await gmail_get_auth_status()

            assert result["status"] == "success"
            assert result["data"]["authenticated"] is False
            assert "invalid or expired" in result["message"].lower()

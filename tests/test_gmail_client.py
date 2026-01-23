"""Tests for Gmail client credential handling."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.gmail.client import GmailClient


class TestBuildCredentials:
    """Tests for _build_credentials method."""

    @pytest.fixture
    def gmail_client(self) -> GmailClient:
        """Create a fresh GmailClient instance."""
        return GmailClient()

    @pytest.fixture
    def token_data_with_secret(self) -> dict[str, Any]:
        """Token data that includes client_secret."""
        return {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            "client_secret": "test-secret-from-token",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            "expiry": (datetime.now() + timedelta(hours=1)).isoformat(),
        }

    @pytest.fixture
    def token_data_without_secret(self) -> dict[str, Any]:
        """Token data without client_secret (after refresh)."""
        return {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test-client-id",
            # No client_secret - simulating token file after refresh
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            "expiry": (datetime.now() + timedelta(hours=1)).isoformat(),
        }

    def test_uses_client_secret_from_token_data_when_present(
        self,
        gmail_client: GmailClient,
        token_data_with_secret: dict[str, Any],
    ) -> None:
        """Verify client_secret from token_data is used when present."""
        creds = gmail_client._build_credentials(token_data_with_secret)

        assert creds.client_secret == "test-secret-from-token"

    def test_falls_back_to_env_when_secret_missing(
        self,
        gmail_client: GmailClient,
        token_data_without_secret: dict[str, Any],
    ) -> None:
        """Verify fallback to GOOGLE_CLIENT_SECRET env var when missing from token."""
        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "secret-from-env"}):
            creds = gmail_client._build_credentials(token_data_without_secret)

        assert creds.client_secret == "secret-from-env"

    def test_prefers_token_data_over_env(
        self,
        gmail_client: GmailClient,
        token_data_with_secret: dict[str, Any],
    ) -> None:
        """Verify token_data client_secret takes precedence over env var."""
        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "secret-from-env"}):
            creds = gmail_client._build_credentials(token_data_with_secret)

        # Token data should win over environment
        assert creds.client_secret == "test-secret-from-token"

    def test_handles_missing_expiry(
        self,
        gmail_client: GmailClient,
    ) -> None:
        """Verify credentials build correctly without expiry field."""
        token_data = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "client_id": "test-client-id",
        }
        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "secret-from-env"}):
            creds = gmail_client._build_credentials(token_data)

        assert creds.token == "test-access-token"
        assert creds.expiry is None

    def test_handles_invalid_expiry_format(
        self,
        gmail_client: GmailClient,
    ) -> None:
        """Verify invalid expiry is handled gracefully."""
        token_data = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "client_id": "test-client-id",
            "expiry": "not-a-valid-date",
        }
        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "secret-from-env"}):
            creds = gmail_client._build_credentials(token_data)

        # Should handle gracefully, expiry will be None
        assert creds.token == "test-access-token"
        assert creds.expiry is None

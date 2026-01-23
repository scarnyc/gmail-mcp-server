"""Integration tests for cross-component functionality."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from gmail_mcp.gmail.client import GmailClient
from gmail_mcp.middleware.rate_limiter import RateLimiter
from gmail_mcp.utils.errors import RateLimitError


class TestTokenRefreshFallback:
    """Test client_secret fallback to env var during token refresh."""

    def test_build_credentials_uses_env_secret_when_not_in_token(self) -> None:
        """When token_data has no client_secret, fall back to GOOGLE_CLIENT_SECRET."""
        client = GmailClient()

        token_data = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }

        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "env_secret"}):
            creds = client._build_credentials(token_data)
            assert creds.client_secret == "env_secret"

    def test_build_credentials_with_empty_string_secret_uses_env(self) -> None:
        """Empty string client_secret should fall back to env var."""
        client = GmailClient()

        token_data = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "",  # Empty string
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }

        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "env_secret"}):
            creds = client._build_credentials(token_data)
            assert creds.client_secret == "env_secret"

    def test_build_credentials_prefers_token_secret_over_env(self) -> None:
        """When token_data has client_secret, prefer it over env var."""
        client = GmailClient()

        token_data = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "token_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }

        with patch.dict(os.environ, {"GOOGLE_CLIENT_SECRET": "env_secret"}):
            creds = client._build_credentials(token_data)
            assert creds.client_secret == "token_secret"


class TestRateLimiterBoundary:
    """Test rate limiter edge cases."""

    def test_exact_limit_consumption_succeeds(self) -> None:
        """Consuming exactly max_requests should succeed."""
        limiter = RateLimiter(max_requests=5)

        # Consume all 5
        for _ in range(5):
            limiter.consume("test_user")

        # 6th should fail
        with pytest.raises(RateLimitError):
            limiter.consume("test_user")

    def test_different_users_have_independent_limits(self) -> None:
        """Each user should have their own rate limit bucket."""
        limiter = RateLimiter(max_requests=2)

        # User A uses both tokens
        limiter.consume("user_a")
        limiter.consume("user_a")

        # User A is exhausted
        with pytest.raises(RateLimitError):
            limiter.consume("user_a")

        # User B should still work
        limiter.consume("user_b")  # Should not raise

    def test_remaining_returns_correct_count(self) -> None:
        """remaining() should return accurate token count."""
        limiter = RateLimiter(max_requests=10)

        assert limiter.remaining("test_user") == 10

        limiter.consume("test_user", tokens=3)
        assert limiter.remaining("test_user") == 7

    def test_check_does_not_consume_tokens(self) -> None:
        """check() should validate without consuming."""
        limiter = RateLimiter(max_requests=1)

        assert limiter.check("test_user") is True
        assert limiter.remaining("test_user") == 1

        limiter.consume("test_user")
        assert limiter.check("test_user") is False
        assert limiter.remaining("test_user") == 0

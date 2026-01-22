"""Pytest configuration and fixtures for Gmail MCP server tests."""

import pytest


@pytest.fixture
def mock_credentials():
    """Fixture providing mock Google OAuth credentials."""
    return {
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "redirect_uri": "http://localhost:3000/oauth/callback",
    }


@pytest.fixture
def mock_token():
    """Fixture providing mock OAuth token data."""
    return {
        "access_token": "mock-access-token",
        "refresh_token": "mock-refresh-token",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@pytest.fixture
def sample_email():
    """Fixture providing sample email data for testing."""
    return {
        "id": "18abc123def",
        "threadId": "18abc123def",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "This is a test email snippet...",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test Email Subject"},
                {"name": "Date", "value": "Mon, 20 Jan 2026 10:00:00 -0500"},
            ],
            "mimeType": "text/plain",
            "body": {
                "data": "VGhpcyBpcyB0aGUgZW1haWwgYm9keSBjb250ZW50Lg==",
            },
        },
    }


@pytest.fixture
def mock_gmail_service(mocker):
    """Fixture providing a mocked Gmail API service."""
    mock_service = mocker.MagicMock()
    return mock_service

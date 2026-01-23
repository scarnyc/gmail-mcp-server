"""Fixtures for tool tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.hitl.models import ApprovalRequest, ApprovalStatus


@pytest.fixture
def mock_gmail_service() -> MagicMock:
    """Mock Gmail API service."""
    return MagicMock()


@pytest.fixture
def mock_gmail_client(mock_gmail_service: MagicMock):
    """Mock gmail_client.get_service()."""
    with patch("gmail_mcp.gmail.client.gmail_client") as mock:
        mock.get_service.return_value = mock_gmail_service
        yield mock


@pytest.fixture
def mock_rate_limiter():
    """Mock rate_limiter.consume()."""
    with patch("gmail_mcp.tools.base.rate_limiter") as mock:
        mock.consume.return_value = None
        yield mock


@pytest.fixture
def mock_audit_logger():
    """Mock audit_logger.log_tool_call()."""
    with patch("gmail_mcp.tools.base.audit_logger") as mock:
        yield mock


@pytest.fixture
def mock_approval_manager():
    """Mock approval_manager for HITL tests."""
    with patch("gmail_mcp.tools.base.approval_manager") as mock:
        yield mock


@pytest.fixture
def sample_message_list() -> list[dict[str, str]]:
    """Sample message list response."""
    return [
        {"id": "msg1", "threadId": "thread1"},
        {"id": "msg2", "threadId": "thread2"},
    ]


@pytest.fixture
def sample_full_message() -> dict[str, Any]:
    """Sample full message response."""
    return {
        "id": "msg1",
        "threadId": "thread1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Test message snippet",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test Subject"},
                {"name": "Date", "value": "Mon, 20 Jan 2026 10:00:00 -0500"},
            ],
            "body": {"data": "VGVzdCBib2R5IGNvbnRlbnQ="},
        },
    }


@pytest.fixture
def sample_thread(sample_full_message: dict[str, Any]) -> dict[str, Any]:
    """Sample thread response."""
    return {
        "id": "thread1",
        "messages": [sample_full_message],
    }


@pytest.fixture
def sample_labels() -> list[dict[str, str]]:
    """Sample labels list response."""
    return [
        {"id": "INBOX", "name": "INBOX", "type": "system"},
        {"id": "UNREAD", "name": "UNREAD", "type": "system"},
        {"id": "Label_1", "name": "Work", "type": "user"},
        {"id": "Label_2", "name": "Personal", "type": "user"},
    ]


@pytest.fixture
def valid_approval_request() -> ApprovalRequest:
    """Create a valid approval request for testing."""
    return ApprovalRequest(
        action="send_email",
        preview={"to": "test@example.com", "subject": "Test"},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        status=ApprovalStatus.PENDING,
    )


@pytest.fixture
def expired_approval_request() -> ApprovalRequest:
    """Create an expired approval request for testing."""
    return ApprovalRequest(
        action="send_email",
        preview={"to": "test@example.com", "subject": "Test"},
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        status=ApprovalStatus.PENDING,
    )

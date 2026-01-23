"""Tests for write Gmail tools with HITL approval."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.hitl.models import ApprovalRequest
from gmail_mcp.schemas.tools import (
    ArchiveEmailParams,
    CreateLabelParams,
    DeleteEmailParams,
    OrganizeLabelsParams,
    SendEmailParams,
    UnsubscribeParams,
)
from gmail_mcp.utils.errors import ApprovalError


class TestHITLTwoStepFlow:
    """Base tests for HITL two-step flow pattern."""

    @pytest.mark.asyncio
    async def test_step1_returns_pending_approval(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test first call without approval_id returns pending_approval."""
        with patch(
            "gmail_mcp.tools.write.send.gmail_client", mock_gmail_client
        ), patch("gmail_mcp.tools.write.send.create_approval_request") as mock_create:
            mock_create.return_value = {
                "status": "pending_approval",
                "approval_id": "test-id",
                "expires_at": "2026-01-23T15:30:00+00:00",
                "preview": {"to": "test@example.com"},
                "message": "ACTION NOT TAKEN. Please review and confirm.",
            }

            from gmail_mcp.tools.write.send import gmail_send_email

            params = SendEmailParams(
                to="test@example.com",
                subject="Test",
                body="Test body",
            )
            result = await gmail_send_email(params)

            assert result["status"] == "pending_approval"
            assert "approval_id" in result
            mock_create.assert_called_once()


class TestGmailSendEmail:
    """Tests for gmail_send_email tool."""

    @pytest.mark.asyncio
    async def test_send_preview_includes_body_truncation(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test preview truncates long body."""
        with patch(
            "gmail_mcp.tools.write.send.gmail_client", mock_gmail_client
        ), patch("gmail_mcp.tools.write.send.create_approval_request") as mock_create:
            mock_create.return_value = {"status": "pending_approval"}

            from gmail_mcp.tools.write.send import gmail_send_email

            long_body = "x" * 1000
            params = SendEmailParams(
                to="test@example.com",
                subject="Test",
                body=long_body,
            )
            await gmail_send_email(params)

            # Check that preview was called with truncated body
            call_args = mock_create.call_args
            preview = call_args.kwargs.get("preview") or call_args.args[1]
            assert len(preview.get("body_preview", "")) <= 503  # 500 + "..."

    @pytest.mark.asyncio
    async def test_send_execution_calls_gmail_api(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        valid_approval_request: ApprovalRequest,
    ):
        """Test approved send calls Gmail API."""
        with patch(
            "gmail_mcp.tools.write.send.gmail_client", mock_gmail_client
        ), patch(
            "gmail_mcp.tools.write.send.validate_and_consume_approval"
        ) as mock_validate, patch(
            "gmail_mcp.tools.write.send.send_message"
        ) as mock_send:
            mock_validate.return_value = valid_approval_request
            mock_send.return_value = {"id": "sent-msg-1", "threadId": "thread-1"}

            from gmail_mcp.tools.write.send import gmail_send_email

            params = SendEmailParams(
                to="test@example.com",
                subject="Test",
                body="Body",
                approval_id="valid-approval-id",
            )
            result = await gmail_send_email(params)

            assert result["status"] == "success"
            assert result["data"]["message_id"] == "sent-msg-1"
            mock_send.assert_called_once()


class TestGmailArchiveEmail:
    """Tests for gmail_archive_email tool."""

    @pytest.mark.asyncio
    async def test_archive_preview_shows_messages(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_full_message: dict[str, Any],
    ):
        """Test preview includes message details."""
        with patch(
            "gmail_mcp.tools.write.archive.gmail_client", mock_gmail_client
        ), patch("gmail_mcp.tools.write.archive.get_message") as mock_get, patch(
            "gmail_mcp.tools.write.archive.create_approval_request"
        ) as mock_create:
            mock_get.return_value = sample_full_message
            mock_create.return_value = {"status": "pending_approval"}

            from gmail_mcp.tools.write.archive import gmail_archive_email

            params = ArchiveEmailParams(message_ids=["msg1"])
            await gmail_archive_email(params)

            mock_create.assert_called_once()
            call_args = mock_create.call_args
            preview = call_args.kwargs.get("preview") or call_args.args[1]
            assert "messages" in preview

    @pytest.mark.asyncio
    async def test_archive_removes_inbox_label(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        valid_approval_request: ApprovalRequest,
    ):
        """Test archive removes INBOX label."""
        with patch(
            "gmail_mcp.tools.write.archive.gmail_client", mock_gmail_client
        ), patch(
            "gmail_mcp.tools.write.archive.validate_and_consume_approval"
        ) as mock_validate, patch(
            "gmail_mcp.tools.write.archive.batch_modify_messages"
        ) as mock_modify:
            mock_validate.return_value = valid_approval_request

            from gmail_mcp.tools.write.archive import gmail_archive_email

            params = ArchiveEmailParams(
                message_ids=["msg1", "msg2"],
                approval_id="valid-id",
            )
            result = await gmail_archive_email(params)

            assert result["status"] == "success"
            mock_modify.assert_called_once()
            call_args = mock_modify.call_args
            assert "INBOX" in call_args.kwargs.get("remove_labels", [])


class TestGmailDeleteEmail:
    """Tests for gmail_delete_email tool."""

    @pytest.mark.asyncio
    async def test_delete_moves_to_trash(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        valid_approval_request: ApprovalRequest,
    ):
        """Test delete moves to trash, not permanent delete."""
        with patch(
            "gmail_mcp.tools.write.delete.gmail_client", mock_gmail_client
        ), patch(
            "gmail_mcp.tools.write.delete.validate_and_consume_approval"
        ) as mock_validate, patch(
            "gmail_mcp.tools.write.delete.trash_message"
        ) as mock_trash:
            mock_validate.return_value = valid_approval_request

            from gmail_mcp.tools.write.delete import gmail_delete_email

            params = DeleteEmailParams(
                message_ids=["msg1"],
                approval_id="valid-id",
            )
            result = await gmail_delete_email(params)

            assert result["status"] == "success"
            mock_trash.assert_called_once_with(mock_gmail_client.get_service(), "msg1")


class TestGmailUnsubscribe:
    """Tests for gmail_unsubscribe tool."""

    @pytest.mark.asyncio
    async def test_unsubscribe_handles_no_header(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_full_message: dict[str, Any],
    ):
        """Test error when no List-Unsubscribe header."""
        with patch(
            "gmail_mcp.tools.write.unsubscribe.gmail_client", mock_gmail_client
        ), patch("gmail_mcp.tools.write.unsubscribe.get_message") as mock_get:
            # Message without List-Unsubscribe header
            mock_get.return_value = sample_full_message

            from gmail_mcp.tools.write.unsubscribe import gmail_unsubscribe

            params = UnsubscribeParams(message_id="msg1")
            result = await gmail_unsubscribe(params)

            assert result["status"] == "error"
            assert "NO_UNSUBSCRIBE_HEADER" in result.get("error_code", "")


class TestGmailCreateLabel:
    """Tests for gmail_create_label tool."""

    @pytest.mark.asyncio
    async def test_create_label_preview(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test create label returns preview."""
        with patch(
            "gmail_mcp.tools.write.labels.gmail_client", mock_gmail_client
        ), patch(
            "gmail_mcp.tools.write.labels.create_approval_request"
        ) as mock_create:
            mock_create.return_value = {"status": "pending_approval"}

            from gmail_mcp.tools.write.labels import gmail_create_label

            params = CreateLabelParams(name="New Label")
            result = await gmail_create_label(params)

            assert result["status"] == "pending_approval"
            mock_create.assert_called_once()


class TestGmailOrganizeLabels:
    """Tests for gmail_organize_labels tool."""

    @pytest.mark.asyncio
    async def test_organize_validates_operations(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test invalid operations are rejected."""
        with patch("gmail_mcp.tools.write.labels.gmail_client", mock_gmail_client):
            from gmail_mcp.tools.write.labels import gmail_organize_labels

            # Missing required field
            params = OrganizeLabelsParams(
                operations=[{"action": "invalid_action", "label_id": "123"}]
            )
            result = await gmail_organize_labels(params)

            assert result["status"] == "error"

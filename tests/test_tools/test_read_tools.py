"""Tests for read-only Gmail tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.schemas.tools import (
    ApplyLabelsParams,
    ChatInboxParams,
    DownloadEmailParams,
    DraftReplyParams,
    SearchParams,
    SummarizeThreadParams,
    TriageParams,
)


class TestGmailTriageInbox:
    """Tests for gmail_triage_inbox tool."""

    @pytest.mark.asyncio
    async def test_triage_returns_categorized_emails(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_message_list: list[dict[str, str]],
        sample_full_message: dict[str, Any],
    ):
        """Test successful triage returns categorized results."""
        with (
            patch("gmail_mcp.tools.read.triage.list_messages") as mock_list,
            patch("gmail_mcp.tools.read.triage.get_message") as mock_get,
            patch("gmail_mcp.tools.read.triage.gmail_client", mock_gmail_client),
        ):
            mock_list.return_value = sample_message_list
            mock_get.return_value = sample_full_message

            from gmail_mcp.tools.read.triage import gmail_triage_inbox

            params = TriageParams(max_results=10)
            result = await gmail_triage_inbox(params)

            assert result["status"] == "success"
            # Data contains the triaged emails list directly
            assert isinstance(result["data"], list)
            mock_rate_limiter.consume.assert_called_once()
            mock_audit_logger.log_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_triage_respects_max_results(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test max_results parameter is passed correctly."""
        with (
            patch("gmail_mcp.tools.read.triage.list_messages") as mock_list,
            patch("gmail_mcp.tools.read.triage.gmail_client", mock_gmail_client),
        ):
            mock_list.return_value = []

            from gmail_mcp.tools.read.triage import gmail_triage_inbox

            params = TriageParams(max_results=25)
            await gmail_triage_inbox(params)

            mock_list.assert_called_once()
            call_args = mock_list.call_args
            assert call_args.kwargs["max_results"] == 25


class TestGmailSearch:
    """Tests for gmail_search tool."""

    @pytest.mark.asyncio
    async def test_search_returns_results(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_message_list: list[dict[str, str]],
        sample_full_message: dict[str, Any],
    ):
        """Test successful search returns formatted results."""
        with (
            patch("gmail_mcp.tools.read.search.list_messages") as mock_list,
            patch("gmail_mcp.tools.read.search.get_message") as mock_get,
            patch("gmail_mcp.tools.read.search.gmail_client", mock_gmail_client),
        ):
            mock_list.return_value = sample_message_list
            mock_get.return_value = sample_full_message

            from gmail_mcp.tools.read.search import gmail_search

            params = SearchParams(query="from:test@example.com")
            result = await gmail_search(params)

            assert result["status"] == "success"
            # Data contains the results list directly or results key
            assert result["data"] is not None

    @pytest.mark.asyncio
    async def test_search_sanitizes_query(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test dangerous operators are removed from query."""
        with (
            patch("gmail_mcp.tools.read.search.list_messages") as mock_list,
            patch("gmail_mcp.tools.read.search.gmail_client", mock_gmail_client),
            patch("gmail_mcp.tools.read.search.sanitize_search_query") as mock_sanitize,
        ):
            mock_list.return_value = []
            mock_sanitize.return_value = "safe query"

            from gmail_mcp.tools.read.search import gmail_search

            params = SearchParams(query="has:drive dangerous")
            await gmail_search(params)

            mock_sanitize.assert_called_once_with("has:drive dangerous")


class TestGmailSummarizeThread:
    """Tests for gmail_summarize_thread tool."""

    @pytest.mark.asyncio
    async def test_summarize_returns_thread_content(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_thread: dict[str, Any],
    ):
        """Test thread content is properly formatted for summarization."""
        with (
            patch("gmail_mcp.tools.read.summarize.get_thread") as mock_get,
            patch("gmail_mcp.tools.read.summarize.gmail_client", mock_gmail_client),
        ):
            mock_get.return_value = sample_thread

            from gmail_mcp.tools.read.summarize import gmail_summarize_thread

            params = SummarizeThreadParams(thread_id="thread1")
            result = await gmail_summarize_thread(params)

            assert result["status"] == "success"
            assert result["data"]["thread_id"] == "thread1"
            assert "messages" in result["data"]
            assert "message_count" in result["data"]


class TestGmailDraftReply:
    """Tests for gmail_draft_reply tool."""

    @pytest.mark.asyncio
    async def test_draft_returns_reply_context(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_thread: dict[str, Any],
    ):
        """Test reply context includes suggested recipients."""
        with (
            patch("gmail_mcp.tools.read.draft.get_thread") as mock_get,
            patch("gmail_mcp.tools.read.draft.gmail_client", mock_gmail_client),
        ):
            mock_get.return_value = sample_thread

            from gmail_mcp.tools.read.draft import gmail_draft_reply

            params = DraftReplyParams(thread_id="thread1")
            result = await gmail_draft_reply(params)

            assert result["status"] == "success"
            assert "suggested_to" in result["data"]
            assert "suggested_subject" in result["data"]
            assert result["data"]["suggested_subject"].startswith("Re:")


class TestGmailChatInbox:
    """Tests for gmail_chat_inbox tool."""

    @pytest.mark.asyncio
    async def test_chat_converts_natural_language(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
    ):
        """Test natural language is converted to Gmail query."""
        with (
            patch("gmail_mcp.tools.read.chat.list_messages") as mock_list,
            patch("gmail_mcp.tools.read.chat.gmail_client", mock_gmail_client),
        ):
            mock_list.return_value = []

            from gmail_mcp.tools.read.chat import gmail_chat_inbox

            params = ChatInboxParams(question="show me unread emails")
            result = await gmail_chat_inbox(params)

            assert result["status"] == "success"
            assert "interpreted_query" in result["data"]
            # Should convert "unread" to Gmail query
            assert "is:unread" in result["data"]["interpreted_query"]


class TestGmailApplyLabels:
    """Tests for gmail_apply_labels tool."""

    @pytest.mark.asyncio
    async def test_apply_labels_modifies_messages(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        sample_labels: list[dict[str, str]],
    ):
        """Test labels are applied to messages."""
        with (
            patch("gmail_mcp.tools.read.labels.batch_modify_messages") as mock_modify,
            patch("gmail_mcp.tools.read.labels.list_labels") as mock_list_labels,
            patch("gmail_mcp.tools.read.labels.gmail_client", mock_gmail_client),
        ):
            mock_list_labels.return_value = sample_labels

            from gmail_mcp.tools.read.labels import gmail_apply_labels

            params = ApplyLabelsParams(
                message_ids=["msg1", "msg2"],
                add_labels=["Work"],
                remove_labels=["UNREAD"],
            )
            result = await gmail_apply_labels(params)

            assert result["status"] == "success"
            assert result["data"]["modified_count"] == 2
            mock_modify.assert_called_once()


class TestDownloadEmailParams:
    """Tests for DownloadEmailParams validation."""

    def test_valid_params(self):
        """Test valid parameters are accepted."""
        from gmail_mcp.schemas.tools import DownloadEmailParams

        params = DownloadEmailParams(
            message_id="msg123",
            output_dir="/tmp/receipts",
        )
        assert params.message_id == "msg123"
        assert params.output_dir == "/tmp/receipts"
        assert params.filename_prefix == ""

    def test_custom_prefix(self):
        """Test custom filename prefix."""
        from gmail_mcp.schemas.tools import DownloadEmailParams

        params = DownloadEmailParams(
            message_id="msg123",
            output_dir="/tmp/receipts",
            filename_prefix="anthropic",
        )
        assert params.filename_prefix == "anthropic"

    def test_missing_message_id_raises(self):
        """Test missing message_id raises validation error."""
        from pydantic import ValidationError as PydanticValidationError

        from gmail_mcp.schemas.tools import DownloadEmailParams

        with pytest.raises(PydanticValidationError):
            DownloadEmailParams(output_dir="/tmp/receipts")

    def test_missing_output_dir_raises(self):
        """Test missing output_dir raises validation error."""
        from pydantic import ValidationError as PydanticValidationError

        from gmail_mcp.schemas.tools import DownloadEmailParams

        with pytest.raises(PydanticValidationError):
            DownloadEmailParams(message_id="msg123")


class TestGetRawMessage:
    """Tests for get_raw_message helper."""

    def test_get_raw_message_returns_bytes(
        self,
        mock_gmail_client: MagicMock,
    ):
        """Test get_raw_message returns decoded RFC 2822 bytes."""
        import base64

        from gmail_mcp.gmail.messages import get_raw_message

        raw_email = b"From: test@example.com\r\nSubject: Test\r\n\r\nBody"
        encoded = base64.urlsafe_b64encode(raw_email).decode("ascii")

        mock_service = mock_gmail_client.get_service.return_value
        mock_get = (
            mock_service.users.return_value.messages.return_value.get.return_value
        )
        mock_get.execute.return_value = {
            "id": "msg1",
            "raw": encoded,
        }

        result = get_raw_message(mock_service, "msg1")
        assert result == raw_email

    def test_get_raw_message_raises_on_missing_raw(
        self,
        mock_gmail_client: MagicMock,
    ):
        """Test get_raw_message raises when raw field is missing."""
        from gmail_mcp.gmail.messages import get_raw_message
        from gmail_mcp.utils.errors import GmailAPIError

        mock_service = mock_gmail_client.get_service.return_value
        mock_get = (
            mock_service.users.return_value.messages.return_value.get.return_value
        )
        mock_get.execute.return_value = {
            "id": "msg1",
        }

        with pytest.raises(GmailAPIError, match="No raw data"):
            get_raw_message(mock_service, "msg1")


class TestGetAttachmentData:
    """Tests for get_attachment_data helper."""

    def test_get_attachment_data_returns_bytes(
        self,
        mock_gmail_client: MagicMock,
    ):
        """Test attachment data is decoded from base64."""
        import base64

        from gmail_mcp.gmail.messages import get_attachment_data

        attachment_bytes = b"PDF content here"
        encoded = base64.urlsafe_b64encode(attachment_bytes).decode("ascii")

        mock_service = mock_gmail_client.get_service.return_value
        mock_msgs = mock_service.users.return_value.messages.return_value
        mock_att_get = mock_msgs.attachments.return_value.get.return_value
        mock_att_get.execute.return_value = {
            "data": encoded,
        }

        result = get_attachment_data(mock_service, "msg1", "att1")
        assert result == attachment_bytes


class TestGmailDownloadEmail:
    """Tests for gmail_download_email tool."""

    @pytest.mark.asyncio
    async def test_download_saves_eml_file(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        tmp_path,
    ):
        """Test that .eml file is saved correctly."""
        raw_email = (
            b"From: sender@example.com\r\n"
            b"Subject: Test Receipt\r\n"
            b"Date: Mon, 20 Jan 2025 10:00:00 -0500\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Plain text body"
        )

        with (
            patch("gmail_mcp.tools.read.download.get_raw_message") as mock_raw,
            patch("gmail_mcp.tools.read.download.get_message") as mock_get,
            patch("gmail_mcp.tools.read.download.gmail_client", mock_gmail_client),
        ):
            mock_raw.return_value = raw_email
            mock_get.return_value = {
                "id": "msg1",
                "threadId": "thread1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Receipt"},
                        {"name": "Date", "value": "Mon, 20 Jan 2025 10:00:00 -0500"},
                        {"name": "From", "value": "sender@example.com"},
                    ],
                    "parts": [],
                },
            }

            from gmail_mcp.tools.read.download import gmail_download_email

            params = DownloadEmailParams(
                message_id="msg1",
                output_dir=str(tmp_path),
            )
            result = await gmail_download_email(params)

            assert result["status"] == "success"
            eml_files = list(tmp_path.glob("*.eml"))
            assert len(eml_files) == 1

    @pytest.mark.asyncio
    async def test_download_with_prefix(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        tmp_path,
    ):
        """Test that filename prefix is applied."""
        raw_email = (
            b"From: sender@example.com\r\n"
            b"Subject: Invoice\r\n"
            b"Date: Mon, 20 Jan 2025 10:00:00 -0500\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body"
        )

        with (
            patch("gmail_mcp.tools.read.download.get_raw_message") as mock_raw,
            patch("gmail_mcp.tools.read.download.get_message") as mock_get,
            patch("gmail_mcp.tools.read.download.gmail_client", mock_gmail_client),
        ):
            mock_raw.return_value = raw_email
            mock_get.return_value = {
                "id": "msg1",
                "threadId": "thread1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Invoice"},
                        {"name": "Date", "value": "Mon, 20 Jan 2025 10:00:00 -0500"},
                        {"name": "From", "value": "sender@example.com"},
                    ],
                    "parts": [],
                },
            }

            from gmail_mcp.tools.read.download import gmail_download_email

            params = DownloadEmailParams(
                message_id="msg1",
                output_dir=str(tmp_path),
                filename_prefix="anthropic",
            )
            result = await gmail_download_email(params)

            assert result["status"] == "success"
            eml_files = list(tmp_path.glob("*.eml"))
            assert len(eml_files) == 1
            assert eml_files[0].name.startswith("anthropic_")

    @pytest.mark.asyncio
    async def test_download_creates_output_dir(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        tmp_path,
    ):
        """Test that output directory is created if it doesn't exist."""
        raw_email = (
            b"From: test@example.com\r\n"
            b"Subject: Test\r\n"
            b"Date: Mon, 20 Jan 2025 10:00:00 -0500\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Body"
        )
        nested_dir = tmp_path / "nested" / "dir"

        with (
            patch("gmail_mcp.tools.read.download.get_raw_message") as mock_raw,
            patch("gmail_mcp.tools.read.download.get_message") as mock_get,
            patch("gmail_mcp.tools.read.download.gmail_client", mock_gmail_client),
        ):
            mock_raw.return_value = raw_email
            mock_get.return_value = {
                "id": "msg1",
                "threadId": "thread1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test"},
                        {"name": "Date", "value": "Mon, 20 Jan 2025 10:00:00 -0500"},
                        {"name": "From", "value": "test@example.com"},
                    ],
                    "parts": [],
                },
            }

            from gmail_mcp.tools.read.download import gmail_download_email

            params = DownloadEmailParams(
                message_id="msg1",
                output_dir=str(nested_dir),
            )
            result = await gmail_download_email(params)

            assert result["status"] == "success"
            assert nested_dir.exists()

    @pytest.mark.asyncio
    async def test_download_html_email_saves_html(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        tmp_path,
    ):
        """Test that HTML body is saved as .html file."""
        raw_email = (
            b"From: sender@example.com\r\n"
            b"Subject: HTML Receipt\r\n"
            b"Date: Mon, 20 Jan 2025 10:00:00 -0500\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"\r\n"
            b"<html><body><h1>Receipt</h1><p>$100.00</p></body></html>"
        )

        with (
            patch("gmail_mcp.tools.read.download.get_raw_message") as mock_raw,
            patch("gmail_mcp.tools.read.download.get_message") as mock_get,
            patch("gmail_mcp.tools.read.download.gmail_client", mock_gmail_client),
        ):
            mock_raw.return_value = raw_email
            mock_get.return_value = {
                "id": "msg1",
                "threadId": "thread1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "HTML Receipt"},
                        {"name": "Date", "value": "Mon, 20 Jan 2025 10:00:00 -0500"},
                        {"name": "From", "value": "sender@example.com"},
                    ],
                    "parts": [],
                },
            }

            from gmail_mcp.tools.read.download import gmail_download_email

            params = DownloadEmailParams(
                message_id="msg1",
                output_dir=str(tmp_path),
            )
            result = await gmail_download_email(params)

            assert result["status"] == "success"
            html_files = list(tmp_path.glob("*.html"))
            assert len(html_files) == 1
            content = html_files[0].read_text()
            assert "<h1>Receipt</h1>" in content

    @pytest.mark.asyncio
    async def test_download_error_returns_error_response(
        self,
        mock_gmail_client: MagicMock,
        mock_rate_limiter: MagicMock,
        mock_audit_logger: MagicMock,
        tmp_path,
    ):
        """Test that API errors return error response."""
        from gmail_mcp.utils.errors import GmailAPIError

        with (
            patch("gmail_mcp.tools.read.download.get_raw_message") as mock_raw,
            patch("gmail_mcp.tools.read.download.gmail_client", mock_gmail_client),
        ):
            mock_raw.side_effect = GmailAPIError("Message not found")

            from gmail_mcp.tools.read.download import gmail_download_email

            params = DownloadEmailParams(
                message_id="bad_id",
                output_dir=str(tmp_path),
            )
            result = await gmail_download_email(params)

            assert result["status"] == "error"
            assert "Message not found" in result["error"]

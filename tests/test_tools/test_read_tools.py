"""Tests for read-only Gmail tools."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.schemas.tools import (
    ApplyLabelsParams,
    ChatInboxParams,
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
        with patch("gmail_mcp.tools.read.triage.list_messages") as mock_list, patch(
            "gmail_mcp.tools.read.triage.get_message"
        ) as mock_get, patch(
            "gmail_mcp.tools.read.triage.gmail_client", mock_gmail_client
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
        with patch("gmail_mcp.tools.read.triage.list_messages") as mock_list, patch(
            "gmail_mcp.tools.read.triage.gmail_client", mock_gmail_client
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
        with patch("gmail_mcp.tools.read.search.list_messages") as mock_list, patch(
            "gmail_mcp.tools.read.search.get_message"
        ) as mock_get, patch(
            "gmail_mcp.tools.read.search.gmail_client", mock_gmail_client
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
        with patch("gmail_mcp.tools.read.search.list_messages") as mock_list, patch(
            "gmail_mcp.tools.read.search.gmail_client", mock_gmail_client
        ), patch(
            "gmail_mcp.tools.read.search.sanitize_search_query"
        ) as mock_sanitize:
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
        with patch("gmail_mcp.tools.read.summarize.get_thread") as mock_get, patch(
            "gmail_mcp.tools.read.summarize.gmail_client", mock_gmail_client
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
        with patch("gmail_mcp.tools.read.draft.get_thread") as mock_get, patch(
            "gmail_mcp.tools.read.draft.gmail_client", mock_gmail_client
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
        with patch("gmail_mcp.tools.read.chat.list_messages") as mock_list, patch(
            "gmail_mcp.tools.read.chat.gmail_client", mock_gmail_client
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
        with patch(
            "gmail_mcp.tools.read.labels.batch_modify_messages"
        ) as mock_modify, patch(
            "gmail_mcp.tools.read.labels.list_labels"
        ) as mock_list_labels, patch(
            "gmail_mcp.tools.read.labels.gmail_client", mock_gmail_client
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

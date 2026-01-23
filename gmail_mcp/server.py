"""FastMCP server for Gmail MCP.

This module provides the FastMCP server instance with all 12 tool registrations.
Tools are organized into two categories:

- Read Tools (6): Read-only operations that do not require HITL approval
- Write Tools (6): Destructive operations that require human-in-the-loop approval

The server uses a lifespan context manager to perform cleanup of expired approvals
and stale rate limiter buckets at startup.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

# Import singletons
from gmail_mcp.hitl.manager import approval_manager
from gmail_mcp.middleware.rate_limiter import rate_limiter

# Import schemas
from gmail_mcp.schemas.tools import (
    ApplyLabelsParams,
    ArchiveEmailParams,
    ChatInboxParams,
    CreateLabelParams,
    DeleteEmailParams,
    DraftReplyParams,
    OrganizeLabelsParams,
    SearchParams,
    SendEmailParams,
    SummarizeThreadParams,
    TriageParams,
    UnsubscribeParams,
)

# Import tools
from gmail_mcp.tools import (
    gmail_apply_labels,
    gmail_archive_email,
    gmail_chat_inbox,
    gmail_create_label,
    gmail_delete_email,
    gmail_draft_reply,
    gmail_organize_labels,
    gmail_search,
    gmail_send_email,
    gmail_summarize_thread,
    gmail_triage_inbox,
    gmail_unsubscribe,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Cleanup Resources Helper
# =============================================================================


async def cleanup_resources() -> None:
    """Clean up expired approvals and stale rate limiter buckets.

    This helper function is called during server startup via the lifespan
    context manager. It can also be called directly for testing or manual
    cleanup.

    The function handles exceptions gracefully to ensure both cleanup
    operations are attempted even if one fails.
    """
    try:
        expired_count = approval_manager.cleanup_expired()
        if expired_count > 0:
            logger.info("Cleaned up %d expired approval requests", expired_count)
    except Exception as e:
        logger.warning("Error cleaning up expired approvals: %s", e)

    try:
        stale_count = rate_limiter.cleanup_stale()
        if stale_count > 0:
            logger.info("Cleaned up %d stale rate limiter buckets", stale_count)
    except Exception as e:
        logger.warning("Error cleaning up stale rate limiter buckets: %s", e)


# =============================================================================
# Lifespan Context Manager
# =============================================================================


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Lifespan context manager for server startup/shutdown.

    Performs cleanup of expired approvals and stale rate limiter buckets
    at startup to ensure clean state.

    Args:
        server: The FastMCP server instance.

    Yields:
        Empty context dict (no shared state needed).
    """
    logger.info("Gmail MCP server starting up...")

    # Run cleanup of expired approvals and stale rate limiter buckets
    await cleanup_resources()

    logger.info("Gmail MCP server ready")

    yield {}

    logger.info("Gmail MCP server shutting down...")


# =============================================================================
# Read Tool Wrappers
# =============================================================================


def _register_read_tools(mcp: FastMCP) -> None:
    """Register all read-only tools with the FastMCP server.

    Read tools do not require HITL approval and are marked with:
    - readOnlyHint=True
    - destructiveHint=False
    - idempotentHint=True (most are idempotent)

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool(
        name="gmail_triage_inbox",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def gmail_triage_inbox_tool(
        max_results: int = 50,
        label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Triage inbox by categorizing emails by urgency and importance.

        Analyzes inbox messages and categorizes them into:
        - urgent: Time-sensitive emails requiring immediate attention
        - other: Regular emails (personal, work correspondence)
        - social: Social media notifications
        - newsletter: Marketing emails and newsletters

        Results are sorted by priority (urgent first) then by date (newest first).

        Args:
            max_results: Maximum number of emails to triage (1-500, default 50).
            label_ids: Labels to filter by (default: ["INBOX", "UNREAD"]).

        Returns:
            Categorized email list with priority rankings.
        """
        params = TriageParams(
            max_results=max_results,
            label_ids=label_ids or ["INBOX", "UNREAD"],
        )
        return await gmail_triage_inbox(params)

    @mcp.tool(
        name="gmail_summarize_thread",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def gmail_summarize_thread_tool(thread_id: str) -> dict[str, Any]:
        """Get all messages in a thread for summarization.

        Fetches a full thread with all messages and returns structured
        data suitable for AI summarization. Each message includes headers
        and body content (truncated to prevent token overflow).

        Args:
            thread_id: Gmail thread ID to summarize.

        Returns:
            Thread data with all messages, subjects, and body content.
        """
        params = SummarizeThreadParams(thread_id=thread_id)
        return await gmail_summarize_thread(params)

    @mcp.tool(
        name="gmail_draft_reply",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def gmail_draft_reply_tool(
        thread_id: str,
        context: str | None = None,
    ) -> dict[str, Any]:
        """Get context for drafting a reply to a thread.

        Fetches the latest message in a thread and returns structured
        context to help compose a reply. Includes the original message
        details and suggested reply-to information.

        Args:
            thread_id: Gmail thread ID to reply to.
            context: Optional additional context for reply generation.

        Returns:
            Reply context including original message, suggested recipient,
            and suggested subject line.
        """
        params = DraftReplyParams(thread_id=thread_id, context=context)
        return await gmail_draft_reply(params)

    @mcp.tool(
        name="gmail_search",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def gmail_search_tool(
        query: str,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search emails using Gmail query syntax.

        Executes a search query against the user's Gmail account and returns
        matching messages with metadata and preview snippets.

        Gmail query syntax examples:
        - from:sender@example.com - Messages from specific sender
        - to:recipient@example.com - Messages to specific recipient
        - subject:keyword - Messages with keyword in subject
        - after:2024/01/01 - Messages after date
        - has:attachment - Messages with attachments
        - is:unread - Unread messages
        - label:important - Messages with specific label

        Args:
            query: Gmail search query string.
            max_results: Maximum results to return (1-100, default 20).

        Returns:
            Search results with message metadata and snippets.
        """
        params = SearchParams(query=query, max_results=max_results)
        return await gmail_search(params)

    @mcp.tool(
        name="gmail_chat_inbox",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def gmail_chat_inbox_tool(question: str) -> dict[str, Any]:
        """Answer natural language questions about inbox contents.

        Converts natural language questions into Gmail search queries
        and returns relevant messages. Supports questions like:
        - "Show me unread emails from today"
        - "Find emails about the project meeting"
        - "What emails have attachments?"

        Args:
            question: Natural language question about inbox contents.

        Returns:
            Search results matching the interpreted query.
        """
        params = ChatInboxParams(question=question)
        return await gmail_chat_inbox(params)

    @mcp.tool(
        name="gmail_apply_labels",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
        ),
    )
    async def gmail_apply_labels_tool(
        message_ids: list[str],
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply labels to messages (add or remove).

        Adds and/or removes labels from the specified messages. This operation
        is idempotent - applying the same labels multiple times has no
        additional effect.

        NOTE: This tool does NOT require HITL approval since it only modifies
        labels, not message content.

        Args:
            message_ids: List of message IDs to modify.
            add_labels: Labels to add (names or IDs).
            remove_labels: Labels to remove (names or IDs).

        Returns:
            Result with modified count and label changes.
        """
        params = ApplyLabelsParams(
            message_ids=message_ids,
            add_labels=add_labels or [],
            remove_labels=remove_labels or [],
        )
        return await gmail_apply_labels(params)


# =============================================================================
# Write Tool Wrappers
# =============================================================================


def _register_write_tools(mcp: FastMCP) -> None:
    """Register all write tools with the FastMCP server.

    Write tools require HITL approval and are marked with appropriate
    destructive and idempotent hints.

    Args:
        mcp: The FastMCP server instance.
    """

    @mcp.tool(
        name="gmail_send_email",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
        ),
    )
    async def gmail_send_email_tool(
        to: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to_thread_id: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an email (requires HITL approval).

        Two-step HITL flow:
        1. First call (no approval_id): Returns preview for confirmation
        2. Second call (with approval_id): Sends the email

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body content (plain text or HTML).
            cc: Optional CC recipients.
            bcc: Optional BCC recipients.
            reply_to_thread_id: Thread ID if this is a reply.
            approval_id: Approval ID from step 1 (required for execution).

        Returns:
            Approval request (step 1) or sent message info (step 2).
        """
        params = SendEmailParams(
            to=to,
            subject=subject,
            body=body,
            cc=cc or [],
            bcc=bcc or [],
            reply_to_thread_id=reply_to_thread_id,
            approval_id=approval_id,
        )
        return await gmail_send_email(params)

    @mcp.tool(
        name="gmail_archive_email",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
        ),
    )
    async def gmail_archive_email_tool(
        message_ids: list[str],
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Archive emails by removing from inbox (requires HITL approval).

        Two-step HITL flow:
        1. First call (no approval_id): Returns preview of emails to archive
        2. Second call (with approval_id): Archives the emails

        Archiving removes the INBOX label but keeps the email accessible
        in All Mail.

        Args:
            message_ids: List of message IDs to archive.
            approval_id: Approval ID from step 1 (required for execution).

        Returns:
            Approval request (step 1) or archive result (step 2).
        """
        params = ArchiveEmailParams(
            message_ids=message_ids,
            approval_id=approval_id,
        )
        return await gmail_archive_email(params)

    @mcp.tool(
        name="gmail_delete_email",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
        ),
    )
    async def gmail_delete_email_tool(
        message_ids: list[str],
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete emails by moving to trash (requires HITL approval).

        Two-step HITL flow:
        1. First call (no approval_id): Returns preview of emails to delete
        2. Second call (with approval_id): Moves emails to trash

        WARNING: Emails in trash are permanently deleted after 30 days.

        Args:
            message_ids: List of message IDs to delete.
            approval_id: Approval ID from step 1 (required for execution).

        Returns:
            Approval request (step 1) or delete result (step 2).
        """
        params = DeleteEmailParams(
            message_ids=message_ids,
            approval_id=approval_id,
        )
        return await gmail_delete_email(params)

    @mcp.tool(
        name="gmail_unsubscribe",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
        ),
    )
    async def gmail_unsubscribe_tool(
        message_id: str,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Extract unsubscribe link from email (requires HITL approval).

        Two-step HITL flow:
        1. First call (no approval_id): Returns preview with unsubscribe link
        2. Second call (with approval_id): Returns confirmed unsubscribe info

        Note: Actual unsubscription requires following the returned link.
        This tool extracts and validates the link but cannot automatically
        complete HTTP unsubscribe requests.

        Args:
            message_id: Message ID containing List-Unsubscribe header.
            approval_id: Approval ID from step 1 (required for execution).

        Returns:
            Approval request (step 1) or unsubscribe link info (step 2).
        """
        params = UnsubscribeParams(
            message_id=message_id,
            approval_id=approval_id,
        )
        return await gmail_unsubscribe(params)

    @mcp.tool(
        name="gmail_create_label",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
        ),
    )
    async def gmail_create_label_tool(
        name: str,
        label_list_visibility: str = "labelShow",
        message_list_visibility: str = "show",
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Gmail label (requires HITL approval).

        Two-step HITL flow:
        1. First call (no approval_id): Returns preview of label to create
        2. Second call (with approval_id): Creates the label

        Args:
            name: Label name to create.
            label_list_visibility: Visibility in label list
                (labelShow, labelHide, labelShowIfUnread).
            message_list_visibility: Visibility in message list (show, hide).
            approval_id: Approval ID from step 1 (required for execution).

        Returns:
            Approval request (step 1) or created label info (step 2).
        """
        params = CreateLabelParams(
            name=name,
            label_list_visibility=label_list_visibility,
            message_list_visibility=message_list_visibility,
            approval_id=approval_id,
        )
        return await gmail_create_label(params)

    @mcp.tool(
        name="gmail_organize_labels",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
        ),
    )
    async def gmail_organize_labels_tool(
        operations: list[dict[str, str]],
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        """Perform batch label operations (requires HITL approval).

        Two-step HITL flow:
        1. First call (no approval_id): Returns preview of operations
        2. Second call (with approval_id): Executes all operations

        Supported operations:
        - rename: {"action": "rename", "label_id": "...", "new_name": "..."}
        - delete: {"action": "delete", "label_id": "..."}
        - update_visibility: {"action": "update_visibility", "label_id": "...",
            "visibility": "labelShow|labelHide|labelShowIfUnread"}

        WARNING: Delete operations cannot be undone.

        Args:
            operations: List of operation dicts with action and parameters.
            approval_id: Approval ID from step 1 (required for execution).

        Returns:
            Approval request (step 1) or operation results (step 2).
        """
        params = OrganizeLabelsParams(
            operations=operations,
            approval_id=approval_id,
        )
        return await gmail_organize_labels(params)


# =============================================================================
# Server Factory
# =============================================================================


def create_server() -> FastMCP:
    """Create and configure the FastMCP server instance.

    Creates a FastMCP server with:
    - Lifespan context manager for startup/shutdown cleanup
    - All 12 Gmail tools registered with appropriate annotations

    Returns:
        Configured FastMCP server instance.
    """
    server = FastMCP(
        name="gmail-mcp-server",
        lifespan=server_lifespan,
    )

    _register_read_tools(server)
    _register_write_tools(server)

    logger.info("Gmail MCP server created with 12 tools registered")
    return server


# =============================================================================
# Global Server Instance
# =============================================================================

# Create the global server instance for use by __main__.py
mcp = create_server()

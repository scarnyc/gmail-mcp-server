"""Gmail draft reply context tool.

This read-only tool fetches thread context to help draft a reply.
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import decode_body, parse_headers
from gmail_mcp.gmail.threads import get_thread
from gmail_mcp.middleware.validator import validate_thread_id
from gmail_mcp.schemas.tools import DraftReplyParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)

# Maximum body length for original message context
MAX_BODY_LENGTH = 3000


def _build_reply_subject(original_subject: str) -> str:
    """Build reply subject line.

    Adds 'Re: ' prefix if not already present.

    Args:
        original_subject: Original email subject.

    Returns:
        Subject with 'Re: ' prefix.
    """
    subject = original_subject.strip()
    if not subject:
        return "Re: (no subject)"

    # Don't add Re: if already present
    if subject.lower().startswith("re:"):
        return subject

    return f"Re: {subject}"


def _extract_email_address(from_header: str) -> str:
    """Extract email address from From header.

    Handles formats like:
    - "name@example.com"
    - "John Doe <name@example.com>"

    Args:
        from_header: The From header value.

    Returns:
        Extracted email address or original value if parsing fails.
    """
    from_header = from_header.strip()

    # Check for angle bracket format
    if "<" in from_header and ">" in from_header:
        start = from_header.index("<") + 1
        end = from_header.index(">")
        return from_header[start:end].strip()

    return from_header


async def gmail_draft_reply(
    params: DraftReplyParams, user_id: str = "default"
) -> dict[str, Any]:
    """Get context for drafting a reply to a thread.

    This tool fetches the latest message in a thread and returns structured
    context to help compose a reply. It includes the original message details
    and suggested reply-to information.

    Args:
        params: Parameters containing:
            - thread_id: Thread ID to reply to
            - context: Optional additional context for reply generation

    Returns:
        Success response with reply context including:
        - thread_id: The thread identifier
        - reply_to_message_id: ID of message being replied to
        - original_from: Sender of original message
        - original_to: Recipients of original message
        - original_subject: Subject of original message
        - original_date: Date of original message
        - original_body: Body of original message (truncated)
        - suggested_to: Suggested reply recipient (original sender)
        - suggested_subject: Suggested reply subject (Re: original)
        - thread_message_count: Total messages in thread
        - user_context: User-provided context (if any)

    Raises:
        ValidationError: If thread_id format is invalid.
        GmailAPIError: If Gmail API call fails.
        AuthenticationError: If user is not authenticated.
    """

    def operation() -> dict[str, Any]:
        # Validate thread ID
        thread_id = validate_thread_id(params.thread_id)

        # Get authenticated Gmail service
        service = gmail_client.get_service()

        # Fetch full thread
        thread = get_thread(service, thread_id, format="full")

        # Extract messages
        raw_messages = thread.get("messages", [])

        if not raw_messages:
            return build_success_response(
                data={
                    "thread_id": thread_id,
                    "reply_to_message_id": None,
                    "original_from": "",
                    "original_to": "",
                    "original_subject": "",
                    "original_date": "",
                    "original_body": "",
                    "suggested_to": "",
                    "suggested_subject": "Re: ",
                    "thread_message_count": 0,
                    "user_context": params.context,
                },
                message="Thread is empty - no messages to reply to",
            )

        # Get the latest message (last in list)
        latest_message = raw_messages[-1]
        headers = parse_headers(latest_message)
        body = decode_body(latest_message)

        # Truncate body to prevent token overflow
        if len(body) > MAX_BODY_LENGTH:
            body = body[:MAX_BODY_LENGTH] + "... [truncated]"

        original_from = headers.get("From", "")
        original_subject = headers.get("Subject", "")

        # Build reply context
        reply_context = {
            "thread_id": thread_id,
            "reply_to_message_id": latest_message.get("id", ""),
            "original_from": original_from,
            "original_to": headers.get("To", ""),
            "original_subject": original_subject,
            "original_date": headers.get("Date", ""),
            "original_body": body,
            "suggested_to": _extract_email_address(original_from),
            "suggested_subject": _build_reply_subject(original_subject),
            "thread_message_count": len(raw_messages),
        }

        # Include user context if provided
        if params.context:
            reply_context["user_context"] = params.context

        msg_count = len(raw_messages)
        return build_success_response(
            data=reply_context,
            message=f"Retrieved reply context for thread with {msg_count} messages",
        )

    try:
        return await execute_tool(
            tool_name="gmail_draft_reply",
            params={
                "thread_id": params.thread_id,
                "context": params.context,
            },
            operation=operation,
        )
    except GmailMCPError as e:
        logger.error("Draft reply context failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.exception("Unexpected error in gmail_draft_reply")
        return build_error_response(
            error=f"Unexpected error: {e}",
            error_code="UnexpectedError",
        )

"""Gmail thread summarization tool.

This read-only tool fetches and returns all messages in a thread for summarization.
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import decode_body, parse_headers
from gmail_mcp.gmail.threads import get_thread
from gmail_mcp.middleware.validator import validate_thread_id
from gmail_mcp.schemas.tools import SummarizeThreadParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)

# Maximum body length to return per message
MAX_BODY_LENGTH = 5000


async def gmail_summarize_thread(
    params: SummarizeThreadParams, user_id: str = "default"
) -> dict[str, Any]:
    """Summarize an email thread by returning all messages.

    This tool fetches a full thread with all messages and returns structured
    data suitable for AI summarization. Each message includes headers and
    body content (truncated to prevent token overflow).

    Args:
        params: Parameters containing thread_id to summarize.

    Returns:
        Success response with thread data including:
        - thread_id: The thread identifier
        - subject: Thread subject line
        - message_count: Total messages in thread
        - messages: Array of message objects with id, from, to, date, subject, body

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
                    "subject": "",
                    "message_count": 0,
                    "messages": [],
                },
                message="Thread is empty or contains no messages",
                count=0,
            )

        # Process each message
        messages: list[dict[str, Any]] = []
        subject = ""

        for msg in raw_messages:
            headers = parse_headers(msg)
            body = decode_body(msg)

            # Truncate body to prevent token overflow
            if len(body) > MAX_BODY_LENGTH:
                body = body[:MAX_BODY_LENGTH] + "... [truncated]"

            # Use first message subject as thread subject
            if not subject:
                subject = headers.get("Subject", "")

            messages.append(
                {
                    "id": msg.get("id", ""),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "subject": headers.get("Subject", ""),
                    "body": body,
                }
            )

        return build_success_response(
            data={
                "thread_id": thread_id,
                "subject": subject,
                "message_count": len(messages),
                "messages": messages,
            },
            message=f"Retrieved thread with {len(messages)} messages",
            count=len(messages),
        )

    try:
        return await execute_tool(
            tool_name="gmail_summarize_thread",
            params={"thread_id": params.thread_id},
            operation=operation,
        )
    except GmailMCPError as e:
        logger.error("Summarize thread failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.exception("Unexpected error in gmail_summarize_thread")
        return build_error_response(
            error=f"Unexpected error: {e}",
            error_code="UnexpectedError",
        )

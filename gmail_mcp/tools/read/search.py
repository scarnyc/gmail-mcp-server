"""Gmail search tool.

Searches emails using Gmail's powerful query syntax.
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import get_message, list_messages, parse_headers
from gmail_mcp.middleware.validator import sanitize_search_query
from gmail_mcp.schemas.tools import SearchParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)


async def gmail_search(
    params: SearchParams, user_id: str = "default"
) -> dict[str, Any]:
    """Search emails using Gmail query syntax.

    Executes a search query against the user's Gmail account and returns
    matching messages with metadata and preview snippets.

    Gmail query syntax examples:
    - from:sender@example.com - Messages from specific sender
    - to:recipient@example.com - Messages to specific recipient
    - subject:keyword - Messages with keyword in subject
    - after:2024/01/01 - Messages after date
    - before:2024/12/31 - Messages before date
    - has:attachment - Messages with attachments
    - is:unread - Unread messages
    - label:important - Messages with specific label
    - in:inbox - Messages in inbox
    - "exact phrase" - Messages containing exact phrase

    Args:
        params: Search parameters (query, max_results).
        user_id: User identifier for Gmail authentication.

    Returns:
        Standardized response with search results.

    Example response:
        {
            "status": "success",
            "count": 15,
            "data": [
                {
                    "id": "abc123",
                    "thread_id": "thread456",
                    "from": "sender@example.com",
                    "to": "recipient@example.com",
                    "subject": "Meeting Notes",
                    "date": "2024-01-20T14:30:00Z",
                    "snippet": "Here are the notes from today's meeting...",
                    "labels": ["INBOX", "IMPORTANT"]
                },
                ...
            ],
            "message": "Found 15 messages matching query"
        }
    """

    def _execute() -> dict[str, Any]:
        # Sanitize the search query (removes dangerous operators, validates length)
        sanitized_query = sanitize_search_query(params.query)

        if not sanitized_query:
            return build_error_response(
                error="Search query cannot be empty after sanitization",
                error_code="InvalidQuery",
            )

        # Get Gmail service
        service = gmail_client.get_service(user_id)

        # Execute search
        messages_list = list_messages(
            service=service,
            query=sanitized_query,
            label_ids=None,  # Search across all labels
            max_results=params.max_results,
        )

        if not messages_list:
            return build_success_response(
                data=[],
                message=f"No messages found matching query: {sanitized_query}",
                count=0,
            )

        # Fetch full message details for each result
        search_results: list[dict[str, Any]] = []

        for msg_ref in messages_list:
            message_id = msg_ref.get("id")
            if not message_id:
                continue

            # Get full message metadata
            message = get_message(service, message_id, format="metadata")
            headers = parse_headers(message)

            # Build result entry
            search_results.append(
                {
                    "id": message_id,
                    "thread_id": message.get("threadId", ""),
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": message.get("snippet", ""),
                    "labels": message.get("labelIds", []),
                }
            )

        return build_success_response(
            data=search_results,
            message=f"Found {len(search_results)} messages matching query",
            count=len(search_results),
        )

    try:
        return await execute_tool(
            tool_name="gmail_search",
            params=params.model_dump(),
            operation=_execute,
            user_id=user_id,
        )
    except GmailMCPError as e:
        logger.error("Search failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.exception("Unexpected error in gmail_search")
        return build_error_response(
            error=f"Unexpected error: {e}",
            error_code="UnexpectedError",
        )

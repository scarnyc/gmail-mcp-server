"""Gmail chat inbox tool for natural language queries.

This tool enables conversational queries about inbox contents by converting
natural language questions into Gmail search queries.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import get_message, list_messages, parse_headers
from gmail_mcp.middleware.validator import sanitize_search_query
from gmail_mcp.schemas.tools import ChatInboxParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)


# =============================================================================
# Natural Language Query Patterns
# =============================================================================

# Mapping of natural language patterns to Gmail search operators
NL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Unread messages
    (re.compile(r"\bunread\b", re.IGNORECASE), "is:unread"),
    # From patterns - "from John", "emails from jane@example.com"
    (
        re.compile(
            r"\bfrom\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)",
            re.IGNORECASE,
        ),
        "from:{0}",
    ),
    # To patterns - "to John", "sent to jane@example.com"
    (
        re.compile(
            r"\bto\s+([a-zA-Z0-9._%+-]+(?:@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?)",
            re.IGNORECASE,
        ),
        "to:{0}",
    ),
    # Subject patterns - "subject meeting", "about project"
    (re.compile(r"\bsubject\s+(\w+)", re.IGNORECASE), "subject:{0}"),
    (re.compile(r"\babout\s+(\w+)", re.IGNORECASE), "subject:{0}"),
    # Time-based patterns
    (re.compile(r"\btoday\b", re.IGNORECASE), "newer_than:1d"),
    (re.compile(r"\byesterday\b", re.IGNORECASE), "newer_than:2d older_than:1d"),
    (re.compile(r"\bthis week\b", re.IGNORECASE), "newer_than:7d"),
    (re.compile(r"\blast week\b", re.IGNORECASE), "newer_than:14d older_than:7d"),
    (re.compile(r"\bthis month\b", re.IGNORECASE), "newer_than:30d"),
    (re.compile(r"\blast month\b", re.IGNORECASE), "newer_than:60d older_than:30d"),
    # Attachment patterns
    (re.compile(r"\b(?:has\s+)?attachment[s]?\b", re.IGNORECASE), "has:attachment"),
    (re.compile(r"\bwith\s+file[s]?\b", re.IGNORECASE), "has:attachment"),
    # Important/starred patterns
    (re.compile(r"\bimportant\b", re.IGNORECASE), "is:starred OR is:important"),
    (re.compile(r"\bstarred\b", re.IGNORECASE), "is:starred"),
    # Inbox/location patterns
    (re.compile(r"\bin\s+inbox\b", re.IGNORECASE), "in:inbox"),
    (re.compile(r"\bin\s+sent\b", re.IGNORECASE), "in:sent"),
    (re.compile(r"\bin\s+drafts?\b", re.IGNORECASE), "in:drafts"),
    (re.compile(r"\bin\s+trash\b", re.IGNORECASE), "in:trash"),
    (re.compile(r"\bin\s+spam\b", re.IGNORECASE), "in:spam"),
]


def _natural_language_to_query(question: str) -> str:
    """Convert natural language question to Gmail search query.

    Args:
        question: Natural language question about inbox contents.

    Returns:
        Gmail search query string.
    """
    query_parts: list[str] = []
    processed_question = question

    for pattern, replacement in NL_PATTERNS:
        match = pattern.search(processed_question)
        if match:
            # Handle replacements with captured groups
            if "{0}" in replacement and match.groups():
                query_parts.append(replacement.format(match.group(1)))
            else:
                query_parts.append(replacement)

            # Remove matched portion to avoid double-matching
            processed_question = pattern.sub("", processed_question, count=1)

    # If no patterns matched, treat remaining words as general search terms
    # Extract significant words (nouns, names) for keyword search
    remaining_words = processed_question.strip()
    if remaining_words and not query_parts:
        # Remove common question words
        stop_words = {
            "what",
            "where",
            "when",
            "who",
            "how",
            "is",
            "are",
            "the",
            "a",
            "an",
            "my",
            "me",
            "i",
            "do",
            "does",
            "have",
            "has",
            "any",
            "some",
            "all",
            "show",
            "find",
            "get",
            "list",
            "search",
            "emails",
            "email",
            "messages",
            "message",
            "mail",
            "mails",
            "inbox",
            "can",
            "could",
            "would",
            "please",
        }
        keywords = [
            word
            for word in remaining_words.split()
            if word.lower() not in stop_words and len(word) > 2
        ]
        if keywords:
            query_parts.append(" ".join(keywords))

    # Combine all query parts
    final_query = " ".join(query_parts) if query_parts else ""

    logger.debug("Converted '%s' to query: '%s'", question, final_query)
    return final_query


async def gmail_chat_inbox(
    params: ChatInboxParams, user_id: str = "default"
) -> dict[str, Any]:
    """Answer natural language questions about inbox contents.

    This tool converts natural language questions into Gmail search queries
    and returns relevant messages.

    Supported question patterns:
        - "Show me unread emails from today"
        - "Find emails about the project meeting"
        - "What emails have attachments?"
        - "Emails from john@example.com this week"

    Args:
        params: ChatInboxParams containing the question.

    Returns:
        Success response with question, interpreted_query, and results array,
        or error response if operation fails.
    """

    def _execute() -> dict[str, Any]:
        # Convert natural language to Gmail query
        gmail_query = _natural_language_to_query(params.question)

        # Sanitize the generated query
        if gmail_query:
            gmail_query = sanitize_search_query(gmail_query)

        # Get Gmail service
        service = gmail_client.get_service()

        # List messages matching query
        messages = list_messages(
            service=service,
            query=gmail_query,
            max_results=20,  # Reasonable default for chat responses
        )

        # Fetch full message details
        results: list[dict[str, Any]] = []
        for msg in messages[:10]:  # Limit detail fetching for performance
            try:
                full_message = get_message(service, msg["id"], format="metadata")
                headers = parse_headers(full_message)
                results.append(
                    {
                        "id": msg["id"],
                        "thread_id": full_message.get("threadId"),
                        "from": headers.get("From", ""),
                        "to": headers.get("To", ""),
                        "subject": headers.get("Subject", "(no subject)"),
                        "date": headers.get("Date", ""),
                        "snippet": full_message.get("snippet", ""),
                        "labels": full_message.get("labelIds", []),
                    }
                )
            except GmailMCPError as e:
                logger.warning("Failed to fetch message %s: %s", msg["id"], e)
                continue

        return build_success_response(
            data={
                "question": params.question,
                "interpreted_query": gmail_query or "(all messages)",
                "results": results,
            },
            message=f"Found {len(results)} messages matching your query",
            count=len(results),
        )

    try:
        return await execute_tool(
            tool_name="gmail_chat_inbox",
            params=params.model_dump(),
            operation=_execute,
        )
    except GmailMCPError as e:
        logger.error("Chat inbox query failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.error("Unexpected error in chat inbox: %s", e)
        return build_error_response(
            error="An unexpected error occurred",
            error_code="INTERNAL_ERROR",
        )

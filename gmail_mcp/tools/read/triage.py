"""Gmail inbox triage tool.

Categorizes inbox emails by urgency to help users prioritize their attention.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import get_message, list_messages, parse_headers
from gmail_mcp.schemas.tools import TriageParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)

# =============================================================================
# Categorization Patterns
# =============================================================================

# Keywords indicating urgent emails
URGENT_KEYWORDS = [
    "urgent",
    "asap",
    "immediately",
    "critical",
    "emergency",
    "action required",
    "time sensitive",
    "deadline",
    "important",
    "priority",
]

# Patterns indicating newsletters/marketing (List-Unsubscribe header or common patterns)
NEWSLETTER_PATTERNS = [
    r"unsubscribe",
    r"list-unsubscribe",
    r"email\s*preferences",
    r"opt.?out",
    r"newsletter",
    r"weekly\s*digest",
    r"daily\s*update",
]

# Known social media domains
SOCIAL_DOMAINS = [
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "instagram.com",
    "pinterest.com",
    "tiktok.com",
    "reddit.com",
    "facebookmail.com",
    "linkedin.email",
    "notifications.twitter.com",
]


# =============================================================================
# Categorization Logic
# =============================================================================


def _extract_from_domain(from_header: str) -> str:
    """Extract domain from From header.

    Args:
        from_header: The From header value (e.g., "John Doe <john@example.com>").

    Returns:
        Lowercase domain or empty string if not found.
    """
    match = re.search(r"@([a-zA-Z0-9.-]+)", from_header)
    return match.group(1).lower() if match else ""


def _is_urgent(subject: str, snippet: str) -> bool:
    """Check if email appears urgent based on keywords.

    Args:
        subject: Email subject line.
        snippet: Email snippet/preview.

    Returns:
        True if email contains urgency indicators.
    """
    text = f"{subject} {snippet}".lower()
    return any(keyword in text for keyword in URGENT_KEYWORDS)


def _is_newsletter(message: dict[str, Any]) -> bool:
    """Check if email is a newsletter/marketing email.

    Args:
        message: Full message object from Gmail API.

    Returns:
        True if email appears to be a newsletter.
    """
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    # Check for List-Unsubscribe header (strong indicator)
    for header in headers:
        name = header.get("name", "").lower()
        if name == "list-unsubscribe":
            return True

    # Check subject and snippet for newsletter patterns
    headers_dict = parse_headers(message)
    subject = headers_dict.get("Subject", "")
    snippet = message.get("snippet", "")
    text = f"{subject} {snippet}".lower()

    return any(re.search(pattern, text) for pattern in NEWSLETTER_PATTERNS)


def _is_social(from_header: str) -> bool:
    """Check if email is from a social media platform.

    Args:
        from_header: The From header value.

    Returns:
        True if email is from a known social domain.
    """
    domain = _extract_from_domain(from_header)
    return any(social in domain for social in SOCIAL_DOMAINS)


def _categorize_email(message: dict[str, Any]) -> tuple[str, int]:
    """Categorize an email by type and priority.

    Args:
        message: Full message object from Gmail API.

    Returns:
        Tuple of (category, priority) where priority 1 is highest.
    """
    headers = parse_headers(message)
    subject = headers.get("Subject", "")
    snippet = message.get("snippet", "")
    from_header = headers.get("From", "")

    # Check urgent first (highest priority)
    if _is_urgent(subject, snippet):
        return "urgent", 1

    # Check newsletters
    if _is_newsletter(message):
        return "newsletter", 4

    # Check social
    if _is_social(from_header):
        return "social", 3

    # Default to "other" with medium priority
    return "other", 2


# =============================================================================
# Tool Implementation
# =============================================================================


async def gmail_triage_inbox(
    params: TriageParams, user_id: str = "default"
) -> dict[str, Any]:
    """Triage inbox by categorizing emails based on urgency and importance.

    Analyzes inbox messages and categorizes them into:
    - urgent: Time-sensitive emails requiring immediate attention
    - other: Regular emails (personal, work correspondence)
    - social: Social media notifications
    - newsletter: Marketing emails and newsletters

    Results are sorted by priority (urgent first) then by date (newest first).

    Args:
        params: Triage parameters (max_results, label_ids).
        user_id: User identifier for Gmail authentication.

    Returns:
        Standardized response with categorized email list.

    Example response:
        {
            "status": "success",
            "count": 25,
            "data": [
                {
                    "id": "abc123",
                    "thread_id": "thread456",
                    "from": "boss@company.com",
                    "subject": "URGENT: Meeting in 10 minutes",
                    "date": "2024-01-20T10:30:00Z",
                    "snippet": "Please join the call immediately...",
                    "category": "urgent",
                    "priority": 1
                },
                ...
            ],
            "message": "Triaged 25 emails: 2 urgent, 10 other, 5 social, 8 newsletter"
        }
    """

    def _execute() -> dict[str, Any]:
        # Get Gmail service
        service = gmail_client.get_service(user_id)

        # List messages with specified labels
        messages_list = list_messages(
            service=service,
            query="",
            label_ids=params.label_ids,
            max_results=params.max_results,
        )

        if not messages_list:
            return build_success_response(
                data=[],
                message="No messages found in inbox",
                count=0,
            )

        # Fetch full message details and categorize
        triaged_emails: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {
            "urgent": 0,
            "other": 0,
            "social": 0,
            "newsletter": 0,
        }

        for msg_ref in messages_list:
            message_id = msg_ref.get("id")
            if not message_id:
                continue

            # Get full message
            message = get_message(service, message_id, format="full")
            headers = parse_headers(message)

            # Categorize
            category, priority = _categorize_email(message)
            category_counts[category] = category_counts.get(category, 0) + 1

            # Build result entry
            triaged_emails.append(
                {
                    "id": message_id,
                    "thread_id": message.get("threadId", ""),
                    "from": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": message.get("snippet", ""),
                    "category": category,
                    "priority": priority,
                }
            )

        # Sort by priority (ascending), preserving relative order within priority
        triaged_emails.sort(key=lambda x: x["priority"])

        # Build summary message
        summary_parts = [
            f"{count} {cat}" for cat, count in category_counts.items() if count > 0
        ]
        summary = f"Triaged {len(triaged_emails)} emails: {', '.join(summary_parts)}"

        return build_success_response(
            data=triaged_emails,
            message=summary,
            count=len(triaged_emails),
        )

    try:
        return await execute_tool(
            tool_name="gmail_triage_inbox",
            params=params.model_dump(),
            operation=_execute,
            user_id=user_id,
        )
    except GmailMCPError as e:
        logger.error("Triage failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.exception("Unexpected error in gmail_triage_inbox")
        return build_error_response(
            error=f"Unexpected error: {e}",
            error_code="UnexpectedError",
        )

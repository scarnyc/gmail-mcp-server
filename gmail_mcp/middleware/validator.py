"""Input validation utilities."""

from __future__ import annotations

import logging
import re

from gmail_mcp.utils.errors import ValidationError

logger = logging.getLogger(__name__)

# Regex patterns
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
MESSAGE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]+$")
THREAD_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]+$")

# Dangerous search operators that could leak data
DANGEROUS_OPERATORS = [
    "has:drive",
    "has:document",
    "has:spreadsheet",
    "has:presentation",
]


def validate_email(email: str) -> str:
    """Validate email address format.

    Args:
        email: Email address to validate.

    Returns:
        Validated email address (stripped).

    Raises:
        ValidationError: If email format is invalid.
    """
    email = email.strip()
    if not email:
        raise ValidationError("Email address cannot be empty")

    if not EMAIL_PATTERN.match(email):
        raise ValidationError(f"Invalid email format: {email}")

    if len(email) > 254:
        raise ValidationError("Email address too long (max 254 characters)")

    return email


def validate_email_list(emails: list[str]) -> list[str]:
    """Validate a list of email addresses.

    Args:
        emails: List of email addresses.

    Returns:
        List of validated email addresses.

    Raises:
        ValidationError: If any email is invalid.
    """
    return [validate_email(e) for e in emails]


def validate_message_id(message_id: str) -> str:
    """Validate Gmail message ID format.

    Args:
        message_id: Message ID to validate.

    Returns:
        Validated message ID (stripped).

    Raises:
        ValidationError: If message ID format is invalid.
    """
    message_id = message_id.strip()
    if not message_id:
        raise ValidationError("Message ID cannot be empty")

    if not MESSAGE_ID_PATTERN.match(message_id):
        raise ValidationError(f"Invalid message ID format: {message_id}")

    if len(message_id) > 64:
        raise ValidationError("Message ID too long")

    return message_id


def validate_message_ids(message_ids: list[str]) -> list[str]:
    """Validate a list of message IDs.

    Args:
        message_ids: List of message IDs.

    Returns:
        List of validated message IDs.

    Raises:
        ValidationError: If any message ID is invalid.
    """
    if not message_ids:
        raise ValidationError("Message ID list cannot be empty")

    return [validate_message_id(mid) for mid in message_ids]


def validate_thread_id(thread_id: str) -> str:
    """Validate Gmail thread ID format.

    Args:
        thread_id: Thread ID to validate.

    Returns:
        Validated thread ID (stripped).

    Raises:
        ValidationError: If thread ID format is invalid.
    """
    thread_id = thread_id.strip()
    if not thread_id:
        raise ValidationError("Thread ID cannot be empty")

    if not THREAD_ID_PATTERN.match(thread_id):
        raise ValidationError(f"Invalid thread ID format: {thread_id}")

    if len(thread_id) > 64:
        raise ValidationError("Thread ID too long")

    return thread_id


def sanitize_search_query(query: str) -> str:
    """Sanitize Gmail search query.

    Removes potentially dangerous operators and normalizes whitespace.

    Args:
        query: Search query to sanitize.

    Returns:
        Sanitized search query.

    Raises:
        ValidationError: If query is too long.
    """
    query = query.strip()

    if len(query) > 500:
        raise ValidationError("Search query too long (max 500 characters)")

    # Remove dangerous operators
    for op in DANGEROUS_OPERATORS:
        if op in query.lower():
            logger.warning("Removed dangerous operator from query: %s", op)
            query = re.sub(re.escape(op), "", query, flags=re.IGNORECASE)

    # Normalize whitespace
    query = " ".join(query.split())

    return query


def validate_label_name(name: str) -> str:
    """Validate Gmail label name.

    Args:
        name: Label name to validate.

    Returns:
        Validated label name.

    Raises:
        ValidationError: If label name is invalid.
    """
    name = name.strip()
    if not name:
        raise ValidationError("Label name cannot be empty")

    if len(name) > 225:
        raise ValidationError("Label name too long (max 225 characters)")

    # Gmail doesn't allow these characters in label names
    invalid_chars = ["\\", "/"]
    for char in invalid_chars:
        if char in name and name != "/":  # Allow / for nested labels
            raise ValidationError(f"Label name contains invalid character: {char}")

    return name

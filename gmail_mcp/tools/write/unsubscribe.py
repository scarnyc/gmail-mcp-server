"""Unsubscribe tool for Gmail MCP Server.

This module implements the gmail_unsubscribe tool which extracts unsubscribe
links from email List-Unsubscribe headers and returns them for user action.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import get_message, parse_headers
from gmail_mcp.middleware.validator import validate_message_id
from gmail_mcp.schemas.tools import UnsubscribeParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    compute_params_hash,
    create_approval_request,
    execute_tool,
    validate_and_consume_approval,
)
from gmail_mcp.utils.errors import ApprovalError, GmailAPIError, ValidationError

logger = logging.getLogger(__name__)

# Regex patterns for extracting unsubscribe links
HTTP_LINK_PATTERN = re.compile(r"<(https?://[^>]+)>")
MAILTO_LINK_PATTERN = re.compile(r"<(mailto:[^>]+)>")


def _extract_unsubscribe_link(
    headers_raw: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Extract unsubscribe link from List-Unsubscribe header.

    The List-Unsubscribe header format is typically:
    - <https://example.com/unsubscribe?id=123>
    - <mailto:unsubscribe@example.com?subject=unsubscribe>
    - <https://...>, <mailto:...> (multiple options)

    Args:
        headers_raw: Raw headers list from Gmail API message payload.

    Returns:
        Dict with unsubscribe link info, or None if not found.
        Keys: link, is_mailto, raw_header
    """
    # Find List-Unsubscribe header (case-insensitive)
    list_unsubscribe_value = None
    for header in headers_raw:
        name = header.get("name", "").lower()
        if name == "list-unsubscribe":
            list_unsubscribe_value = header.get("value", "")
            break

    if not list_unsubscribe_value:
        return None

    # Try to extract HTTP link first (preferred)
    http_match = HTTP_LINK_PATTERN.search(list_unsubscribe_value)
    if http_match:
        return {
            "link": http_match.group(1),
            "is_mailto": False,
            "raw_header": list_unsubscribe_value,
        }

    # Fall back to mailto link
    mailto_match = MAILTO_LINK_PATTERN.search(list_unsubscribe_value)
    if mailto_match:
        return {
            "link": mailto_match.group(1),
            "is_mailto": True,
            "raw_header": list_unsubscribe_value,
        }

    # Header exists but no valid link found
    logger.warning(
        "List-Unsubscribe header found but no valid link: %s", list_unsubscribe_value
    )
    return None


async def gmail_unsubscribe(params: UnsubscribeParams) -> dict[str, Any]:
    """Unsubscribe from a mailing list using List-Unsubscribe header.

    This tool implements the HITL two-step flow:
    - Step 1 (no approval_id): Extracts and returns the unsubscribe link for review
    - Step 2 (with approval_id): Confirms and returns the unsubscribe link to follow

    Note: Actual unsubscription requires following the returned link. This tool
    extracts and validates the link but cannot automatically complete HTTP
    unsubscribe requests or send mailto unsubscribe emails.

    Args:
        params: UnsubscribeParams with message_id and optional approval_id.

    Returns:
        Dict with unsubscribe link info or pending approval response.
    """

    def operation() -> dict[str, Any]:
        # Validate message ID
        try:
            validated_message_id = validate_message_id(params.message_id)
        except ValidationError as e:
            return build_error_response(
                error=str(e),
                error_code="VALIDATION_ERROR",
            )

        # Get Gmail service
        try:
            service = gmail_client.get_service()
        except Exception as e:
            logger.error("Failed to get Gmail service: %s", e)
            return build_error_response(
                error="Failed to authenticate with Gmail",
                error_code="AUTH_ERROR",
            )

        # Get message with full headers
        try:
            message = get_message(service, validated_message_id, format="full")
        except GmailAPIError as e:
            return build_error_response(
                error=str(e),
                error_code="GMAIL_API_ERROR",
            )

        # Extract headers
        payload = message.get("payload", {})
        headers_raw = payload.get("headers", [])
        parsed_headers = parse_headers(message)

        # Extract unsubscribe link
        unsubscribe_info = _extract_unsubscribe_link(headers_raw)
        if not unsubscribe_info:
            return build_error_response(
                error="No List-Unsubscribe header found in this email",
                error_code="NO_UNSUBSCRIBE_HEADER",
                details={
                    "message_id": validated_message_id,
                    "from": parsed_headers.get("From", "Unknown"),
                    "subject": parsed_headers.get("Subject", "No Subject"),
                },
            )

        # Step 1: No approval_id - return preview for user confirmation
        if not params.approval_id:
            preview = {
                "message_id": validated_message_id,
                "from": parsed_headers.get("From", "Unknown"),
                "subject": parsed_headers.get("Subject", "No Subject"),
                "unsubscribe_link": unsubscribe_info["link"],
                "is_mailto": unsubscribe_info["is_mailto"],
                "warning": (
                    "This will return the unsubscribe link. "
                    "You will need to follow the link to complete unsubscription."
                    + (
                        " For mailto links, an email must be sent to unsubscribe."
                        if unsubscribe_info["is_mailto"]
                        else ""
                    )
                ),
            }
            return create_approval_request(
                action="unsubscribe",
                preview=preview,
            )

        # Step 2: Validate approval and return unsubscribe info
        # Rebuild the preview to verify parameters haven't been tampered with
        verification_preview = {
            "message_id": validated_message_id,
            "from": parsed_headers.get("From", "Unknown"),
            "subject": parsed_headers.get("Subject", "No Subject"),
            "unsubscribe_link": unsubscribe_info["link"],
            "is_mailto": unsubscribe_info["is_mailto"],
            "warning": (
                "This will return the unsubscribe link. "
                "You will need to follow the link to complete unsubscription."
                + (
                    " For mailto links, an email must be sent to unsubscribe."
                    if unsubscribe_info["is_mailto"]
                    else ""
                )
            ),
        }

        try:
            validate_and_consume_approval(
                params.approval_id,
                expected_action="unsubscribe",
                params_hash=compute_params_hash(verification_preview),
            )
        except ApprovalError as e:
            return build_error_response(
                error=str(e),
                error_code="APPROVAL_ERROR",
            )

        # Return successful unsubscribe info
        return build_success_response(
            data={
                "message_id": validated_message_id,
                "from": parsed_headers.get("From", "Unknown"),
                "subject": parsed_headers.get("Subject", "No Subject"),
                "unsubscribe_link": unsubscribe_info["link"],
                "is_mailto": unsubscribe_info["is_mailto"],
                "action_required": (
                    "Visit the link to complete unsubscription"
                    if not unsubscribe_info["is_mailto"]
                    else "Send an email to the mailto address to unsubscribe"
                ),
            },
            message="Unsubscribe link extracted successfully",
        )

    return await execute_tool(
        tool_name="gmail_unsubscribe",
        params=params.model_dump(exclude_none=True),
        operation=operation,
    )

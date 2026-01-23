"""Gmail archive email tool with HITL approval."""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import batch_modify_messages, get_message, parse_headers
from gmail_mcp.middleware.validator import validate_message_ids
from gmail_mcp.schemas.tools import ArchiveEmailParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    create_approval_request,
    execute_tool,
    validate_and_consume_approval,
)
from gmail_mcp.utils.errors import GmailMCPError, ValidationError

logger = logging.getLogger(__name__)

# Constants
ACTION_NAME = "archive_email"
MAX_PREVIEW_MESSAGES = 5
INBOX_LABEL = "INBOX"


async def gmail_archive_email(params: ArchiveEmailParams) -> dict[str, Any]:
    """Archive emails by removing them from inbox with HITL approval.

    This tool implements a two-step HITL (Human-in-the-Loop) flow:

    Step 1 (no approval_id):
        - Validates message IDs
        - Fetches message previews (up to 5) with id, from, subject, snippet
        - Returns preview for user confirmation

    Step 2 (with approval_id):
        - Validates and consumes the approval
        - Archives messages by removing INBOX label via batch modify
        - Returns count of archived messages

    Args:
        params: ArchiveEmailParams containing:
            - message_ids: List of message IDs to archive
            - approval_id: Optional approval ID from step 1

    Returns:
        dict with either:
            - Approval request (step 1): status, approval_id, preview, message
            - Success response (step 2): status, data with archived_count
            - Error response: status, error, error_code
    """
    try:
        # Validate message IDs upfront
        validated_ids = validate_message_ids(params.message_ids)

        # Step 1: No approval_id - return preview for user confirmation
        if not params.approval_id:
            # Fetch previews for first N messages
            service = gmail_client.get_service()
            previews: list[dict[str, str]] = []

            for msg_id in validated_ids[:MAX_PREVIEW_MESSAGES]:
                try:
                    message = get_message(service, msg_id, format="metadata")
                    headers = parse_headers(message)

                    previews.append(
                        {
                            "id": msg_id,
                            "from": headers.get("From", "Unknown"),
                            "subject": headers.get("Subject", "(no subject)"),
                            "snippet": message.get("snippet", "")[:100],
                        }
                    )
                except GmailMCPError as e:
                    logger.warning("Failed to fetch preview for %s: %s", msg_id, e)
                    previews.append(
                        {
                            "id": msg_id,
                            "from": "Unknown",
                            "subject": "(failed to fetch)",
                            "snippet": "",
                        }
                    )

            preview = {
                "message_count": len(validated_ids),
                "messages": previews,
            }

            # Indicate if there are more messages than shown
            if len(validated_ids) > MAX_PREVIEW_MESSAGES:
                additional = len(validated_ids) - MAX_PREVIEW_MESSAGES
                preview["additional_messages"] = additional

            logger.debug(
                "Creating archive_email approval request for %d messages",
                len(validated_ids),
            )
            return create_approval_request(
                action=ACTION_NAME,
                preview=preview,
            )

        # Step 2: Validate approval and execute archive
        validate_and_consume_approval(params.approval_id, ACTION_NAME)
        logger.info(
            "Approval validated for archive_email, archiving %d messages",
            len(validated_ids),
        )

        # Prepare audit params
        audit_params = {
            "message_ids": validated_ids,
            "message_count": len(validated_ids),
        }

        def _archive_operation() -> dict[str, Any]:
            service = gmail_client.get_service()
            batch_modify_messages(
                service=service,
                message_ids=validated_ids,
                remove_labels=[INBOX_LABEL],
            )
            return {
                "archived_count": len(validated_ids),
                "message_ids": validated_ids,
            }

        result = await execute_tool(
            tool_name="gmail_archive_email",
            params=audit_params,
            operation=_archive_operation,
        )

        logger.info("Archived %d messages successfully", len(validated_ids))
        return build_success_response(
            data=result,
            message=f"Archived {len(validated_ids)} message(s)",
            count=len(validated_ids),
        )

    except ValidationError as e:
        logger.warning("Validation error in archive_email: %s", e)
        return build_error_response(
            error=str(e),
            error_code="VALIDATION_ERROR",
        )
    except GmailMCPError as e:
        logger.error("Gmail MCP error in archive_email: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__.upper(),
        )
    except Exception:
        logger.exception("Unexpected error in archive_email")
        return build_error_response(
            error="An internal error occurred while archiving emails",
            error_code="INTERNAL_ERROR",
        )

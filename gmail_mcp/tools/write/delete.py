"""Gmail delete email tool with HITL approval."""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import get_message, parse_headers, trash_message
from gmail_mcp.middleware.validator import validate_message_ids
from gmail_mcp.schemas.tools import DeleteEmailParams
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
ACTION_NAME = "delete_email"
MAX_PREVIEW_MESSAGES = 5
DELETE_WARNING = (
    "WARNING: This action will move messages to Trash. "
    "Messages in Trash are permanently deleted after 30 days."
)


async def gmail_delete_email(params: DeleteEmailParams) -> dict[str, Any]:
    """Delete emails by moving them to trash with HITL approval.

    This tool implements a two-step HITL (Human-in-the-Loop) flow:

    Step 1 (no approval_id):
        - Validates message IDs
        - Fetches message previews (up to 5) with id, from, subject, snippet
        - Returns preview with deletion warning for user confirmation

    Step 2 (with approval_id):
        - Validates and consumes the approval
        - Moves messages to trash using trash_message for each
        - Returns count of deleted messages and any failures

    Args:
        params: DeleteEmailParams containing:
            - message_ids: List of message IDs to delete
            - approval_id: Optional approval ID from step 1

    Returns:
        dict with either:
            - Approval request (step 1): status, approval_id, preview, message
            - Success response (step 2): status, data with deleted_count
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
                "warning": DELETE_WARNING,
            }

            # Indicate if there are more messages than shown
            if len(validated_ids) > MAX_PREVIEW_MESSAGES:
                additional = len(validated_ids) - MAX_PREVIEW_MESSAGES
                preview["additional_messages"] = additional

            logger.debug(
                "Creating delete_email approval request for %d messages",
                len(validated_ids),
            )
            return create_approval_request(
                action=ACTION_NAME,
                preview=preview,
            )

        # Step 2: Validate approval and execute delete
        validate_and_consume_approval(params.approval_id, ACTION_NAME)
        logger.info(
            "Approval validated for delete_email, deleting %d messages",
            len(validated_ids),
        )

        # Prepare audit params
        audit_params = {
            "message_ids": validated_ids,
            "message_count": len(validated_ids),
        }

        def _delete_operation() -> dict[str, Any]:
            service = gmail_client.get_service()
            deleted_ids: list[str] = []
            failed_ids: list[dict[str, str]] = []

            for msg_id in validated_ids:
                try:
                    trash_message(service, msg_id)
                    deleted_ids.append(msg_id)
                except GmailMCPError as e:
                    logger.warning("Failed to delete message %s: %s", msg_id, e)
                    failed_ids.append({"id": msg_id, "error": str(e)})

            return {
                "deleted_count": len(deleted_ids),
                "deleted_ids": deleted_ids,
                "failed_count": len(failed_ids),
                "failed": failed_ids if failed_ids else None,
            }

        result = await execute_tool(
            tool_name="gmail_delete_email",
            params=audit_params,
            operation=_delete_operation,
        )

        deleted_count = result.get("deleted_count", 0)
        failed_count = result.get("failed_count", 0)

        if failed_count > 0:
            logger.warning(
                "Delete completed with failures: %d deleted, %d failed",
                deleted_count,
                failed_count,
            )
            response_msg = f"Deleted {deleted_count} message(s), {failed_count} failed"
        else:
            logger.info("Deleted %d messages successfully", deleted_count)
            response_msg = f"Deleted {deleted_count} message(s) (moved to Trash)"

        return build_success_response(
            data=result,
            message=response_msg,
            count=deleted_count,
        )

    except ValidationError as e:
        logger.warning("Validation error in delete_email: %s", e)
        return build_error_response(
            error=str(e),
            error_code="VALIDATION_ERROR",
        )
    except GmailMCPError as e:
        logger.error("Gmail MCP error in delete_email: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__.upper(),
        )
    except Exception as e:
        logger.exception("Unexpected error in delete_email")
        return build_error_response(
            error=f"Failed to delete emails: {e}",
            error_code="INTERNAL_ERROR",
        )

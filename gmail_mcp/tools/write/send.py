"""Gmail send email tool with HITL approval."""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import send_message
from gmail_mcp.middleware.validator import (
    validate_email,
    validate_email_list,
    validate_thread_id,
)
from gmail_mcp.schemas.tools import SendEmailParams
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
ACTION_NAME = "send_email"
BODY_PREVIEW_MAX_LENGTH = 500


async def gmail_send_email(params: SendEmailParams) -> dict[str, Any]:
    """Send an email with HITL approval.

    This tool implements a two-step HITL (Human-in-the-Loop) flow:

    Step 1 (no approval_id):
        - Validates email addresses
        - Returns a preview with to, cc, bcc, subject, and truncated body
        - Creates an approval request for user confirmation

    Step 2 (with approval_id):
        - Validates and consumes the approval
        - Sends the email via Gmail API
        - Returns the sent message ID and thread ID

    Args:
        params: SendEmailParams containing:
            - to: Recipient email address
            - subject: Email subject
            - body: Email body content
            - cc: Optional CC recipients
            - bcc: Optional BCC recipients
            - reply_to_thread_id: Optional thread ID for replies
            - approval_id: Optional approval ID from step 1

    Returns:
        dict with either:
            - Approval request (step 1): status, approval_id, preview, message
            - Success response (step 2): status, data with message_id and thread_id
            - Error response: status, error, error_code
    """
    try:
        # Validate email addresses upfront
        validated_to = validate_email(params.to)
        validated_cc = validate_email_list(list(params.cc)) if params.cc else []
        validated_bcc = validate_email_list(list(params.bcc)) if params.bcc else []

        # Validate thread_id if provided
        validated_thread_id: str | None = None
        if params.reply_to_thread_id:
            validated_thread_id = validate_thread_id(params.reply_to_thread_id)

        # Step 1: No approval_id - return preview for user confirmation
        if not params.approval_id:
            # Build preview with truncated body
            body_preview = params.body[:BODY_PREVIEW_MAX_LENGTH]
            if len(params.body) > BODY_PREVIEW_MAX_LENGTH:
                body_preview += "..."

            preview: dict[str, Any] = {
                "to": validated_to,
                "subject": params.subject,
                "body_preview": body_preview,
            }

            # Only include cc/bcc in preview if present
            if validated_cc:
                preview["cc"] = validated_cc
            if validated_bcc:
                preview["bcc"] = validated_bcc
            if validated_thread_id:
                preview["reply_to_thread_id"] = validated_thread_id

            logger.debug("Creating send_email approval request for: %s", validated_to)
            return create_approval_request(
                action=ACTION_NAME,
                preview=preview,
            )

        # Step 2: Validate approval and execute send
        validate_and_consume_approval(params.approval_id, ACTION_NAME)
        logger.info("Approval validated for send_email, proceeding to send")

        # Prepare audit params (exclude sensitive body content)
        audit_params = {
            "to": validated_to,
            "subject": params.subject,
            "cc": validated_cc,
            "bcc": validated_bcc,
            "reply_to_thread_id": validated_thread_id,
            "has_body": bool(params.body),
        }

        def _send_operation() -> dict[str, Any]:
            service = gmail_client.get_service()
            result = send_message(
                service=service,
                to=validated_to,
                subject=params.subject,
                body=params.body,
                cc=validated_cc if validated_cc else None,
                bcc=validated_bcc if validated_bcc else None,
                thread_id=validated_thread_id,
            )
            return {
                "message_id": result.get("id"),
                "thread_id": result.get("threadId"),
            }

        result = await execute_tool(
            tool_name="gmail_send_email",
            params=audit_params,
            operation=_send_operation,
        )

        logger.info("Email sent successfully: %s", result.get("message_id"))
        return build_success_response(
            data=result,
            message=f"Email sent successfully to {validated_to}",
        )

    except ValidationError as e:
        logger.warning("Validation error in send_email: %s", e)
        return build_error_response(
            error=str(e),
            error_code="VALIDATION_ERROR",
        )
    except GmailMCPError as e:
        logger.error("Gmail MCP error in send_email: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__.upper(),
        )
    except Exception as e:
        logger.exception("Unexpected error in send_email")
        return build_error_response(
            error=f"Failed to send email: {e}",
            error_code="INTERNAL_ERROR",
        )

"""Base utilities for Gmail MCP tools.

This module provides shared utilities used by all Gmail MCP tools including:
- Standardized response builders
- Rate limiting and audit logging wrappers
- HITL approval helpers
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from gmail_mcp.hitl.manager import approval_manager
from gmail_mcp.hitl.models import ApprovalRequest, ApprovalResponse
from gmail_mcp.middleware.audit_logger import audit_logger
from gmail_mcp.middleware.rate_limiter import rate_limiter
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Standard Response Keys
# =============================================================================


class ResponseKeys:
    """Standard keys for tool responses."""

    STATUS = "status"
    DATA = "data"
    MESSAGE = "message"
    COUNT = "count"
    ERROR = "error"
    ERROR_CODE = "error_code"


# =============================================================================
# Response Builders
# =============================================================================


def build_success_response(
    data: Any,
    message: str | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    """Build standardized success response.

    Args:
        data: Tool-specific payload.
        message: Optional human-readable message.
        count: Optional item count.

    Returns:
        Standardized success response dict.
    """
    response: dict[str, Any] = {
        ResponseKeys.STATUS: "success",
        ResponseKeys.DATA: data,
    }
    if message:
        response[ResponseKeys.MESSAGE] = message
    if count is not None:
        response[ResponseKeys.COUNT] = count
    return response


def build_error_response(
    error: str,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build standardized error response.

    Args:
        error: Human-readable error message.
        error_code: Optional error code for programmatic handling.
        details: Optional additional error details.

    Returns:
        Standardized error response dict.
    """
    response: dict[str, Any] = {
        ResponseKeys.STATUS: "error",
        ResponseKeys.ERROR: error,
    }
    if error_code:
        response[ResponseKeys.ERROR_CODE] = error_code
    if details:
        response.update(details)
    return response


# =============================================================================
# Tool Execution Wrapper
# =============================================================================


async def execute_tool(
    tool_name: str,
    params: dict[str, Any],
    operation: Callable[[], T],
    user_id: str = "default",
) -> T:
    """Execute a tool with rate limiting and audit logging.

    This wrapper handles:
    1. Rate limit checking and consumption
    2. Operation execution with timing
    3. Audit logging of the tool call

    Args:
        tool_name: Name of the tool being executed.
        params: Tool parameters (for audit logging).
        operation: The actual operation to execute (sync callable).
        user_id: User identifier for rate limiting.

    Returns:
        Result of the operation.

    Raises:
        RateLimitError: If rate limit exceeded.
        GmailMCPError: If operation fails.
    """
    start_time = time.perf_counter()
    result_status = "success"
    error_message: str | None = None

    try:
        # Rate limit check
        rate_limiter.consume(user_id)

        # Execute operation
        result = operation()
        return result

    except GmailMCPError as e:
        result_status = "error"
        error_message = str(e)
        raise
    except Exception as e:
        result_status = "error"
        error_message = str(e)
        raise
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        audit_logger.log_tool_call(
            tool_name=tool_name,
            parameters=params,
            user_id=user_id,
            result_status=result_status,
            error_message=error_message,
            duration_ms=duration_ms,
        )


# =============================================================================
# HITL Approval Helpers
# =============================================================================


def create_approval_request(
    action: str,
    preview: dict[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    """Create and store an approval request, returning response dict.

    This is used in Step 1 of the HITL two-step flow when a write tool
    is called without an approval_id.

    Args:
        action: The action type (e.g., "send_email", "delete_email").
        preview: Action-specific preview data for user review.
        user_id: Optional user identifier.

    Returns:
        ApprovalResponse as dict with pending_approval status.
    """
    # Create request with placeholder expiration (manager will set actual expiry)
    request = ApprovalRequest(
        action=action,
        preview=preview,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        user_id=user_id,
    )
    # Store in manager (this sets the proper expiration based on HITL_TIMEOUT_MS)
    approval_manager.store(request)

    # Return response dict
    return ApprovalResponse.from_request(request).model_dump()


def validate_and_consume_approval(
    approval_id: str,
    expected_action: str,
) -> ApprovalRequest:
    """Validate and consume an approval, raising ApprovalError on failure.

    This is used in Step 2 of the HITL two-step flow when a write tool
    is called with an approval_id.

    Args:
        approval_id: The approval ID from Step 1.
        expected_action: The expected action type for verification.

    Returns:
        The consumed ApprovalRequest.

    Raises:
        ApprovalError: If approval is invalid, expired, or action mismatch.
    """
    # approval_manager.consume() raises ApprovalError on failure
    # The None return is technically unreachable but kept for type safety
    result = approval_manager.consume(approval_id, expected_action=expected_action)
    assert result is not None  # consume() always raises or returns valid request
    return result

"""Human-in-the-loop (HITL) approval system for write operations.

This module provides the HITL approval workflow where write operations
(send, delete, archive, etc.) require explicit user confirmation before
execution.

Usage:
    from gmail_mcp.hitl import approval_manager, ApprovalRequest, ApprovalResponse

    # In a write tool:
    if not approval_id:
        request = ApprovalRequest(
            action="send_email",
            preview={"to": to, "subject": subject},
            expires_at=datetime.utcnow(),  # Will be set by manager
        )
        approval_manager.store(request)
        return ApprovalResponse.from_request(request).model_dump()

    # With approval_id:
    request = approval_manager.consume(approval_id)
    # Execute the action...
"""

from gmail_mcp.hitl.manager import ApprovalManager, approval_manager
from gmail_mcp.hitl.models import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
)

__all__ = [
    "ApprovalManager",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalStatus",
    "approval_manager",
]

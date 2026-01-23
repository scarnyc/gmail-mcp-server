"""Pydantic models for Human-in-the-Loop (HITL) approval system.

This module defines the data models used for the HITL approval workflow,
where write operations require explicit user confirmation before execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    """Status of an approval request.

    Attributes:
        PENDING: Request is awaiting user decision.
        APPROVED: User has approved the action (ready for execution).
        REJECTED: User has explicitly rejected the action.
        EXPIRED: Request timed out before user decision.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest(BaseModel):
    """Model representing a pending approval request for a write operation.

    When a write operation (send, delete, archive, etc.) is invoked without
    an approval_id, the system creates an ApprovalRequest with a preview
    of the action for user review.

    Attributes:
        id: Unique identifier for this approval request (UUID4).
        action: The type of action requiring approval (e.g., "send_email").
        preview: Action-specific data for user to review before approving.
        created_at: Timestamp when the request was created.
        expires_at: Timestamp after which the request is no longer valid.
        status: Current status of the approval request.
        user_id: Optional identifier of the user who initiated the request.

    Example:
        >>> request = ApprovalRequest(
        ...     action="send_email",
        ...     preview={"to": "user@example.com", "subject": "Hello"},
        ...     expires_at=datetime.utcnow() + timedelta(minutes=5),
        ... )
        >>> print(request.id)  # UUID string
    """

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique identifier for this approval request",
    )
    action: str = Field(
        ...,
        description="The type of action requiring approval "
        "(e.g., 'send_email', 'delete_email')",
    )
    preview: dict[str, Any] = Field(
        ...,
        description="Action-specific preview data for user review",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the request was created (UTC)",
    )
    expires_at: datetime = Field(
        ...,
        description="Timestamp after which the request is no longer valid",
    )
    status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING,
        description="Current status of the approval request",
    )
    user_id: str | None = Field(
        default=None,
        description="Optional identifier of the user who initiated the request",
    )
    params_hash: str | None = Field(
        default=None,
        description="SHA-256 hash of critical parameters for verification",
    )

    def is_expired(self) -> bool:
        """Check if the approval request has expired.

        Returns:
            True if current time is past expires_at, False otherwise.
        """
        now = datetime.now(UTC)
        # Handle both timezone-aware and naive datetimes for expires_at
        if self.expires_at.tzinfo is None:
            return now.replace(tzinfo=None) > self.expires_at
        return now > self.expires_at

    def is_valid(self) -> bool:
        """Check if the approval request is still valid for consumption.

        A request is valid if it is pending and not expired.

        Returns:
            True if request can be approved/consumed, False otherwise.
        """
        return self.status == ApprovalStatus.PENDING and not self.is_expired()


class ApprovalResponse(BaseModel):
    """Response model returned when an action requires HITL approval.

    This is the response format returned by write tools when invoked
    without an approval_id, indicating the action was NOT taken and
    requires user confirmation.

    Attributes:
        status: Always "pending_approval" for this response type.
        approval_id: The ID to include in the follow-up call to execute.
        expires_at: ISO format timestamp when the approval expires.
        preview: The action preview data for user review.
        message: Human-readable message explaining the pending state.

    Example:
        >>> response = ApprovalResponse(
        ...     approval_id="abc-123",
        ...     expires_at="2024-01-15T10:30:00Z",
        ...     preview={"to": "user@example.com"},
        ...     message="ACTION NOT TAKEN. Please review and confirm.",
        ... )
    """

    status: str = Field(
        default="pending_approval",
        description="Status indicating action requires approval",
    )
    approval_id: str = Field(
        ...,
        description="The approval ID to include in follow-up call to execute action",
    )
    expires_at: str = Field(
        ...,
        description="ISO format timestamp when this approval expires",
    )
    preview: dict[str, Any] = Field(
        ...,
        description="Action-specific preview data for user review",
    )
    message: str = Field(
        default="ACTION NOT TAKEN. Please review and confirm.",
        description="Human-readable message explaining the pending approval state",
    )

    @classmethod
    def from_request(cls, request: ApprovalRequest) -> ApprovalResponse:
        """Create an ApprovalResponse from an ApprovalRequest.

        Args:
            request: The ApprovalRequest to convert.

        Returns:
            ApprovalResponse with data from the request.
        """
        return cls(
            approval_id=request.id,
            expires_at=request.expires_at.isoformat(),
            preview=request.preview,
        )

"""HITL approval manager for managing approval request lifecycle.

This module provides thread-safe management of approval requests,
including storage, validation, consumption, and automatic cleanup
of expired requests.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime, timedelta

from gmail_mcp.hitl.models import ApprovalRequest, ApprovalStatus
from gmail_mcp.utils.errors import ApprovalError

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Thread-safe manager for HITL approval requests with TTL.

    The ApprovalManager handles the complete lifecycle of approval requests:
    1. Store: Create and store a new approval request with TTL
    2. Validate: Check if an approval_id is valid and not expired
    3. Consume: Validate and remove an approval (one-time use)
    4. Cleanup: Remove expired requests to prevent memory leaks

    Attributes:
        timeout_ms: Timeout in milliseconds for approval requests.

    Example:
        >>> manager = ApprovalManager(timeout_ms=300000)  # 5 minutes
        >>> request = ApprovalRequest(
        ...     action="send_email",
        ...     preview={"to": "user@example.com"},
        ...     expires_at=datetime.utcnow() + timedelta(minutes=5),
        ... )
        >>> approval_id = manager.store(request)
        >>> if manager.validate(approval_id):
        ...     consumed = manager.consume(approval_id)
        ...     # Execute the action
    """

    def __init__(self, timeout_ms: int = 300000) -> None:
        """Initialize the ApprovalManager.

        Args:
            timeout_ms: Timeout in milliseconds for approval requests.
                        Defaults to 300000 (5 minutes).
        """
        self._timeout_ms = timeout_ms
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()
        logger.info(
            "ApprovalManager initialized with timeout_ms=%d (%d seconds)",
            timeout_ms,
            timeout_ms // 1000,
        )

    @property
    def timeout_ms(self) -> int:
        """Get the timeout in milliseconds."""
        return self._timeout_ms

    @property
    def timeout_delta(self) -> timedelta:
        """Get the timeout as a timedelta."""
        return timedelta(milliseconds=self._timeout_ms)

    def store(self, request: ApprovalRequest) -> str:
        """Store an approval request and set its expiration time.

        If the request's expires_at is not set or is in the past,
        it will be updated based on the manager's timeout setting.

        Args:
            request: The ApprovalRequest to store.

        Returns:
            The approval_id (request.id) for later validation/consumption.

        Example:
            >>> request = ApprovalRequest(
            ...     action="send_email",
            ...     preview={"to": "user@example.com"},
            ...     expires_at=datetime.utcnow(),  # Will be updated
            ... )
            >>> approval_id = manager.store(request)
        """
        # Calculate expiration based on timeout (use timezone-aware UTC)
        now = datetime.now(UTC)
        request.expires_at = now + self.timeout_delta
        request.created_at = now
        request.status = ApprovalStatus.PENDING

        with self._lock:
            self._requests[request.id] = request
            logger.debug(
                "Stored approval request: id=%s, action=%s, expires_at=%s",
                request.id,
                request.action,
                request.expires_at.isoformat(),
            )

        return request.id

    def validate(self, approval_id: str) -> bool:
        """Check if an approval_id exists and hasn't expired.

        This method does NOT consume the approval - use consume() for that.

        Args:
            approval_id: The approval ID to validate.

        Returns:
            True if the approval_id exists and is still valid, False otherwise.

        Example:
            >>> if manager.validate(approval_id):
            ...     print("Approval is valid")
            ... else:
            ...     print("Approval is invalid or expired")
        """
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                logger.debug("Validation failed: approval_id=%s not found", approval_id)
                return False

            if request.is_expired():
                logger.debug(
                    "Validation failed: approval_id=%s expired at %s",
                    approval_id,
                    request.expires_at.isoformat(),
                )
                request.status = ApprovalStatus.EXPIRED
                return False

            if request.status != ApprovalStatus.PENDING:
                logger.debug(
                    "Validation failed: approval_id=%s has status %s",
                    approval_id,
                    request.status.value,
                )
                return False

            return True

    def consume(
        self,
        approval_id: str,
        expected_action: str | None = None,
        params_hash: str | None = None,
    ) -> ApprovalRequest | None:
        """Validate and remove an approval request (one-time use).

        If the approval_id is valid and not expired, the request is
        removed from storage and returned. This ensures each approval
        can only be used once.

        Args:
            approval_id: The approval ID to consume.
            expected_action: Optional action type to verify against the stored request.
                           If provided, raises ApprovalError on mismatch.
            params_hash: Optional SHA-256 hash of parameters for tampering detection.
                        If provided and the stored request has a params_hash,
                        they must match.

        Returns:
            The ApprovalRequest if valid and consumed, None if invalid/expired.

        Raises:
            ApprovalError: If the approval_id is invalid, expired, already consumed,
                          action type doesn't match expected_action, or params_hash
                          doesn't match stored hash.

        Example:
            >>> request = manager.consume(approval_id, expected_action="send_email")
            >>> if request:
            ...     # Execute the approved action
            ...     send_email(request.preview)
        """
        with self._lock:
            request = self._requests.get(approval_id)

            if request is None:
                logger.warning("Consume failed: approval_id=%s not found", approval_id)
                raise ApprovalError(
                    "Invalid approval ID",
                    details={"approval_id": approval_id, "reason": "not_found"},
                )

            if request.is_expired():
                logger.warning(
                    "Consume failed: approval_id=%s expired at %s",
                    approval_id,
                    request.expires_at.isoformat(),
                )
                request.status = ApprovalStatus.EXPIRED
                # Remove expired request
                del self._requests[approval_id]
                raise ApprovalError(
                    "Approval has expired",
                    details={
                        "approval_id": approval_id,
                        "reason": "expired",
                        "expired_at": request.expires_at.isoformat(),
                    },
                )

            if request.status != ApprovalStatus.PENDING:
                logger.warning(
                    "Consume failed: approval_id=%s already consumed (status=%s)",
                    approval_id,
                    request.status.value,
                )
                raise ApprovalError(
                    "Approval has already been used",
                    details={
                        "approval_id": approval_id,
                        "reason": "already_consumed",
                        "status": request.status.value,
                    },
                )

            # Verify action type matches if expected_action is provided
            if expected_action and request.action != expected_action:
                logger.warning(
                    "Consume failed: approval_id=%s action mismatch "
                    "(expected=%s, actual=%s)",
                    approval_id,
                    expected_action,
                    request.action,
                )
                raise ApprovalError(
                    "Approval action mismatch",
                    details={
                        "approval_id": approval_id,
                        "reason": "action_mismatch",
                        "expected_action": expected_action,
                        "actual_action": request.action,
                    },
                )

            # Verify params hash if provided
            if params_hash and request.params_hash:
                if params_hash != request.params_hash:
                    logger.warning(
                        "Consume failed: approval_id=%s params hash mismatch",
                        approval_id,
                    )
                    raise ApprovalError(
                        "Approval parameters mismatch",
                        details={
                            "approval_id": approval_id,
                            "reason": "params_hash_mismatch",
                        },
                    )

            # Mark as approved and remove from storage
            request.status = ApprovalStatus.APPROVED
            del self._requests[approval_id]
            logger.info(
                "Consumed approval: id=%s, action=%s",
                approval_id,
                request.action,
            )
            return request

    def cleanup_expired(self) -> int:
        """Remove all expired approval requests.

        This method should be called periodically to prevent memory leaks
        from accumulated expired requests.

        Returns:
            The number of expired requests that were removed.

        Example:
            >>> removed = manager.cleanup_expired()
            >>> print(f"Removed {removed} expired requests")
        """
        now = datetime.now(UTC)
        expired_ids: list[str] = []

        with self._lock:
            for approval_id, request in self._requests.items():
                if now > request.expires_at:
                    expired_ids.append(approval_id)
                    request.status = ApprovalStatus.EXPIRED

            for approval_id in expired_ids:
                del self._requests[approval_id]

        if expired_ids:
            logger.info("Cleaned up %d expired approval requests", len(expired_ids))

        return len(expired_ids)

    def get_pending_count(self) -> int:
        """Get the number of pending approval requests.

        Returns:
            The count of pending (non-expired) requests.
        """
        with self._lock:
            return sum(
                1
                for request in self._requests.values()
                if request.status == ApprovalStatus.PENDING and not request.is_expired()
            )

    def reject(self, approval_id: str) -> ApprovalRequest | None:
        """Explicitly reject an approval request.

        Args:
            approval_id: The approval ID to reject.

        Returns:
            The rejected ApprovalRequest if found, None otherwise.
        """
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                logger.debug("Reject failed: approval_id=%s not found", approval_id)
                return None

            request.status = ApprovalStatus.REJECTED
            del self._requests[approval_id]
            logger.info(
                "Rejected approval: id=%s, action=%s", approval_id, request.action
            )
            return request


def _get_timeout_ms() -> int:
    """Get timeout from environment variable with fallback to default.

    Returns:
        Timeout in milliseconds from HITL_TIMEOUT_MS env var or 300000 (5 min).
    """
    try:
        return int(os.getenv("HITL_TIMEOUT_MS", "300000"))
    except ValueError:
        logger.warning("Invalid HITL_TIMEOUT_MS value, using default 300000")
        return 300000


# Global singleton instance - initialized from environment
approval_manager = ApprovalManager(timeout_ms=_get_timeout_ms())

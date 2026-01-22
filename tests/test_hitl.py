"""Tests for the HITL (Human-in-the-Loop) approval system.

Tests cover:
- ApprovalRequest model creation and validation
- ApprovalResponse model creation
- ApprovalManager lifecycle operations (store, validate, consume, cleanup)
- Thread safety under concurrent access
- Edge cases (expiration, invalid IDs, double consumption)
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

from gmail_mcp.hitl import (
    ApprovalManager,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    approval_manager,
)
from gmail_mcp.utils.errors import ApprovalError


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_status_values(self) -> None:
        """Test that all expected status values exist."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.EXPIRED.value == "expired"


class TestApprovalRequest:
    """Tests for ApprovalRequest model."""

    def test_create_request_with_defaults(self) -> None:
        """Test creating a request with default values."""
        request = ApprovalRequest(
            action="send_email",
            preview={"to": "test@example.com"},
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )

        assert request.action == "send_email"
        assert request.preview == {"to": "test@example.com"}
        assert request.status == ApprovalStatus.PENDING
        assert request.user_id is None
        assert request.id is not None
        assert len(request.id) == 36  # UUID format

    def test_create_request_with_all_fields(self) -> None:
        """Test creating a request with all fields specified."""
        custom_id = "custom-id-123"
        custom_time = datetime(2024, 1, 15, 10, 0, 0)
        expires = datetime(2024, 1, 15, 10, 5, 0)

        request = ApprovalRequest(
            id=custom_id,
            action="delete_email",
            preview={"message_id": "msg123"},
            created_at=custom_time,
            expires_at=expires,
            status=ApprovalStatus.PENDING,
            user_id="user-456",
        )

        assert request.id == custom_id
        assert request.action == "delete_email"
        assert request.created_at == custom_time
        assert request.expires_at == expires
        assert request.user_id == "user-456"

    def test_is_expired_when_not_expired(self) -> None:
        """Test is_expired returns False when request hasn't expired."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )

        assert request.is_expired() is False

    def test_is_expired_when_expired(self) -> None:
        """Test is_expired returns True when request has expired."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow() - timedelta(seconds=1),
        )

        assert request.is_expired() is True

    def test_is_valid_when_pending_and_not_expired(self) -> None:
        """Test is_valid returns True for pending, non-expired request."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            status=ApprovalStatus.PENDING,
        )

        assert request.is_valid() is True

    def test_is_valid_when_expired(self) -> None:
        """Test is_valid returns False for expired request."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow() - timedelta(seconds=1),
            status=ApprovalStatus.PENDING,
        )

        assert request.is_valid() is False

    def test_is_valid_when_not_pending(self) -> None:
        """Test is_valid returns False for non-pending request."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            status=ApprovalStatus.APPROVED,
        )

        assert request.is_valid() is False


class TestApprovalResponse:
    """Tests for ApprovalResponse model."""

    def test_create_response_with_defaults(self) -> None:
        """Test creating a response with default values."""
        response = ApprovalResponse(
            approval_id="abc-123",
            expires_at="2024-01-15T10:30:00",
            preview={"to": "test@example.com"},
        )

        assert response.status == "pending_approval"
        assert response.approval_id == "abc-123"
        assert response.expires_at == "2024-01-15T10:30:00"
        assert response.preview == {"to": "test@example.com"}
        assert response.message == "ACTION NOT TAKEN. Please review and confirm."

    def test_create_response_with_custom_message(self) -> None:
        """Test creating a response with a custom message."""
        response = ApprovalResponse(
            approval_id="abc-123",
            expires_at="2024-01-15T10:30:00",
            preview={},
            message="Custom approval message",
        )

        assert response.message == "Custom approval message"

    def test_from_request(self) -> None:
        """Test creating a response from a request."""
        request = ApprovalRequest(
            id="req-456",
            action="send_email",
            preview={"to": "test@example.com", "subject": "Hello"},
            expires_at=datetime(2024, 1, 15, 10, 30, 0),
        )

        response = ApprovalResponse.from_request(request)

        assert response.approval_id == "req-456"
        assert response.expires_at == "2024-01-15T10:30:00"
        assert response.preview == {"to": "test@example.com", "subject": "Hello"}
        assert response.status == "pending_approval"


class TestApprovalManager:
    """Tests for ApprovalManager."""

    @pytest.fixture
    def manager(self) -> ApprovalManager:
        """Create a fresh ApprovalManager for each test."""
        return ApprovalManager(timeout_ms=60000)  # 1 minute

    def test_init_with_default_timeout(self) -> None:
        """Test manager initializes with default timeout."""
        manager = ApprovalManager()
        assert manager.timeout_ms == 300000  # 5 minutes

    def test_init_with_custom_timeout(self) -> None:
        """Test manager initializes with custom timeout."""
        manager = ApprovalManager(timeout_ms=120000)
        assert manager.timeout_ms == 120000

    def test_timeout_delta_property(self) -> None:
        """Test timeout_delta returns correct timedelta."""
        manager = ApprovalManager(timeout_ms=60000)
        assert manager.timeout_delta == timedelta(milliseconds=60000)

    def test_store_returns_approval_id(self, manager: ApprovalManager) -> None:
        """Test store returns the approval_id."""
        request = ApprovalRequest(
            action="send_email",
            preview={"to": "test@example.com"},
            expires_at=datetime.utcnow(),  # Will be overwritten
        )

        approval_id = manager.store(request)

        assert approval_id == request.id
        assert len(approval_id) == 36  # UUID format

    def test_store_sets_expires_at(self, manager: ApprovalManager) -> None:
        """Test store sets expires_at based on timeout."""
        old_time = datetime(2020, 1, 1)
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=old_time,
        )

        before_store = datetime.now(UTC)
        manager.store(request)
        after_store = datetime.now(UTC)

        # expires_at should be approximately now + timeout
        expected_min = before_store + manager.timeout_delta
        expected_max = after_store + manager.timeout_delta

        assert request.expires_at >= expected_min
        assert request.expires_at <= expected_max

    def test_store_resets_status_to_pending(self, manager: ApprovalManager) -> None:
        """Test store resets status to PENDING."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
            status=ApprovalStatus.APPROVED,  # Will be reset
        )

        manager.store(request)

        assert request.status == ApprovalStatus.PENDING

    def test_validate_returns_true_for_valid_approval(
        self, manager: ApprovalManager
    ) -> None:
        """Test validate returns True for valid, non-expired approval."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        assert manager.validate(approval_id) is True

    def test_validate_returns_false_for_unknown_id(
        self, manager: ApprovalManager
    ) -> None:
        """Test validate returns False for unknown approval_id."""
        assert manager.validate("unknown-id") is False

    def test_validate_returns_false_for_expired_approval(
        self, manager: ApprovalManager
    ) -> None:
        """Test validate returns False for expired approval."""
        # Create manager with very short timeout
        short_manager = ApprovalManager(timeout_ms=1)
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = short_manager.store(request)

        # Wait for expiration
        time.sleep(0.01)

        assert short_manager.validate(approval_id) is False

    def test_validate_does_not_consume(self, manager: ApprovalManager) -> None:
        """Test validate does not remove the approval."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        # Validate multiple times
        assert manager.validate(approval_id) is True
        assert manager.validate(approval_id) is True
        assert manager.validate(approval_id) is True

    def test_consume_returns_request_and_removes(
        self, manager: ApprovalManager
    ) -> None:
        """Test consume returns the request and removes it."""
        request = ApprovalRequest(
            action="send_email",
            preview={"to": "test@example.com"},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        consumed = manager.consume(approval_id)

        assert consumed is not None
        assert consumed.id == approval_id
        assert consumed.action == "send_email"
        assert consumed.status == ApprovalStatus.APPROVED

        # Should not be valid anymore
        assert manager.validate(approval_id) is False

    def test_consume_raises_for_unknown_id(self, manager: ApprovalManager) -> None:
        """Test consume raises ApprovalError for unknown ID."""
        with pytest.raises(ApprovalError) as exc_info:
            manager.consume("unknown-id")

        assert "Invalid approval ID" in str(exc_info.value)
        assert exc_info.value.details["reason"] == "not_found"

    def test_consume_raises_for_expired_approval(
        self, manager: ApprovalManager
    ) -> None:
        """Test consume raises ApprovalError for expired approval."""
        short_manager = ApprovalManager(timeout_ms=1)
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = short_manager.store(request)

        time.sleep(0.01)

        with pytest.raises(ApprovalError) as exc_info:
            short_manager.consume(approval_id)

        assert "expired" in str(exc_info.value).lower()
        assert exc_info.value.details["reason"] == "expired"

    def test_consume_raises_for_double_consumption(
        self, manager: ApprovalManager
    ) -> None:
        """Test consume raises ApprovalError when called twice."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        # First consume succeeds
        manager.consume(approval_id)

        # Second consume fails
        with pytest.raises(ApprovalError) as exc_info:
            manager.consume(approval_id)

        assert "Invalid approval ID" in str(exc_info.value)

    def test_cleanup_expired_removes_expired_requests(
        self, manager: ApprovalManager
    ) -> None:
        """Test cleanup_expired removes expired requests."""
        short_manager = ApprovalManager(timeout_ms=1)

        # Store multiple requests
        for i in range(5):
            request = ApprovalRequest(
                action=f"action_{i}",
                preview={},
                expires_at=datetime.utcnow(),
            )
            short_manager.store(request)

        # Wait for expiration
        time.sleep(0.01)

        removed = short_manager.cleanup_expired()

        assert removed == 5
        assert short_manager.get_pending_count() == 0

    def test_cleanup_expired_preserves_valid_requests(
        self, manager: ApprovalManager
    ) -> None:
        """Test cleanup_expired preserves non-expired requests."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        removed = manager.cleanup_expired()

        assert removed == 0
        assert manager.validate(approval_id) is True

    def test_get_pending_count(self, manager: ApprovalManager) -> None:
        """Test get_pending_count returns correct count."""
        assert manager.get_pending_count() == 0

        for i in range(3):
            request = ApprovalRequest(
                action=f"action_{i}",
                preview={},
                expires_at=datetime.utcnow(),
            )
            manager.store(request)

        assert manager.get_pending_count() == 3

    def test_reject_removes_request(self, manager: ApprovalManager) -> None:
        """Test reject removes the request and marks it rejected."""
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        rejected = manager.reject(approval_id)

        assert rejected is not None
        assert rejected.status == ApprovalStatus.REJECTED
        assert manager.validate(approval_id) is False

    def test_reject_returns_none_for_unknown_id(self, manager: ApprovalManager) -> None:
        """Test reject returns None for unknown ID."""
        result = manager.reject("unknown-id")
        assert result is None


class TestApprovalManagerThreadSafety:
    """Tests for thread safety of ApprovalManager."""

    def test_concurrent_store_and_consume(self) -> None:
        """Test concurrent store and consume operations."""
        manager = ApprovalManager(timeout_ms=60000)
        stored_ids: list[str] = []
        consumed_ids: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def store_requests() -> None:
            for i in range(100):
                request = ApprovalRequest(
                    action=f"action_{i}",
                    preview={},
                    expires_at=datetime.utcnow(),
                )
                try:
                    approval_id = manager.store(request)
                    with lock:
                        stored_ids.append(approval_id)
                except Exception as e:
                    with lock:
                        errors.append(e)

        def consume_requests() -> None:
            for _ in range(100):
                time.sleep(0.001)  # Small delay to let store populate
                with lock:
                    if stored_ids:
                        approval_id = stored_ids.pop(0)
                    else:
                        continue
                try:
                    manager.consume(approval_id)
                    with lock:
                        consumed_ids.append(approval_id)
                except ApprovalError:
                    pass  # Expected for some cases
                except Exception as e:
                    with lock:
                        errors.append(e)

        store_thread = threading.Thread(target=store_requests)
        consume_thread = threading.Thread(target=consume_requests)

        store_thread.start()
        consume_thread.start()

        store_thread.join()
        consume_thread.join()

        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_concurrent_validate_operations(self) -> None:
        """Test concurrent validate operations on the same ID."""
        manager = ApprovalManager(timeout_ms=60000)
        request = ApprovalRequest(
            action="send_email",
            preview={},
            expires_at=datetime.utcnow(),
        )
        approval_id = manager.store(request)

        results: list[bool] = []
        errors: list[Exception] = []

        def validate_repeatedly() -> None:
            for _ in range(100):
                try:
                    result = manager.validate(approval_id)
                    results.append(result)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=validate_repeatedly) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(r is True for r in results)


class TestGlobalApprovalManager:
    """Tests for the global approval_manager singleton."""

    def test_global_manager_exists(self) -> None:
        """Test the global approval_manager is available."""
        assert approval_manager is not None
        assert isinstance(approval_manager, ApprovalManager)

    def test_global_manager_has_default_timeout(self) -> None:
        """Test the global manager has the default or env-configured timeout."""
        # Default is 300000ms (5 minutes) unless HITL_TIMEOUT_MS is set
        assert approval_manager.timeout_ms > 0

"""Tests for tools/base.py utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gmail_mcp.tools.base import (
    ResponseKeys,
    build_error_response,
    build_success_response,
    create_approval_request,
    execute_tool,
    validate_and_consume_approval,
)
from gmail_mcp.utils.errors import ApprovalError, RateLimitError


class TestBuildSuccessResponse:
    """Tests for build_success_response."""

    def test_basic_response(self):
        """Test basic success response with data."""
        result = build_success_response(data={"key": "value"})
        assert result[ResponseKeys.STATUS] == "success"
        assert result[ResponseKeys.DATA] == {"key": "value"}

    def test_response_with_message(self):
        """Test success response with optional message."""
        result = build_success_response(data=[], message="Done")
        assert result[ResponseKeys.MESSAGE] == "Done"

    def test_response_with_count(self):
        """Test success response with optional count."""
        result = build_success_response(data=[], count=5)
        assert result[ResponseKeys.COUNT] == 5

    def test_response_with_all_options(self):
        """Test success response with all options."""
        result = build_success_response(
            data={"items": []},
            message="Found items",
            count=0,
        )
        assert result[ResponseKeys.STATUS] == "success"
        assert result[ResponseKeys.DATA] == {"items": []}
        assert result[ResponseKeys.MESSAGE] == "Found items"
        assert result[ResponseKeys.COUNT] == 0


class TestBuildErrorResponse:
    """Tests for build_error_response."""

    def test_basic_error(self):
        """Test basic error response."""
        result = build_error_response(error="Something went wrong")
        assert result[ResponseKeys.STATUS] == "error"
        assert result[ResponseKeys.ERROR] == "Something went wrong"

    def test_error_with_code(self):
        """Test error response with error code."""
        result = build_error_response(
            error="Not found",
            error_code="NOT_FOUND",
        )
        assert result[ResponseKeys.ERROR_CODE] == "NOT_FOUND"

    def test_error_with_details(self):
        """Test error response with additional details."""
        result = build_error_response(
            error="Validation failed",
            details={"field": "email", "reason": "Invalid format"},
        )
        assert result["field"] == "email"
        assert result["reason"] == "Invalid format"


class TestExecuteTool:
    """Tests for execute_tool wrapper."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, mock_rate_limiter, mock_audit_logger):
        """Test successful tool execution."""
        result = await execute_tool(
            tool_name="test_tool",
            params={"key": "value"},
            operation=lambda: {"result": "ok"},
        )
        assert result == {"result": "ok"}
        mock_rate_limiter.consume.assert_called_once_with("default")
        mock_audit_logger.log_tool_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_audit_logger):
        """Test rate limit error is propagated."""
        with patch("gmail_mcp.tools.base.rate_limiter") as mock_rl:
            mock_rl.consume.side_effect = RateLimitError("Rate limit exceeded")
            with pytest.raises(RateLimitError):
                await execute_tool(
                    tool_name="test_tool",
                    params={},
                    operation=lambda: None,
                )

    @pytest.mark.asyncio
    async def test_custom_user_id(self, mock_rate_limiter, mock_audit_logger):
        """Test custom user_id is used."""
        await execute_tool(
            tool_name="test_tool",
            params={},
            operation=lambda: None,
            user_id="custom_user",
        )
        mock_rate_limiter.consume.assert_called_once_with("custom_user")


class TestHITLHelpers:
    """Tests for HITL helper functions."""

    def test_create_approval_request(self, mock_approval_manager):
        """Test creating an approval request."""
        result = create_approval_request(
            action="send_email",
            preview={"to": "test@example.com"},
        )
        assert result["status"] == "pending_approval"
        assert "approval_id" in result
        assert "expires_at" in result
        assert result["preview"] == {"to": "test@example.com"}
        mock_approval_manager.store.assert_called_once()

    def test_validate_and_consume_approval_success(
        self, mock_approval_manager, valid_approval_request
    ):
        """Test successful approval validation."""
        mock_approval_manager.consume.return_value = valid_approval_request
        result = validate_and_consume_approval(
            approval_id="test-id",
            expected_action="send_email",
        )
        assert result == valid_approval_request
        mock_approval_manager.consume.assert_called_once_with(
            "test-id", expected_action="send_email", params_hash=None
        )

    def test_validate_and_consume_approval_failure(self, mock_approval_manager):
        """Test approval validation failure."""
        # approval_manager.consume() raises ApprovalError on failure
        mock_approval_manager.consume.side_effect = ApprovalError(
            "Invalid approval ID",
            details={"approval_id": "invalid-id", "reason": "not_found"},
        )
        with pytest.raises(ApprovalError) as exc_info:
            validate_and_consume_approval(
                approval_id="invalid-id",
                expected_action="send_email",
            )
        assert "Invalid approval ID" in str(exc_info.value)

"""Custom exception hierarchy for Gmail MCP Server.

This module defines a structured exception hierarchy for handling various
error conditions that may occur during Gmail MCP operations, including
authentication, encryption, approval workflows, and API interactions.
"""

from __future__ import annotations


class GmailMCPError(Exception):
    """Base exception for all Gmail MCP Server errors.

    All custom exceptions in the Gmail MCP Server inherit from this base class,
    enabling consistent error handling and catch-all exception handling patterns.

    Attributes:
        message: Human-readable error description.
        details: Optional dictionary containing additional error context.
    """

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error description.
            details: Optional dictionary containing additional error context.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class AuthenticationError(GmailMCPError):
    """Exception raised for OAuth and credential-related errors.

    This exception is raised when authentication operations fail, such as
    invalid credentials, expired sessions, or OAuth flow failures.

    Examples:
        - OAuth authorization code is invalid or expired
        - User denied OAuth consent
        - Invalid client credentials
        - Session has expired and requires re-authentication
    """

    pass


class TokenError(AuthenticationError):
    """Exception raised for token encryption, decryption, or refresh errors.

    This exception is raised when operations on OAuth tokens fail, including
    encryption, decryption, storage, or refresh operations.

    Examples:
        - Token decryption failed due to invalid key
        - Token refresh failed due to revoked access
        - Token storage/retrieval failed
        - Invalid or corrupted token data
    """

    pass


class ApprovalError(GmailMCPError):
    """Exception raised for HITL approval validation errors.

    This exception is raised when Human-in-the-Loop (HITL) approval
    operations fail, such as invalid, expired, or already-used approval IDs.

    Examples:
        - Approval ID not found
        - Approval has expired
        - Approval has already been used
        - Approval action mismatch
    """

    pass


class RateLimitError(GmailMCPError):
    """Exception raised when rate limits are exceeded.

    This exception is raised when a user or operation exceeds the configured
    rate limits for API calls or tool invocations.

    Attributes:
        retry_after_seconds: Suggested time to wait before retrying.
    """

    def __init__(
        self,
        message: str,
        retry_after_seconds: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize the rate limit exception.

        Args:
            message: Human-readable error description.
            retry_after_seconds: Suggested time to wait before retrying.
            details: Optional dictionary containing additional error context.
        """
        super().__init__(message, details)
        self.retry_after_seconds = retry_after_seconds


class GmailAPIError(GmailMCPError):
    """Exception raised for errors from Gmail API calls.

    This exception wraps errors returned by the Gmail API, providing
    structured access to error codes and response data.

    Attributes:
        status_code: HTTP status code from the API response.
        error_code: Gmail API-specific error code, if available.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize the Gmail API error exception.

        Args:
            message: Human-readable error description.
            status_code: HTTP status code from the API response.
            error_code: Gmail API-specific error code, if available.
            details: Optional dictionary containing additional error context.
        """
        super().__init__(message, details)
        self.status_code = status_code
        self.error_code = error_code


class ValidationError(GmailMCPError):
    """Exception raised for input validation errors.

    This exception is raised when input data fails validation checks,
    such as invalid email addresses, malformed parameters, or missing
    required fields.

    Attributes:
        field: The name of the field that failed validation, if applicable.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Initialize the validation error exception.

        Args:
            message: Human-readable error description.
            field: The name of the field that failed validation.
            details: Optional dictionary containing additional error context.
        """
        super().__init__(message, details)
        self.field = field


__all__ = [
    "GmailMCPError",
    "AuthenticationError",
    "TokenError",
    "ApprovalError",
    "RateLimitError",
    "GmailAPIError",
    "ValidationError",
]

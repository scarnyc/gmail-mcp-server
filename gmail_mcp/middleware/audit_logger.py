"""Audit logging middleware for tool invocations."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    """Model for an audit log entry."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO format timestamp",
    )
    user_id: str = Field(default="default", description="User identifier")
    tool_name: str = Field(..., description="Name of the tool invoked")
    action: str = Field(default="invoke", description="Action type")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool parameters (sensitive data redacted)",
    )
    result_status: str | None = Field(
        default=None,
        description="Result status (success/error)",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if failed",
    )
    duration_ms: float | None = Field(
        default=None,
        description="Execution duration in milliseconds",
    )


class AuditLogger:
    """Audit logger that writes to stderr (STDIO-safe).

    All audit entries are written to stderr as JSON lines,
    ensuring they don't interfere with MCP STDIO communication.
    """

    SENSITIVE_KEYS = {
        "body",
        "password",
        "token",
        "secret",
        "key",
        "credential",
        "access_token",
        "refresh_token",
        "client_secret",
        "client_id",
        "authorization",
        "api_key",
        "auth",
        "bearer",
        "private_key",
    }

    def __init__(self, enabled: bool = True):
        """Initialize audit logger.

        Args:
            enabled: Whether audit logging is enabled.
        """
        self._enabled = enabled
        logger.info("AuditLogger initialized (enabled=%s)", enabled)

    def _redact_sensitive(self, params: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive values from parameters."""
        redacted: dict[str, Any] = {}
        for key, value in params.items():
            if key.lower() in self.SENSITIVE_KEYS:
                if isinstance(value, str) and len(value) > 20:
                    redacted[key] = f"{value[:10]}...[REDACTED]"
                else:
                    redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive(value)
            else:
                redacted[key] = value
        return redacted

    def log(self, entry: AuditEntry) -> None:
        """Write audit entry to stderr.

        Args:
            entry: The audit entry to log.
        """
        if not self._enabled:
            return

        try:
            line = json.dumps({"audit": entry.model_dump()})
            print(line, file=sys.stderr, flush=True)
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    def log_tool_call(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        user_id: str = "default",
        result_status: str | None = None,
        error_message: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log a tool invocation.

        Args:
            tool_name: Name of the tool being invoked.
            parameters: Tool parameters (will be redacted).
            user_id: User identifier.
            result_status: "success" or "error".
            error_message: Error message if failed.
            duration_ms: Execution time in milliseconds.
        """
        entry = AuditEntry(
            user_id=user_id,
            tool_name=tool_name,
            action="invoke",
            parameters=self._redact_sensitive(parameters),
            result_status=result_status,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self.log(entry)

    def log_auth_event(
        self,
        event: str,
        user_id: str = "default",
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Log an authentication event.

        Args:
            event: Event type (login, logout, refresh, etc.)
            user_id: User identifier.
            success: Whether the event succeeded.
            details: Additional event details.
        """
        entry = AuditEntry(
            user_id=user_id,
            tool_name="auth",
            action=event,
            parameters=details or {},
            result_status="success" if success else "error",
        )
        self.log(entry)


# Global singleton
audit_logger = AuditLogger()

"""Middleware module for Gmail MCP server."""

from gmail_mcp.middleware.audit_logger import AuditEntry, AuditLogger, audit_logger
from gmail_mcp.middleware.rate_limiter import RateLimiter, rate_limiter
from gmail_mcp.middleware.validator import (
    sanitize_search_query,
    validate_email,
    validate_email_list,
    validate_label_name,
    validate_message_id,
    validate_message_ids,
    validate_thread_id,
)

__all__ = [
    "RateLimiter",
    "rate_limiter",
    "AuditLogger",
    "AuditEntry",
    "audit_logger",
    "validate_email",
    "validate_email_list",
    "validate_message_id",
    "validate_message_ids",
    "validate_thread_id",
    "sanitize_search_query",
    "validate_label_name",
]

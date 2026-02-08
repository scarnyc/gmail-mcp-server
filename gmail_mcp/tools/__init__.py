"""Gmail MCP tools package.

This package contains all MCP tool implementations for Gmail operations.
Tools are organized into three categories:

- Auth Tools: OAuth authentication operations
- Read Tools: Read-only operations (no HITL required)
- Write Tools: Destructive operations (HITL approval required)
"""

from gmail_mcp.tools.auth import (
    gmail_get_auth_status,
    gmail_login,
    gmail_logout,
)
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    create_approval_request,
    execute_tool,
    validate_and_consume_approval,
)
from gmail_mcp.tools.read import (
    gmail_apply_labels,
    gmail_chat_inbox,
    gmail_download_email,
    gmail_draft_reply,
    gmail_search,
    gmail_summarize_thread,
    gmail_triage_inbox,
)
from gmail_mcp.tools.write import (
    gmail_archive_email,
    gmail_create_label,
    gmail_delete_email,
    gmail_organize_labels,
    gmail_send_email,
    gmail_unsubscribe,
)

__all__ = [
    # Base utilities
    "build_error_response",
    "build_success_response",
    "create_approval_request",
    "execute_tool",
    "validate_and_consume_approval",
    # Auth tools
    "gmail_get_auth_status",
    "gmail_login",
    "gmail_logout",
    # Read tools
    "gmail_apply_labels",
    "gmail_chat_inbox",
    "gmail_download_email",
    "gmail_draft_reply",
    "gmail_search",
    "gmail_summarize_thread",
    "gmail_triage_inbox",
    # Write tools
    "gmail_archive_email",
    "gmail_create_label",
    "gmail_delete_email",
    "gmail_organize_labels",
    "gmail_send_email",
    "gmail_unsubscribe",
]

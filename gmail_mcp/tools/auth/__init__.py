"""Gmail MCP authentication tools package.

This package contains MCP tool implementations for OAuth authentication:

- gmail_login: Two-step device flow authentication
- gmail_logout: Clear stored credentials
- gmail_get_auth_status: Check authentication state
"""

from gmail_mcp.tools.auth.login import gmail_login
from gmail_mcp.tools.auth.logout import gmail_logout
from gmail_mcp.tools.auth.status import gmail_get_auth_status

__all__ = [
    "gmail_login",
    "gmail_logout",
    "gmail_get_auth_status",
]

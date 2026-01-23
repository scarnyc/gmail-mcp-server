"""Write Gmail tools.

All tools in this module require HITL (Human-in-the-Loop) approval
before executing destructive operations.
"""

from gmail_mcp.tools.write.archive import gmail_archive_email
from gmail_mcp.tools.write.delete import gmail_delete_email
from gmail_mcp.tools.write.labels import gmail_create_label, gmail_organize_labels
from gmail_mcp.tools.write.send import gmail_send_email
from gmail_mcp.tools.write.unsubscribe import gmail_unsubscribe

__all__ = [
    "gmail_archive_email",
    "gmail_create_label",
    "gmail_delete_email",
    "gmail_organize_labels",
    "gmail_send_email",
    "gmail_unsubscribe",
]

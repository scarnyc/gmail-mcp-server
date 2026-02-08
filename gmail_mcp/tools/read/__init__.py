"""Read-only Gmail tools.

These tools perform read-only operations and do not require HITL approval.
"""

from gmail_mcp.tools.read.chat import gmail_chat_inbox
from gmail_mcp.tools.read.download import gmail_download_email
from gmail_mcp.tools.read.draft import gmail_draft_reply
from gmail_mcp.tools.read.labels import gmail_apply_labels
from gmail_mcp.tools.read.search import gmail_search
from gmail_mcp.tools.read.summarize import gmail_summarize_thread
from gmail_mcp.tools.read.triage import gmail_triage_inbox

__all__ = [
    "gmail_apply_labels",
    "gmail_chat_inbox",
    "gmail_download_email",
    "gmail_draft_reply",
    "gmail_search",
    "gmail_summarize_thread",
    "gmail_triage_inbox",
]

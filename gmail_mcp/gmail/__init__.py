"""Gmail API operations module."""

from gmail_mcp.gmail.client import GmailClient, gmail_client
from gmail_mcp.gmail.labels import (
    create_label,
    delete_label,
    get_label,
    get_label_by_name,
    list_labels,
    update_label,
)
from gmail_mcp.gmail.messages import (
    batch_modify_messages,
    decode_body,
    delete_message,
    get_message,
    list_messages,
    modify_message,
    parse_headers,
    send_message,
    trash_message,
)
from gmail_mcp.gmail.threads import (
    delete_thread,
    get_thread,
    list_threads,
    modify_thread,
    trash_thread,
)

__all__ = [
    "GmailClient",
    "gmail_client",
    "list_messages",
    "get_message",
    "send_message",
    "modify_message",
    "trash_message",
    "delete_message",
    "batch_modify_messages",
    "parse_headers",
    "decode_body",
    "list_threads",
    "get_thread",
    "modify_thread",
    "trash_thread",
    "delete_thread",
    "list_labels",
    "get_label",
    "create_label",
    "update_label",
    "delete_label",
    "get_label_by_name",
]

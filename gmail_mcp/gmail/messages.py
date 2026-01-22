"""Gmail message operations."""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import Resource

from gmail_mcp.utils.errors import GmailAPIError

logger = logging.getLogger(__name__)


def list_messages(
    service: Resource,
    query: str = "",
    label_ids: list[str] | None = None,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """List messages matching query and labels."""
    try:
        messages: list[dict[str, Any]] = []
        request = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                labelIds=label_ids or [],
                maxResults=min(max_results, 500),
            )
        )

        while request and len(messages) < max_results:
            response = request.execute()
            messages.extend(response.get("messages", []))
            request = service.users().messages().list_next(request, response)

        logger.debug("Listed %d messages", len(messages))
        return messages[:max_results]

    except Exception as e:
        logger.error("Failed to list messages: %s", e)
        raise GmailAPIError(f"Failed to list messages: {e}") from e


def get_message(
    service: Resource, message_id: str, format: str = "full"
) -> dict[str, Any]:
    """Get a specific message by ID."""
    try:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format=format)
            .execute()
        )
        logger.debug("Retrieved message %s", message_id)
        return message
    except Exception as e:
        logger.error("Failed to get message %s: %s", message_id, e)
        raise GmailAPIError(f"Failed to get message {message_id}: {e}") from e


def send_message(
    service: Resource,
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    thread_id: str | None = None,
    html: bool = False,
) -> dict[str, Any]:
    """Send an email message."""
    try:
        message: MIMEText | MIMEMultipart
        if html:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "html"))
        else:
            message = MIMEText(body)

        message["to"] = to
        message["subject"] = subject
        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body_dict: dict[str, Any] = {"raw": raw}
        if thread_id:
            body_dict["threadId"] = thread_id

        sent = service.users().messages().send(userId="me", body=body_dict).execute()
        logger.info("Sent message %s to %s", sent["id"], to)
        return sent
    except Exception as e:
        logger.error("Failed to send message to %s: %s", to, e)
        raise GmailAPIError(f"Failed to send message: {e}") from e


def modify_message(
    service: Resource,
    message_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Modify message labels."""
    try:
        body = {"addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []}
        modified = (
            service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
            .execute()
        )
        logger.debug("Modified labels on message %s", message_id)
        return modified
    except Exception as e:
        logger.error("Failed to modify message %s: %s", message_id, e)
        raise GmailAPIError(f"Failed to modify message {message_id}: {e}") from e


def trash_message(service: Resource, message_id: str) -> dict[str, Any]:
    """Move message to trash."""
    try:
        trashed = service.users().messages().trash(userId="me", id=message_id).execute()
        logger.info("Trashed message %s", message_id)
        return trashed
    except Exception as e:
        logger.error("Failed to trash message %s: %s", message_id, e)
        raise GmailAPIError(f"Failed to trash message {message_id}: {e}") from e


def delete_message(service: Resource, message_id: str) -> None:
    """Permanently delete a message."""
    try:
        service.users().messages().delete(userId="me", id=message_id).execute()
        logger.info("Permanently deleted message %s", message_id)
    except Exception as e:
        logger.error("Failed to delete message %s: %s", message_id, e)
        raise GmailAPIError(f"Failed to delete message {message_id}: {e}") from e


def batch_modify_messages(
    service: Resource,
    message_ids: list[str],
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> None:
    """Batch modify labels on multiple messages."""
    try:
        body = {
            "ids": message_ids,
            "addLabelIds": add_labels or [],
            "removeLabelIds": remove_labels or [],
        }
        service.users().messages().batchModify(userId="me", body=body).execute()
        logger.info("Batch modified %d messages", len(message_ids))
    except Exception as e:
        logger.error("Failed to batch modify messages: %s", e)
        raise GmailAPIError(f"Failed to batch modify messages: {e}") from e


def parse_headers(message: dict[str, Any]) -> dict[str, str]:
    """Extract common headers from message payload."""
    headers = {}
    payload = message.get("payload", {})
    for header in payload.get("headers", []):
        name = header.get("name", "").lower()
        if name in ("from", "to", "subject", "date", "cc", "bcc"):
            headers[name.capitalize()] = header.get("value", "")
    return headers


def _safe_base64_decode(data: str) -> str:
    """Safely decode base64 data with error handling.

    Args:
        data: Base64 encoded string.

    Returns:
        Decoded string, or empty string if decoding fails.
    """
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError) as e:
        logger.warning("Failed to decode base64 body data: %s", e)
        return ""


def decode_body(message: dict[str, Any]) -> str:
    """Decode message body from base64."""
    payload = message.get("payload", {})

    # Simple message
    if "body" in payload and payload["body"].get("data"):
        return _safe_base64_decode(payload["body"]["data"])

    # Multipart - find text/plain or text/html
    parts = payload.get("parts", [])
    for part in parts:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain" and part.get("body", {}).get("data"):
            return _safe_base64_decode(part["body"]["data"])

    for part in parts:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/html" and part.get("body", {}).get("data"):
            return _safe_base64_decode(part["body"]["data"])

    # Nested multipart
    for part in parts:
        if "parts" in part:
            result = decode_body({"payload": part})
            if result:
                return result

    return ""

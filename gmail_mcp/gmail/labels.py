"""Gmail label operations."""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import Resource

from gmail_mcp.utils.errors import GmailAPIError

logger = logging.getLogger(__name__)


def list_labels(service: Resource) -> list[dict[str, Any]]:
    """List all labels in the mailbox."""
    try:
        response = service.users().labels().list(userId="me").execute()
        labels = response.get("labels", [])
        logger.debug("Listed %d labels", len(labels))
        return labels
    except Exception as e:
        logger.error("Failed to list labels: %s", e)
        raise GmailAPIError(f"Failed to list labels: {e}") from e


def get_label(service: Resource, label_id: str) -> dict[str, Any]:
    """Get a specific label by ID."""
    try:
        label = service.users().labels().get(userId="me", id=label_id).execute()
        logger.debug("Retrieved label %s (%s)", label_id, label.get("name"))
        return label
    except Exception as e:
        logger.error("Failed to get label %s: %s", label_id, e)
        raise GmailAPIError(f"Failed to get label {label_id}: {e}") from e


def create_label(
    service: Resource,
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
    background_color: str | None = None,
    text_color: str | None = None,
) -> dict[str, Any]:
    """Create a new label."""
    try:
        body: dict[str, Any] = {
            "name": name,
            "labelListVisibility": label_list_visibility,
            "messageListVisibility": message_list_visibility,
        }
        if background_color or text_color:
            body["color"] = {}
            if background_color:
                body["color"]["backgroundColor"] = background_color
            if text_color:
                body["color"]["textColor"] = text_color

        label = service.users().labels().create(userId="me", body=body).execute()
        logger.info("Created label %s (%s)", label["id"], name)
        return label
    except Exception as e:
        logger.error("Failed to create label %s: %s", name, e)
        raise GmailAPIError(f"Failed to create label {name}: {e}") from e


def update_label(
    service: Resource,
    label_id: str,
    name: str | None = None,
    label_list_visibility: str | None = None,
    message_list_visibility: str | None = None,
    background_color: str | None = None,
    text_color: str | None = None,
) -> dict[str, Any]:
    """Update an existing label."""
    try:
        existing = get_label(service, label_id)
        existing_visibility = existing.get("labelListVisibility")
        existing_msg_visibility = existing.get("messageListVisibility")
        body: dict[str, Any] = {
            "name": name if name is not None else existing.get("name"),
            "labelListVisibility": label_list_visibility or existing_visibility,
            "messageListVisibility": message_list_visibility or existing_msg_visibility,
        }
        existing_color = existing.get("color", {})
        if background_color is not None or text_color is not None:
            existing_bg = existing_color.get("backgroundColor")
            body["color"] = {
                "backgroundColor": background_color or existing_bg,
                "textColor": text_color or existing_color.get("textColor"),
            }
        elif existing_color:
            body["color"] = existing_color

        label = (
            service.users()
            .labels()
            .update(userId="me", id=label_id, body=body)
            .execute()
        )
        logger.info("Updated label %s", label_id)
        return label
    except GmailAPIError:
        raise
    except Exception as e:
        logger.error("Failed to update label %s: %s", label_id, e)
        raise GmailAPIError(f"Failed to update label {label_id}: {e}") from e


def delete_label(service: Resource, label_id: str) -> None:
    """Delete a label."""
    try:
        service.users().labels().delete(userId="me", id=label_id).execute()
        logger.info("Deleted label %s", label_id)
    except Exception as e:
        logger.error("Failed to delete label %s: %s", label_id, e)
        raise GmailAPIError(f"Failed to delete label {label_id}: {e}") from e


def get_label_by_name(service: Resource, name: str) -> dict[str, Any] | None:
    """Find a label by name."""
    labels = list_labels(service)
    for label in labels:
        if label.get("name") == name:
            return label
    return None

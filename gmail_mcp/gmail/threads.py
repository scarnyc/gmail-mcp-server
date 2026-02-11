"""Gmail thread operations."""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import Resource

from gmail_mcp.utils.errors import GmailAPIError

logger = logging.getLogger(__name__)


def list_threads(
    service: Resource,
    query: str = "",
    label_ids: list[str] | None = None,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """List threads matching query and labels."""
    try:
        threads: list[dict[str, Any]] = []
        # Merge label_ids into the q parameter as label: filters instead of
        # using the labelIds parameter.  The google-api-python-client's
        # list_next() pagination helper calls parse_unique_urlencoded() which
        # raises ValueError on repeated URL keys like labelIds=INBOX&labelIds=UNREAD.
        combined_query = query
        if label_ids:
            label_filters = " ".join(f"label:{lid}" for lid in label_ids)
            combined_query = f"{query} {label_filters}".strip()
        request = (
            service.users()
            .threads()
            .list(userId="me", q=combined_query, maxResults=min(max_results, 500))
        )

        while request and len(threads) < max_results:
            response = request.execute()
            threads.extend(response.get("threads", []))
            request = service.users().threads().list_next(request, response)

        logger.debug("Listed %d threads", len(threads))
        return threads[:max_results]
    except Exception as e:
        logger.error("Failed to list threads: %s", e)
        raise GmailAPIError(f"Failed to list threads: {e}") from e


def get_thread(
    service: Resource, thread_id: str, format: str = "full"
) -> dict[str, Any]:
    """Get a thread with all its messages."""
    try:
        thread = (
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format=format)
            .execute()
        )
        msg_count = len(thread.get("messages", []))
        logger.debug("Retrieved thread %s with %d messages", thread_id, msg_count)
        return thread
    except Exception as e:
        logger.error("Failed to get thread %s: %s", thread_id, e)
        raise GmailAPIError(f"Failed to get thread {thread_id}: {e}") from e


def modify_thread(
    service: Resource,
    thread_id: str,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Modify labels on all messages in a thread."""
    try:
        body = {"addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []}
        modified = (
            service.users()
            .threads()
            .modify(userId="me", id=thread_id, body=body)
            .execute()
        )
        logger.debug("Modified labels on thread %s", thread_id)
        return modified
    except Exception as e:
        logger.error("Failed to modify thread %s: %s", thread_id, e)
        raise GmailAPIError(f"Failed to modify thread {thread_id}: {e}") from e


def trash_thread(service: Resource, thread_id: str) -> dict[str, Any]:
    """Move entire thread to trash."""
    try:
        trashed = service.users().threads().trash(userId="me", id=thread_id).execute()
        logger.info("Trashed thread %s", thread_id)
        return trashed
    except Exception as e:
        logger.error("Failed to trash thread %s: %s", thread_id, e)
        raise GmailAPIError(f"Failed to trash thread {thread_id}: {e}") from e


def delete_thread(service: Resource, thread_id: str) -> None:
    """Permanently delete a thread."""
    try:
        service.users().threads().delete(userId="me", id=thread_id).execute()
        logger.info("Permanently deleted thread %s", thread_id)
    except Exception as e:
        logger.error("Failed to delete thread %s: %s", thread_id, e)
        raise GmailAPIError(f"Failed to delete thread {thread_id}: {e}") from e

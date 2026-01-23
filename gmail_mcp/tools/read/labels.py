"""Gmail label application tool.

This tool applies labels to messages in bulk. It is idempotent and does NOT
require HITL approval since it only modifies labels (not message content).
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.labels import list_labels
from gmail_mcp.gmail.messages import batch_modify_messages
from gmail_mcp.middleware.validator import validate_message_ids
from gmail_mcp.schemas.tools import ApplyLabelsParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError, ValidationError

logger = logging.getLogger(__name__)


def _resolve_label_ids(
    service: Any,
    label_names_or_ids: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Resolve label names to Gmail label IDs.

    Supports both label names and direct label IDs. For names, performs a
    lookup against the user's label list.

    Args:
        service: Gmail API service resource.
        label_names_or_ids: List of label names or IDs to resolve.

    Returns:
        Tuple of (resolved_label_ids, name_to_id_mapping).

    Raises:
        ValidationError: If a label name cannot be resolved.
    """
    if not label_names_or_ids:
        return [], {}

    # Fetch all labels once
    all_labels = list_labels(service)

    # Build lookup maps
    id_to_label: dict[str, dict[str, Any]] = {
        label["id"]: label for label in all_labels
    }
    name_to_label: dict[str, dict[str, Any]] = {
        label["name"].lower(): label for label in all_labels
    }

    resolved_ids: list[str] = []
    name_mapping: dict[str, str] = {}

    for label_ref in label_names_or_ids:
        # Check if it's already a valid label ID
        if label_ref in id_to_label:
            resolved_ids.append(label_ref)
            name_mapping[label_ref] = id_to_label[label_ref]["name"]
            continue

        # Try to resolve by name (case-insensitive)
        label_lower = label_ref.lower()
        if label_lower in name_to_label:
            label_id = name_to_label[label_lower]["id"]
            resolved_ids.append(label_id)
            name_mapping[label_ref] = name_to_label[label_lower]["name"]
            continue

        # Check for system labels (INBOX, UNREAD, STARRED, etc.)
        system_labels = {
            "inbox": "INBOX",
            "unread": "UNREAD",
            "starred": "STARRED",
            "important": "IMPORTANT",
            "sent": "SENT",
            "draft": "DRAFT",
            "trash": "TRASH",
            "spam": "SPAM",
            "category_personal": "CATEGORY_PERSONAL",
            "category_social": "CATEGORY_SOCIAL",
            "category_promotions": "CATEGORY_PROMOTIONS",
            "category_updates": "CATEGORY_UPDATES",
            "category_forums": "CATEGORY_FORUMS",
        }

        if label_lower in system_labels:
            system_id = system_labels[label_lower]
            resolved_ids.append(system_id)
            name_mapping[label_ref] = system_id
            continue

        # Label not found
        raise ValidationError(
            f"Label not found: '{label_ref}'. Please provide a valid label name or ID."
        )

    return resolved_ids, name_mapping


async def gmail_apply_labels(
    params: ApplyLabelsParams, user_id: str = "default"
) -> dict[str, Any]:
    """Apply labels to messages.

    Adds and/or removes labels from the specified messages. This operation
    is idempotent - applying the same labels multiple times has no additional
    effect.

    NOTE: This tool does NOT require HITL approval since it only modifies
    labels, not message content.

    Args:
        params: ApplyLabelsParams with message_ids, add_labels, remove_labels.

    Returns:
        Success response with modified_count, labels_added, labels_removed,
        or error response if operation fails.
    """

    def _execute() -> dict[str, Any]:
        # Validate message IDs
        validated_ids = validate_message_ids(params.message_ids)

        # Check that at least one label operation is specified
        if not params.add_labels and not params.remove_labels:
            raise ValidationError(
                "At least one of add_labels or remove_labels must be specified"
            )

        # Get Gmail service
        service = gmail_client.get_service()

        # Resolve label names to IDs
        add_label_ids: list[str] = []
        remove_label_ids: list[str] = []
        labels_added_names: list[str] = []
        labels_removed_names: list[str] = []

        if params.add_labels:
            add_label_ids, add_mapping = _resolve_label_ids(service, params.add_labels)
            labels_added_names = list(add_mapping.values())

        if params.remove_labels:
            remove_label_ids, remove_mapping = _resolve_label_ids(
                service, params.remove_labels
            )
            labels_removed_names = list(remove_mapping.values())

        # Apply label modifications
        batch_modify_messages(
            service=service,
            message_ids=validated_ids,
            add_labels=add_label_ids if add_label_ids else None,
            remove_labels=remove_label_ids if remove_label_ids else None,
        )

        logger.info(
            "Applied labels to %d messages: +%s -%s",
            len(validated_ids),
            labels_added_names,
            labels_removed_names,
        )

        return build_success_response(
            data={
                "modified_count": len(validated_ids),
                "message_ids": validated_ids,
                "labels_added": labels_added_names,
                "labels_removed": labels_removed_names,
            },
            message=f"Successfully modified labels on {len(validated_ids)} message(s)",
            count=len(validated_ids),
        )

    try:
        return await execute_tool(
            tool_name="gmail_apply_labels",
            params=params.model_dump(),
            operation=_execute,
        )
    except GmailMCPError as e:
        logger.error("Apply labels failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.error("Unexpected error applying labels: %s", e)
        return build_error_response(
            error="An unexpected error occurred",
            error_code="INTERNAL_ERROR",
        )

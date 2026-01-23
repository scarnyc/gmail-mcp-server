"""Label management tools for Gmail MCP Server.

This module implements write tools for Gmail label operations:
- gmail_create_label: Create a new label
- gmail_organize_labels: Batch operations (rename, delete, update_visibility)
"""

from __future__ import annotations

import logging
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.labels import (
    create_label,
    delete_label,
    get_label_by_name,
    update_label,
)
from gmail_mcp.middleware.validator import validate_label_name
from gmail_mcp.schemas.tools import CreateLabelParams, OrganizeLabelsParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    compute_params_hash,
    create_approval_request,
    execute_tool,
    validate_and_consume_approval,
)
from gmail_mcp.utils.errors import ApprovalError, GmailAPIError, ValidationError

logger = logging.getLogger(__name__)

# Valid operations for organize_labels
VALID_OPERATIONS = {"rename", "delete", "update_visibility"}

# Valid visibility values
VALID_LABEL_LIST_VISIBILITY = {"labelHide", "labelShow", "labelShowIfUnread"}
VALID_MESSAGE_LIST_VISIBILITY = {"hide", "show"}


async def gmail_create_label(params: CreateLabelParams) -> dict[str, Any]:
    """Create a new Gmail label.

    This tool implements the HITL two-step flow:
    - Step 1 (no approval_id): Returns preview of label to be created
    - Step 2 (with approval_id): Creates the label

    Args:
        params: CreateLabelParams with name, visibility settings,
            and optional approval_id.

    Returns:
        Dict with created label info or pending approval response.
    """

    def operation() -> dict[str, Any]:
        # Validate label name
        try:
            validated_name = validate_label_name(params.name)
        except ValidationError as e:
            return build_error_response(
                error=str(e),
                error_code="VALIDATION_ERROR",
            )

        # Validate visibility settings
        if params.label_list_visibility not in VALID_LABEL_LIST_VISIBILITY:
            return build_error_response(
                error=f"Invalid label_list_visibility: {params.label_list_visibility}",
                error_code="VALIDATION_ERROR",
                details={"valid_values": list(VALID_LABEL_LIST_VISIBILITY)},
            )

        if params.message_list_visibility not in VALID_MESSAGE_LIST_VISIBILITY:
            msg_vis = params.message_list_visibility
            return build_error_response(
                error=f"Invalid message_list_visibility: {msg_vis}",
                error_code="VALIDATION_ERROR",
                details={"valid_values": list(VALID_MESSAGE_LIST_VISIBILITY)},
            )

        # Step 1: No approval_id - return preview for user confirmation
        if not params.approval_id:
            preview = {
                "name": validated_name,
                "label_list_visibility": params.label_list_visibility,
                "message_list_visibility": params.message_list_visibility,
            }
            return create_approval_request(
                action="create_label",
                preview=preview,
            )

        # Step 2: Validate approval and create label
        # Rebuild the preview to verify parameters haven't been tampered with
        verification_preview = {
            "name": validated_name,
            "label_list_visibility": params.label_list_visibility,
            "message_list_visibility": params.message_list_visibility,
        }

        try:
            validate_and_consume_approval(
                params.approval_id,
                expected_action="create_label",
                params_hash=compute_params_hash(verification_preview),
            )
        except ApprovalError as e:
            return build_error_response(
                error=str(e),
                error_code="APPROVAL_ERROR",
            )

        # Get Gmail service
        try:
            service = gmail_client.get_service()
        except Exception as e:
            logger.error("Failed to get Gmail service: %s", e)
            return build_error_response(
                error="Failed to authenticate with Gmail",
                error_code="AUTH_ERROR",
            )

        # Check if label already exists
        existing_label = get_label_by_name(service, validated_name)
        if existing_label:
            return build_error_response(
                error=f"Label '{validated_name}' already exists",
                error_code="LABEL_EXISTS",
                details={
                    "existing_label_id": existing_label.get("id"),
                    "existing_label_name": existing_label.get("name"),
                },
            )

        # Create the label
        try:
            created_label = create_label(
                service,
                name=validated_name,
                label_list_visibility=params.label_list_visibility,
                message_list_visibility=params.message_list_visibility,
            )
        except GmailAPIError as e:
            return build_error_response(
                error=str(e),
                error_code="GMAIL_API_ERROR",
            )

        return build_success_response(
            data={
                "label_id": created_label.get("id"),
                "name": created_label.get("name"),
                "label_list_visibility": created_label.get("labelListVisibility"),
                "message_list_visibility": created_label.get("messageListVisibility"),
            },
            message=f"Label '{validated_name}' created successfully",
        )

    return await execute_tool(
        tool_name="gmail_create_label",
        params=params.model_dump(exclude_none=True),
        operation=operation,
    )


def _validate_operation(op: dict[str, str], index: int) -> dict[str, Any] | None:
    """Validate a single label operation.

    Args:
        op: Operation dict with action and parameters.
        index: Index of operation in list (for error reporting).

    Returns:
        Error response dict if validation fails, None if valid.
    """
    action = op.get("action")
    if not action:
        return build_error_response(
            error=f"Operation {index}: missing 'action' field",
            error_code="VALIDATION_ERROR",
        )

    if action not in VALID_OPERATIONS:
        return build_error_response(
            error=f"Operation {index}: invalid action '{action}'",
            error_code="VALIDATION_ERROR",
            details={"valid_actions": list(VALID_OPERATIONS)},
        )

    label_id = op.get("label_id")
    if not label_id:
        return build_error_response(
            error=f"Operation {index}: missing 'label_id' field",
            error_code="VALIDATION_ERROR",
        )

    # Action-specific validation
    if action == "rename":
        new_name = op.get("new_name")
        if not new_name:
            return build_error_response(
                error=f"Operation {index}: 'rename' action requires 'new_name' field",
                error_code="VALIDATION_ERROR",
            )
        try:
            validate_label_name(new_name)
        except ValidationError as e:
            return build_error_response(
                error=f"Operation {index}: {e}",
                error_code="VALIDATION_ERROR",
            )

    elif action == "update_visibility":
        visibility = op.get("visibility")
        if not visibility:
            return build_error_response(
                error=(
                    f"Operation {index}: 'update_visibility' action "
                    "requires 'visibility' field"
                ),
                error_code="VALIDATION_ERROR",
            )
        if visibility not in VALID_LABEL_LIST_VISIBILITY:
            return build_error_response(
                error=f"Operation {index}: invalid visibility '{visibility}'",
                error_code="VALIDATION_ERROR",
                details={"valid_values": list(VALID_LABEL_LIST_VISIBILITY)},
            )

    return None


def _execute_operation(service: Any, op: dict[str, str]) -> dict[str, Any]:
    """Execute a single label operation.

    Args:
        service: Gmail API service.
        op: Validated operation dict.

    Returns:
        Dict with operation result (status, label_id, details).
    """
    action = op["action"]
    label_id = op["label_id"]

    try:
        if action == "rename":
            new_name = op["new_name"]
            updated = update_label(service, label_id, name=new_name)
            return {
                "status": "success",
                "action": action,
                "label_id": label_id,
                "new_name": updated.get("name"),
            }

        elif action == "delete":
            delete_label(service, label_id)
            return {
                "status": "success",
                "action": action,
                "label_id": label_id,
            }

        elif action == "update_visibility":
            visibility = op["visibility"]
            updated = update_label(service, label_id, label_list_visibility=visibility)
            return {
                "status": "success",
                "action": action,
                "label_id": label_id,
                "visibility": updated.get("labelListVisibility"),
            }

        else:
            return {
                "status": "error",
                "action": action,
                "label_id": label_id,
                "error": f"Unknown action: {action}",
            }

    except GmailAPIError as e:
        return {
            "status": "error",
            "action": action,
            "label_id": label_id,
            "error": str(e),
        }


async def gmail_organize_labels(params: OrganizeLabelsParams) -> dict[str, Any]:
    """Perform batch label operations (rename, delete, update_visibility).

    This tool implements the HITL two-step flow:
    - Step 1 (no approval_id): Returns preview of operations to be performed
    - Step 2 (with approval_id): Executes all operations

    Operations format:
    - rename: {"action": "rename", "label_id": "...", "new_name": "..."}
    - delete: {"action": "delete", "label_id": "..."}
    - update_visibility: {"action": "update_visibility", "label_id": "...",
        "visibility": "labelShow|labelHide|labelShowIfUnread"}

    Example operations:
        - Rename: {"action": "rename", "label_id": "Label_123", "new_name": "NewName"}
        - Delete: {"action": "delete", "label_id": "Label_123"}
        - Update visibility: {"action": "update_visibility", "label_id": "Label_123",
            "visibility": "labelShow"}

    Args:
        params: OrganizeLabelsParams with operations list and optional approval_id.

    Returns:
        Dict with operation results or pending approval response.
    """

    def operation() -> dict[str, Any]:
        operations = params.operations

        # Validate we have at least one operation
        if not operations:
            return build_error_response(
                error="No operations provided",
                error_code="VALIDATION_ERROR",
            )

        # Validate all operations first
        for i, op in enumerate(operations):
            validation_error = _validate_operation(op, i)
            if validation_error:
                return validation_error

        # Step 1: No approval_id - return preview for user confirmation
        if not params.approval_id:
            # Build human-readable operation descriptions
            operation_previews = []
            for op in operations:
                action = op["action"]
                label_id = op["label_id"]

                if action == "rename":
                    desc = f"Rename label '{label_id}' to '{op['new_name']}'"
                elif action == "delete":
                    desc = f"Delete label '{label_id}'"
                elif action == "update_visibility":
                    vis = op["visibility"]
                    desc = f"Update visibility of label '{label_id}' to '{vis}'"
                else:
                    desc = f"{action} on label '{label_id}'"

                operation_previews.append(
                    {
                        "action": action,
                        "label_id": label_id,
                        "description": desc,
                        **{
                            k: v
                            for k, v in op.items()
                            if k not in ("action", "label_id")
                        },
                    }
                )

            preview = {
                "operation_count": len(operations),
                "operations": operation_previews,
                "warning": (
                    "These operations will modify your Gmail labels. "
                    "Delete operations cannot be undone."
                ),
            }
            return create_approval_request(
                action="organize_labels",
                preview=preview,
            )

        # Step 2: Validate approval and execute operations
        # Rebuild the preview to verify parameters haven't been tampered with
        verification_operation_previews = []
        for op in operations:
            action = op["action"]
            label_id = op["label_id"]

            if action == "rename":
                desc = f"Rename label '{label_id}' to '{op['new_name']}'"
            elif action == "delete":
                desc = f"Delete label '{label_id}'"
            elif action == "update_visibility":
                vis = op["visibility"]
                desc = f"Update visibility of label '{label_id}' to '{vis}'"
            else:
                desc = f"{action} on label '{label_id}'"

            verification_operation_previews.append(
                {
                    "action": action,
                    "label_id": label_id,
                    "description": desc,
                    **{k: v for k, v in op.items() if k not in ("action", "label_id")},
                }
            )

        verification_preview = {
            "operation_count": len(operations),
            "operations": verification_operation_previews,
            "warning": (
                "These operations will modify your Gmail labels. "
                "Delete operations cannot be undone."
            ),
        }

        try:
            validate_and_consume_approval(
                params.approval_id,
                expected_action="organize_labels",
                params_hash=compute_params_hash(verification_preview),
            )
        except ApprovalError as e:
            return build_error_response(
                error=str(e),
                error_code="APPROVAL_ERROR",
            )

        # Get Gmail service
        try:
            service = gmail_client.get_service()
        except Exception as e:
            logger.error("Failed to get Gmail service: %s", e)
            return build_error_response(
                error="Failed to authenticate with Gmail",
                error_code="AUTH_ERROR",
            )

        # Execute each operation and collect results
        results = []
        success_count = 0
        failure_count = 0

        for op in operations:
            result = _execute_operation(service, op)
            results.append(result)
            if result["status"] == "success":
                success_count += 1
            else:
                failure_count += 1

        # Build response based on results
        if failure_count == 0:
            return build_success_response(
                data={
                    "results": results,
                    "success_count": success_count,
                    "failure_count": failure_count,
                },
                message=f"All {success_count} operations completed successfully",
                count=success_count,
            )
        elif success_count == 0:
            return build_error_response(
                error="All operations failed",
                error_code="ALL_OPERATIONS_FAILED",
                details={
                    "results": results,
                    "success_count": success_count,
                    "failure_count": failure_count,
                },
            )
        else:
            # Partial success
            return build_success_response(
                data={
                    "results": results,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "partial_success": True,
                },
                message=f"Partial success: {success_count} succeeded, "
                f"{failure_count} failed",
                count=success_count,
            )

    return await execute_tool(
        tool_name="gmail_organize_labels",
        params={"operations": params.operations, "approval_id": params.approval_id},
        operation=operation,
    )

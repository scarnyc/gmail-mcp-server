"""Pydantic parameter models for Gmail MCP tools.

This module contains all input validation schemas for the Gmail MCP server tools.
Models are divided into two categories:

- Read Tools: Read-only operations that don't require HITL approval
- Write Tools: Destructive operations that require human-in-the-loop approval
"""

from pydantic import BaseModel, EmailStr, Field

# =============================================================================
# Read Tool Parameter Models (No HITL Required)
# =============================================================================


class TriageParams(BaseModel):
    """Parameters for gmail_triage_inbox tool.

    Triages the inbox by categorizing emails based on urgency and importance.
    """

    max_results: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum emails to triage",
    )
    label_ids: list[str] = Field(
        default=["INBOX", "UNREAD"],
        description="Labels to filter by",
    )


class SearchParams(BaseModel):
    """Parameters for gmail_search tool.

    Searches emails using Gmail's query syntax.
    """

    query: str = Field(
        ...,
        min_length=1,
        description="Gmail search query (e.g., 'from:user@example.com')",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum results to return",
    )


class SummarizeThreadParams(BaseModel):
    """Parameters for gmail_summarize_thread tool.

    Generates an AI summary of a conversation thread.
    """

    thread_id: str = Field(
        ...,
        description="Gmail thread ID to summarize",
    )


class DraftReplyParams(BaseModel):
    """Parameters for gmail_draft_reply tool.

    Generates a draft reply based on thread context.
    """

    thread_id: str = Field(
        ...,
        description="Gmail thread ID to reply to",
    )
    context: str | None = Field(
        None,
        description="Additional context for generating reply",
    )


class ChatInboxParams(BaseModel):
    """Parameters for gmail_chat_inbox tool.

    Enables natural language queries about inbox contents.
    """

    question: str = Field(
        ...,
        description="Natural language question about inbox",
    )


class ApplyLabelsParams(BaseModel):
    """Parameters for gmail_apply_labels tool.

    Adds or removes labels from messages. This is idempotent and read-safe.
    """

    message_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Message IDs to modify",
    )
    add_labels: list[str] = Field(
        default_factory=list,
        description="Labels to add",
    )
    remove_labels: list[str] = Field(
        default_factory=list,
        description="Labels to remove",
    )


class DownloadEmailParams(BaseModel):
    """Parameters for gmail_download_email tool.

    Downloads an email as .eml file, saves HTML body as .html,
    and extracts file attachments to a local directory.
    """

    message_id: str = Field(
        ...,
        description="Gmail message ID to download",
    )
    output_dir: str = Field(
        ...,
        description="Directory to save files to (created if it doesn't exist)",
    )
    filename_prefix: str = Field(
        default="",
        description="Optional prefix for saved filenames (e.g., vendor name)",
    )


# =============================================================================
# Write Tool Parameter Models (HITL Required)
# =============================================================================


class SendEmailParams(BaseModel):
    """Parameters for gmail_send_email tool (HITL required).

    Sends an email to specified recipients. Requires human approval before execution.

    The two-step HITL flow:
    1. First call (approval_id=None): Returns preview for user confirmation
    2. Second call (approval_id set): Executes the send after validation
    """

    to: EmailStr = Field(
        ...,
        description="Recipient email address",
    )
    subject: str = Field(
        ...,
        description="Email subject",
    )
    body: str = Field(
        ...,
        description="Email body content (plain text or HTML)",
    )
    cc: list[EmailStr] = Field(
        default_factory=list,
        description="CC recipients",
    )
    bcc: list[EmailStr] = Field(
        default_factory=list,
        description="BCC recipients",
    )
    reply_to_thread_id: str | None = Field(
        None,
        description="Thread ID if replying",
    )
    approval_id: str | None = Field(
        None,
        description="Approval ID from step 1 (required for execution)",
    )


class ArchiveEmailParams(BaseModel):
    """Parameters for gmail_archive_email tool (HITL required).

    Archives emails by removing them from inbox. Requires human approval.
    """

    message_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Message IDs to archive",
    )
    approval_id: str | None = Field(
        None,
        description="Approval ID from step 1",
    )


class DeleteEmailParams(BaseModel):
    """Parameters for gmail_delete_email tool (HITL required).

    Permanently deletes emails. Requires human approval.
    """

    message_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Message IDs to delete",
    )
    approval_id: str | None = Field(
        None,
        description="Approval ID from step 1",
    )


class UnsubscribeParams(BaseModel):
    """Parameters for gmail_unsubscribe tool (HITL required).

    Unsubscribes from mailing lists using List-Unsubscribe header.
    Requires human approval.
    """

    message_id: str = Field(
        ...,
        description="Message ID containing List-Unsubscribe header",
    )
    approval_id: str | None = Field(
        None,
        description="Approval ID from step 1",
    )


class CreateLabelParams(BaseModel):
    """Parameters for gmail_create_label tool (HITL required).

    Creates a new Gmail label. Requires human approval.
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Label name to create",
    )
    label_list_visibility: str = Field(
        default="labelShow",
        description="Visibility in label list",
    )
    message_list_visibility: str = Field(
        default="show",
        description="Visibility in message list",
    )
    approval_id: str | None = Field(
        None,
        description="Approval ID from step 1",
    )


class OrganizeLabelsParams(BaseModel):
    """Parameters for gmail_organize_labels tool (HITL required).

    Performs batch label operations (rename, nest, delete).
    Requires human approval due to destructive nature.

    Operations format: [{"action": "rename", "label_id": "...", "new_name": "..."}]
    """

    operations: list[dict[str, str]] = Field(
        ...,
        description="List of label operations [{action, ...}]",
    )
    approval_id: str | None = Field(
        None,
        description="Approval ID from step 1",
    )

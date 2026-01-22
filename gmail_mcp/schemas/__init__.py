"""Pydantic schemas for Gmail MCP.

This module exports all tool parameter models for the Gmail MCP server.
"""

from gmail_mcp.schemas.tools import (
    # Read tool params (no HITL)
    ApplyLabelsParams,
    # Write tool params (HITL required)
    ArchiveEmailParams,
    ChatInboxParams,
    CreateLabelParams,
    DeleteEmailParams,
    DraftReplyParams,
    OrganizeLabelsParams,
    SearchParams,
    SendEmailParams,
    SummarizeThreadParams,
    TriageParams,
    UnsubscribeParams,
)

__all__ = [
    # Read tools
    "TriageParams",
    "SearchParams",
    "SummarizeThreadParams",
    "DraftReplyParams",
    "ChatInboxParams",
    "ApplyLabelsParams",
    # Write tools
    "SendEmailParams",
    "ArchiveEmailParams",
    "DeleteEmailParams",
    "UnsubscribeParams",
    "CreateLabelParams",
    "OrganizeLabelsParams",
]

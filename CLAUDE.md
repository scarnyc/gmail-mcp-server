# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gmail MCP Server (`gmail-mcp-server`) - An MCP server enabling Claude to manage Gmail inboxes via conversational interface. Users interact with Claude, which calls MCP tools to perform email operations.

## Build & Development Commands

```bash
# Setup
poetry install && poetry shell

# Run MCP server (stdio transport - for local)
python -m gmail_mcp

# Run MCP server (HTTP transport - for remote)
TRANSPORT=http python -m gmail_mcp

# Run tests
pytest --cov

# Run single test
pytest tests/test_hitl.py -v

# Quality checks
ruff check . && ruff format . && mypy .
```

## Architecture

```
gmail_mcp/
├── __main__.py           # Entry point
├── server.py             # MCP server setup, tool registration
├── tools/
│   ├── __init__.py
│   ├── read/             # Read-only tools (no HITL required)
│   │   ├── triage.py     # gmail_triage_inbox
│   │   ├── summarize.py  # gmail_summarize_thread
│   │   ├── draft.py      # gmail_draft_reply
│   │   ├── search.py     # gmail_search
│   │   ├── chat.py       # gmail_chat_inbox
│   │   └── labels.py     # gmail_apply_labels
│   └── write/            # Write tools (HITL required)
│       ├── send.py       # gmail_send_email
│       ├── archive.py    # gmail_archive_email
│       ├── delete.py     # gmail_delete_email
│       ├── unsubscribe.py
│       └── labels.py     # gmail_create_label, gmail_organize_labels
├── auth/
│   ├── oauth.py          # Google OAuth flow
│   ├── tokens.py         # Token encryption (AES-256-GCM)
│   └── storage.py        # Secure token persistence
├── hitl/
│   ├── manager.py        # Approval request lifecycle
│   └── models.py         # Pydantic models
├── gmail/
│   ├── client.py         # Authenticated Gmail client
│   ├── messages.py
│   ├── threads.py
│   └── labels.py
├── middleware/
│   ├── rate_limiter.py
│   ├── audit_logger.py
│   └── validator.py
├── schemas/              # Pydantic validation models
│   └── tools.py
└── utils/
    ├── encryption.py
    └── errors.py
tests/
├── conftest.py           # pytest fixtures
├── test_hitl.py
├── test_oauth.py
└── test_tools/
```

## Key Patterns

### HITL (Human-in-the-Loop) Two-Step Flow

Write operations require user approval. Tool returns preview + `approval_id`, Claude shows user, user confirms, tool called again with `approval_id`:

```python
from gmail_mcp.hitl.manager import approval_manager
from gmail_mcp.hitl.models import ApprovalRequest

async def gmail_send_email(to: str, subject: str, body: str, approval_id: str | None = None):
    # Step 1: No approval_id → return preview
    if not approval_id:
        request = ApprovalRequest(
            action="send_email",
            preview={"to": to, "subject": subject, "body": body[:200]},
        )
        approval_manager.store(request)
        return {
            "status": "pending_approval",
            "approval_id": request.id,
            "expires_at": request.expires_at.isoformat(),
            "preview": request.preview,
            "message": "ACTION NOT TAKEN. Please review and confirm.",
        }

    # Step 2: Valid approval_id → execute action
    if not approval_manager.validate(approval_id):
        raise ApprovalError("Invalid or expired approval")
    # Execute the send...
```

### Tool Registration with FastMCP

```python
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("gmail-mcp-server")

class SendEmailParams(BaseModel):
    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content")
    approval_id: str | None = Field(None, description="Approval ID from step 1")

@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)
async def gmail_send_email(params: SendEmailParams) -> dict:
    """Send an email. Requires HITL approval."""
    ...
```

### Token Encryption

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

def encrypt_token(token_data: bytes, key: bytes) -> dict:
    """Encrypt with AES-256-GCM, unique IV per token."""
    iv = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, token_data, None)
    return {"iv": iv, "ciphertext": ciphertext}
```

## Environment Variables

Required in `.env`:
```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:3000/oauth/callback
TOKEN_ENCRYPTION_KEY=     # 64-char hex (256-bit)
```

Optional:
```
PORT=3000
TRANSPORT=stdio           # 'stdio' or 'http'
RATE_LIMIT_MAX=100        # requests per minute per user
HITL_TIMEOUT_MS=300000    # approval expiry (5 min default)
```

## OAuth Scopes

Request minimal scopes:
- `gmail.readonly` - Read emails
- `gmail.modify` - Modify (labels, archive)
- `gmail.compose` - Send emails
- `gmail.labels` - Manage labels

## Testing Strategy

- Unit tests for encryption, validation, rate limiting
- Integration tests for OAuth flow (mocked Google endpoints)
- Tool tests with mocked Gmail API responses
- HITL approval lifecycle tests

## Dependencies

Core (in pyproject.toml):
- `mcp` - Python MCP SDK (FastMCP)
- `pydantic` - Schema validation
- `google-api-python-client` / `google-auth` - Gmail API
- `cryptography` - AES-256-GCM encryption

Dev:
- `pytest`, `pytest-cov`, `pytest-asyncio`
- `ruff`, `mypy`

## Tool Annotations Reference

| Tool | readOnly | destructive | idempotent |
|------|----------|-------------|------------|
| gmail_triage_inbox | Y | | Y |
| gmail_summarize_thread | Y | | Y |
| gmail_draft_reply | Y | | Y |
| gmail_search | Y | | Y |
| gmail_chat_inbox | Y | | Y |
| gmail_apply_labels | | | Y |
| gmail_send_email | | Y | |
| gmail_archive_email | | Y | Y |
| gmail_delete_email | | Y | |
| gmail_unsubscribe | | Y | |
| gmail_create_label | | | |
| gmail_organize_labels | | Y | |

## Project-Level Plugins

Enabled via `.claude/settings.json`:

| Plugin | Purpose |
|--------|---------|
| **context7** | Up-to-date library documentation |
| **serena** | Semantic code analysis, symbol navigation |
| **ralph-loop** | Autonomous multi-step task execution |
| **pyright-lsp** | Python language server for type checking |
| **firebase** | Firebase SDK integration tools |

## JIRA Integration

Available for ticket management. Start sessions with `/backlog` to pull from Kanban "To Do" column, pick a ticket, create feature branch: `feature/PROJECT-123-description`.

## Security Requirements

- OAuth tokens encrypted at rest with AES-256-GCM
- HITL enforcement cannot be bypassed for write operations
- Per-user rate limiting on API calls
- Audit logging for all tool invocations
- Input validation via Pydantic before processing

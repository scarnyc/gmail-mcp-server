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

**Note:** `poetry` is not on PATH. Use `.venv/bin/` directly for quality gates:
```bash
.venv/bin/ruff check gmail_mcp/
.venv/bin/ruff format --check gmail_mcp/
.venv/bin/mypy gmail_mcp/
.venv/bin/pytest tests/ -v --tb=short
```

## Architecture

```
gmail_mcp/
├── __main__.py           # Entry point
├── server.py             # MCP server setup, tool registration
├── tools/
│   ├── __init__.py
│   ├── auth/             # OAuth authentication tools
│   │   ├── login.py      # gmail_login (uses local server OAuth flow)
│   │   ├── logout.py     # gmail_logout
│   │   └── status.py     # gmail_get_auth_status
│   ├── read/             # Read-only tools (no HITL required)
│   │   ├── triage.py     # gmail_triage_inbox
│   │   ├── summarize.py  # gmail_summarize_thread
│   │   ├── draft.py      # gmail_draft_reply
│   │   ├── search.py     # gmail_search
│   │   ├── chat.py       # gmail_chat_inbox
│   │   ├── download.py   # gmail_download_email
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

## Secret Management

Following the standard MCP secret management pattern (consistent with JIRA MCP):

**Setup:**

1. Generate API credentials:
   - Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   - Create OAuth 2.0 Client ID with type **"Desktop app"** (required for loopback OAuth flow)
   - Download credentials

2. Set environment variables:
```bash
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export TOKEN_ENCRYPTION_KEY="$(openssl rand -hex 32)"
```

3. Add to `.mcp.json`:
```json
{
  "mcpServers": {
    "gmail": {
      "command": "gmail-mcp",
      "args": [],
      "env": {
        "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
        "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}",
        "TOKEN_ENCRYPTION_KEY": "${TOKEN_ENCRYPTION_KEY}",
        "TRANSPORT": "stdio",
        "READ_ONLY": "true"
      }
    }
  }
}
```

Set `READ_ONLY` to `"true"` for read-only access (9 tools, `gmail.readonly` scope only) or omit/set `"false"` for full access (16 tools, all scopes).

4. Restart Claude Code, verify with `/mcp`

**CLI Commands:**
```bash
gmail-mcp serve    # Start MCP server (alias for python -m gmail_mcp)
```

**Environment Variables:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_CLIENT_ID` | Yes | - | OAuth 2.0 Client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | - | OAuth 2.0 Client Secret |
| `TOKEN_ENCRYPTION_KEY` | Yes | - | 64-char hex (256-bit AES key) |
| `READ_ONLY` | No | `false` | Read-only mode: only `gmail.readonly` scope, no write tools |
| `TRANSPORT` | No | `stdio` | Transport: stdio, http, streamable-http |
| `PORT` | No | `3000` | HTTP server port |
| `OAUTH_PORT` | No | `3000` | OAuth callback server port (fallback: +1, +2) |
| `RATE_LIMIT_MAX` | No | `100` | Requests per minute per user |
| `HITL_TIMEOUT_MS` | No | `300000` | Approval expiry (5 min) |

## OAuth Scopes

Scopes are determined dynamically based on `READ_ONLY` mode (`get_gmail_scopes()` in `auth/oauth.py`):

**Read-only mode** (`READ_ONLY=true`): Requests only `gmail.readonly` — single checkbox on consent screen.

**Full mode** (default): Requests all 4 scopes:
- `gmail.readonly` - Read emails
- `gmail.modify` - Modify (labels, archive)
- `gmail.compose` - Send emails
- `gmail.labels` - Manage labels

**Note:** Switching modes requires re-authentication (`gmail_login`) since Google doesn't upgrade scopes on existing tokens.

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

Tools registered depend on `READ_ONLY` mode. In read-only mode (9 tools), only auth + read tools are available. In full mode (16 tools), all tools are registered.

| Tool | readOnly | destructive | idempotent | Mode |
|------|----------|-------------|------------|------|
| gmail_login | | | | both |
| gmail_logout | | Y | Y | both |
| gmail_get_auth_status | Y | | Y | both |
| gmail_triage_inbox | Y | | Y | both |
| gmail_summarize_thread | Y | | Y | both |
| gmail_draft_reply | Y | | Y | both |
| gmail_search | Y | | Y | both |
| gmail_chat_inbox | Y | | Y | both |
| gmail_download_email | Y | | Y | both |
| gmail_apply_labels | | | Y | full only |
| gmail_send_email | | Y | | full only |
| gmail_archive_email | | Y | Y | full only |
| gmail_delete_email | | Y | | full only |
| gmail_unsubscribe | | Y | | full only |
| gmail_create_label | | | | full only |
| gmail_organize_labels | | Y | | full only |

## Project-Level Plugins

Enabled via `.claude/settings.json`:

| Plugin | Purpose |
|--------|---------|
| **context7** | Up-to-date library documentation |
| **serena** | Semantic code analysis, symbol navigation |
| **ralph-loop** | Autonomous multi-step task execution |
| **pyright-lsp** | Python language server for type checking |
| **firebase** | Firebase SDK integration tools |
| **code-review** | Code review a pull request |
| **security-guidance** | Security best practices and vulnerability guidance |
| **code-simplifier** | Simplifies code for clarity and maintainability (agent) |
| **feature-dev** | Guided feature development with architecture focus |

## JIRA Integration

Available for ticket management. Start sessions with `/backlog` to pull from Kanban "To Do" column, pick a ticket, create feature branch: `feature/PROJECT-123-description`.

## Security Requirements

- OAuth tokens encrypted at rest with AES-256-GCM
- HITL enforcement cannot be bypassed for write operations
- Per-user rate limiting on API calls
- Audit logging for all tool invocations
- Input validation via Pydantic before processing

## Known Limitations

### Single-User Mode
The current implementation operates in single-user mode (`user_id="default"`). All
Gmail operations use the same authenticated account. Multi-user support (extracting
user identity from MCP context) is planned for a future release.

For multi-account use cases, run separate MCP server instances with different
token storage paths via `TOKEN_STORAGE_PATH` environment variable.

### Google OAuth Incremental Authorization

Google OAuth supports "incremental authorization" where new tokens can inherit
previously-granted scopes. The `create_auth_url()` method in `auth/oauth.py`
sets `include_granted_scopes=false` to prevent this. Do not remove this
parameter — without it, switching from full to read-only mode may still
produce tokens with all 4 scopes.

### Gmail Scopes and OAuth Flow

**Note:** Gmail scopes (`gmail.readonly`, `gmail.modify`, `gmail.compose`, `gmail.labels`)
are classified as "restricted scopes" by Google and cannot use device flow. The `gmail_login`
tool uses local server flow instead:

1. Opens browser to Google consent page
2. Runs local HTTP server on `localhost:3000` for callback
3. Exchanges authorization code for tokens

**Headless environments (Replit, Docker, etc.):**
Since local server flow requires a browser, headless deployments need alternative strategies:
1. Pre-authenticate locally, copy encrypted tokens to server
2. Use Google Workspace service account with domain-wide delegation
3. Implement a separate web-based OAuth flow with redirect URI

### OAuth Troubleshooting

**Port already in use:**
```
OSError: [Errno 48] Address already in use
```
The server automatically tries fallback ports (3000 → 3001 → 3002). To use a different primary port:
```bash
export OAUTH_PORT=4000
```

**Browser doesn't open:**
- Check if running in headless environment (no display)
- Manually visit the URL printed in logs
- Ensure `webbrowser` module can access system browser

**Callback never received:**
- Ensure firewall allows localhost connections on the OAuth port
- Check browser didn't block the redirect
- Verify redirect URI in Google Cloud Console matches `http://localhost:{port}/oauth/callback`

**Token storage errors:**
- Ensure `~/.gmail-mcp/tokens/` directory exists and is writable
- Check `TOKEN_ENCRYPTION_KEY` is set (64 hex characters = 256-bit key)
- Verify key hasn't changed since tokens were encrypted

**State mismatch error:**
- This is CSRF protection - the callback state doesn't match the request
- Don't reuse browser tabs/windows from old auth attempts
- Restart the login flow from the beginning

**"Loopback flow has been blocked" error (Error 400: invalid_request):**
- Your OAuth client type is incorrect. Google blocks loopback redirects for non-desktop client types
- Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- Create a new OAuth 2.0 Client ID with type **"Desktop app"** (not "Web application" or "TV and Limited Input")
- Update `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` with the new credentials

## Quality Gate Checklist (Phase-Gated Development)

Before proceeding to the next implementation wave, **ALL** checks must pass:

```bash
# 1. Lint check
.venv/bin/ruff check gmail_mcp/

# 2. Format check
.venv/bin/ruff format --check gmail_mcp/

# 3. Type check
.venv/bin/mypy gmail_mcp/

# 4. Run tests for completed modules
.venv/bin/pytest tests/ -v --tb=short

# 5. Code review (via /code-review skill)
```

**Gate criteria:**
- [ ] Zero lint errors
- [ ] Zero format issues
- [ ] Zero type errors (mypy strict)
- [ ] All tests pass
- [ ] Code review approved (no critical issues)

**Post-gate action:** After code review passes, commit and push changes before proceeding to next wave.

**Wave progression:**
- Wave 1 → GATE 1 → Wave 2 → GATE 2 → Wave 3 → GATE 3 → Wave 4 → GATE 4 → Wave 5

## Implementation Progress

All waves complete. 16 tools registered (3 auth + 6 read + 7 write). 158+ tests passing.

| Wave | Description | Status |
|------|-------------|--------|
| 1 | Foundation (errors, encryption, HITL, schemas) | ✅ |
| 2 | Auth + Gmail Client + Middleware | ✅ |
| 3 | Tools (6 read, 5 write) | ✅ |
| 4 | Server Integration (server.py, __main__.py) | ✅ |
| 5 | Final Validation & Deployment Prep | ✅ |
| 6 | OAuth Auth Tools (login, logout, status) | ✅ |

### MCP Client Configuration

See [Secret Management](#secret-management) above for `.mcp.json` examples. Set `TRANSPORT=http` for remote/Replit deployments (binds to `0.0.0.0:$PORT`). Headless environments require pre-authenticated tokens — see [Known Limitations](#gmail-scopes-and-oauth-flow).

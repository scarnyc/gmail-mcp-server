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
        "TRANSPORT": "stdio"
      }
    }
  }
}
```

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
| `TRANSPORT` | No | `stdio` | Transport: stdio, http, streamable-http |
| `PORT` | No | `3000` | HTTP server port |
| `OAUTH_PORT` | No | `3000` | OAuth callback server port (fallback: +1, +2) |
| `RATE_LIMIT_MAX` | No | `100` | Requests per minute per user |
| `HITL_TIMEOUT_MS` | No | `300000` | Approval expiry (5 min) |

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
| gmail_login | | | |
| gmail_logout | | Y | Y |
| gmail_get_auth_status | Y | | Y |
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
ruff check gmail_mcp/

# 2. Format check
ruff format --check gmail_mcp/

# 3. Type check
mypy gmail_mcp/

# 4. Run tests for completed modules
pytest tests/ -v --tb=short

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

| Wave | Description | Status | Commit |
|------|-------------|--------|--------|
| **Wave 1** | Foundation Layer (errors, encryption, HITL, schemas) | ✅ Complete | `4a520fe` |
| **Wave 2** | Auth + Gmail Client (tokens, storage, oauth, gmail ops, middleware) | ✅ Complete | `9cfbe3e`, `7d3b0f4` (security fixes) |
| **Wave 3** | Tools (6 read, 5 write) | ✅ Complete | `9ce8d5c` |
| **Wave 4** | Server Integration (server.py, __main__.py) | ✅ Complete | `c49b46b` |
| **Wave 5** | Final Validation & Deployment Prep | ✅ Complete | `35c66d1` |
| **Wave 6** | OAuth Authentication Tools (3 tools: login, logout, status) | ✅ Complete | (pending) |

### Wave 1 Details (Complete)
- `utils/errors.py` - 7 custom exception classes
- `utils/encryption.py` - AES-256-GCM utilities
- `hitl/models.py` - Pydantic approval models
- `hitl/manager.py` - Thread-safe approval manager with action verification
- `schemas/tools.py` - 11 tool parameter models with EmailStr validation
- Tests: 53 passing (75% coverage)

### Wave 2 Details (Complete)
- `auth/tokens.py` - Token encryption/decryption (encrypt_token, decrypt_token)
- `auth/storage.py` - File-based encrypted token storage (~/.gmail-mcp/tokens/)
- `auth/oauth.py` - Google OAuth (local server + device flow)
- `gmail/messages.py` - Message operations (list, get, send, modify, delete)
- `gmail/threads.py` - Thread operations (list, get, modify, delete)
- `gmail/labels.py` - Label management (CRUD operations)
- `gmail/client.py` - Authenticated client factory with token refresh
- `middleware/rate_limiter.py` - Token bucket rate limiting
- `middleware/audit_logger.py` - Stderr JSON audit logging
- `middleware/validator.py` - Input validation (email, message_id, thread_id, search query)

### Wave 4 Details (Complete)
- `server.py` - FastMCP server with 12 tool registrations and lifespan context
- `__main__.py` - Entry point with env validation and transport selection (stdio/SSE/streamable-http)
- `tests/test_server.py` - 24 tests across 6 test classes
- Added uvicorn as runtime dependency for SSE transport

### Wave 6 Details (Complete)
- `tools/auth/__init__.py` - Auth tools package exports
- `tools/auth/login.py` - `gmail_login` (uses local server OAuth flow)
- `tools/auth/logout.py` - `gmail_logout` (clear stored credentials)
- `tools/auth/status.py` - `gmail_get_auth_status` (check authentication state)
- `server.py` - Updated with 15 tool registrations (3 auth + 6 read + 6 write)
- Tests: `tests/test_tools/test_auth.py` - 9 test cases (4 login, 2 logout, 3 status)

## Implementation Phases

### Phase 1: Foundation Layer

Files to create:

1. gmail_mcp/utils/errors.py
- GmailMCPError (base), AuthenticationError, TokenError, ApprovalError, RateLimitError, GmailAPIError, ValidationError
2. gmail_mcp/utils/encryption.py
- generate_key() - Generate 256-bit key
- encrypt_data(plaintext, key) - AES-256-GCM with unique IV
- decrypt_data(iv, ciphertext, key)
- key_from_hex(hex_string)
3. gmail_mcp/hitl/models.py
- ApprovalStatus enum (PENDING, APPROVED, REJECTED, EXPIRED)
- ApprovalRequest model (id, action, preview, expires_at, user_id)
- ApprovalResponse model (status, approval_id, expires_at, preview, message)
4. gmail_mcp/hitl/manager.py
- ApprovalManager class with store(), validate(), consume(), cleanup_expired()
- Global approval_manager singleton

Tests: tests/test_utils.py, tests/test_hitl.py

---
### Phase 2: Authentication Layer

Files to create:

5. gmail_mcp/schemas/tools.py
- Read params: TriageParams, SearchParams, SummarizeThreadParams, DraftReplyParams, ChatInboxParams, ApplyLabelsParams
- Write params (with approval_id): SendEmailParams, ArchiveEmailParams, DeleteEmailParams, UnsubscribeParams, CreateLabelParams, OrganizeLabelsParams
6. gmail_mcp/auth/tokens.py
- encrypt_token(token_dict, key) - Returns {iv, ciphertext} as hex
- decrypt_token(encrypted, key) - Returns original dict
7. gmail_mcp/auth/storage.py
- TokenStorage class with save(user_id, token), load(user_id), delete(user_id)
- Storage path: ~/.gmail-mcp/tokens/{user_id}.token.enc
8. gmail_mcp/auth/oauth.py
- OAuthManager class:
    - create_auth_url(state) - Generate consent URL
    - run_local_server(port) - Desktop flow (opens browser)
    - start_device_flow() - Returns {verification_uri, user_code, device_code, interval}
    - poll_device_flow(device_code) - Poll until user completes auth
    - exchange_code(code) - Exchange auth code for tokens
    - refresh_credentials(token_data) - Refresh expired tokens

Tests: tests/test_oauth.py, tests/test_tokens.py

---
### Phase 3: Gmail Client Layer

Files to create:

9. gmail_mcp/gmail/client.py
- GmailClient class:
    - get_service(user_id) - Returns authenticated Gmail API Resource
    - invalidate(user_id) - Clear cached service
    - Auto-refreshes tokens when expired
10. gmail_mcp/gmail/messages.py
- list_messages(service, query, label_ids, max_results)
- get_message(service, message_id, format)
- send_message(service, to, subject, body, cc, bcc, thread_id)
- modify_message(service, message_id, add_labels, remove_labels)
- trash_message(service, message_id)
- delete_message(service, message_id)
- parse_headers(message) - Extract From, To, Subject, Date
- decode_body(message) - Base64 decode body
11. gmail_mcp/gmail/threads.py
- list_threads(service, query, label_ids, max_results)
- get_thread(service, thread_id, format)
- modify_thread(service, thread_id, add_labels, remove_labels)
- trash_thread(service, thread_id)
12. gmail_mcp/gmail/labels.py
- list_labels(service)
- get_label(service, label_id)
- create_label(service, name, visibility)
- update_label(service, label_id, ...)
- delete_label(service, label_id)

Tests: tests/test_gmail_client.py

---
### Phase 4: Middleware & Tools

Files to create:

13. gmail_mcp/middleware/rate_limiter.py
- RateLimiter class (token bucket algorithm)
- check(user_id), consume(user_id), remaining(user_id)
- Global rate_limiter singleton
14. gmail_mcp/middleware/audit_logger.py
- AuditEntry model
- AuditLogger class with log(), log_tool_call()
- Writes to stderr (STDIO-safe)
15. gmail_mcp/middleware/validator.py
- validate_email(email), validate_message_id(id), validate_thread_id(id), sanitize_search_query(query)

#### Read Tools (6 files):

16. gmail_mcp/tools/read/triage.py - gmail_triage_inbox
17. gmail_mcp/tools/read/summarize.py - gmail_summarize_thread
18. gmail_mcp/tools/read/draft.py - gmail_draft_reply
19. gmail_mcp/tools/read/search.py - gmail_search
20. gmail_mcp/tools/read/chat.py - gmail_chat_inbox
21. gmail_mcp/tools/read/labels.py - gmail_apply_labels

#### Write Tools (5 files) - All use HITL two-step flow:

22. gmail_mcp/tools/write/send.py - gmail_send_email
23. gmail_mcp/tools/write/archive.py - gmail_archive_email
24. gmail_mcp/tools/write/delete.py - gmail_delete_email
25. gmail_mcp/tools/write/unsubscribe.py - gmail_unsubscribe
26. gmail_mcp/tools/write/labels.py - gmail_create_label, gmail_organize_labels

Tests: tests/test_tools/test_read.py, tests/test_tools/test_write.py

---
### Phase 5: Server Integration

Files to modify/create:

27. gmail_mcp/server.py (new)
- FastMCP server initialization
- Lifespan context for shared resources (gmail_client, oauth_manager)
- Tool registration with annotations
- Rate limiting and audit logging middleware
28. gmail_mcp/__main__.py (update existing stub)
- Load .env configuration
- Transport selection: stdio (default) or http (Replit)
- HTTP: bind to 0.0.0.0:$PORT for Replit
29. pyproject.toml (update)
- Add missing pytest-mock dev dependency

Tests: tests/test_server.py

---
### HITL Two-Step Flow Pattern

async def gmail_send_email(params: SendEmailParams) -> dict:
    # Step 1: No approval_id -> return preview
    if not params.approval_id:
        request = ApprovalRequest(
            action="send_email",
            preview={"to": params.to, "subject": params.subject, "body": params.body[:200]},
        )
        approval_manager.store(request)
        return {
            "status": "pending_approval",
            "approval_id": request.id,
            "expires_at": request.expires_at.isoformat(),
            "preview": request.preview,
            "message": "ACTION NOT TAKEN. Please review and confirm.",
        }

    # Step 2: Valid approval_id -> execute
    if not approval_manager.consume(params.approval_id):
        raise ApprovalError("Invalid or expired approval")
    # Execute Gmail API call...

---
### Tool Annotations Reference

| Tool                   | readOnly | destructive | idempotent |
|------------------------|----------|-------------|------------|
| gmail_login            |          |             |            |
| gmail_logout           |          | Y           | Y          |
| gmail_get_auth_status  | Y        |             | Y          |
| gmail_triage_inbox     | Y        |             | Y          |
| gmail_summarize_thread | Y        |             | Y          |
| gmail_draft_reply      | Y        |             | Y          |
| gmail_search           | Y        |             | Y          |
| gmail_chat_inbox       | Y        |             | Y          |
| gmail_apply_labels     |          |             | Y          |
| gmail_send_email       |          | Y           |            |
| gmail_archive_email    |          | Y           | Y          |
| gmail_delete_email     |          | Y           |            |
| gmail_unsubscribe      |          | Y           |            |
| gmail_create_label     |          |             |            |
| gmail_organize_labels  |          | Y           |            |

---
### MCP Client Configuration (How Claude Connects)

The server reads TRANSPORT env var to start in the right mode. The client (Claude) needs matching configuration:

#### Local Development (stdio transport)

Add to .mcp.json in project root or ~/.claude/.mcp.json globally:

{
"mcpServers": {
    "gmail": {
    "command": "gmail-mcp",
    "args": [],
    "env": {
        "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
        "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}",
        "TOKEN_ENCRYPTION_KEY": "${TOKEN_ENCRYPTION_KEY}",
        "TRANSPORT": "stdio"
    }
    }
}
}

Or run via Poetry:
{
"mcpServers": {
    "gmail": {
    "command": "poetry",
    "args": ["run", "python", "-m", "gmail_mcp"],
    "cwd": "/path/to/gmail-mcp-server",
    "env": {
        "TRANSPORT": "stdio"
    }
    }
}
}

#### Replit Production (HTTP transport)

For HTTP/SSE transport, Claude clients connect via URL. The Replit deployment exposes an HTTP endpoint:

https://your-replit-app.replit.app/mcp

Configure in Claude's MCP settings (varies by client):
- Claude Desktop: Not yet supported for HTTP (stdio only)
- Claude Code: HTTP MCP servers configured via URL in settings
- Custom clients: Use MCP SDK's HTTP client

Server-side (Replit):
```
# __main__.py detects TRANSPORT=http and starts HTTP server
mcp.run(transport="http", host="0.0.0.0", port=int(os.getenv("PORT", "3000")))
```

---
#### Replit Deployment Notes

1. Environment variables (set in Replit Secrets):
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
TOKEN_ENCRYPTION_KEY=<64-char hex>
TRANSPORT=http
PORT=3000

2. **⚠️ OAuth on Replit - Device Flow Does NOT Work for Gmail:**
   Device flow cannot be used with Gmail scopes (see "Known Limitations" above).

   **Alternative authentication strategies for Replit:**
   - **Option A (Recommended):** Pre-authenticate locally using `run_local_server()`,
     then copy the encrypted token file (`~/.gmail-mcp/tokens/default.token.enc`)
     to Replit's persistent storage
   - **Option B:** Use Google Workspace service account with domain-wide delegation
     (requires Workspace admin access)
   - **Option C:** Build a web OAuth flow with Replit URL as redirect URI
     (requires additional implementation)

3. Token persistence: Store in Replit's persistent storage path

## Plan Files

| Plan | Description |
|------|-------------|
| `~/.claude/plans/woolly-baking-cray.md` | Original implementation plan (architecture, phases, wave strategy) |
| `~/.claude/plans/enchanted-shimmying-squirrel.md` | Wave 5 final validation plan |
| `~/.claude/plans/dazzling-sparking-hollerith.md`  | Wave 6 Oauth hook            |

# Gmail MCP Server

An MCP (Model Context Protocol) server that enables Claude to manage Gmail inboxes through natural conversation. Ask Claude to triage your inbox, search emails, send messages, and more.

## Features

- **16 Gmail Tools** - Full inbox management via conversational AI
- **Read-Only Mode** - Run with `READ_ONLY=true` for safe cross-project use (9 tools, single OAuth scope)
- **Human-in-the-Loop Security** - All write operations require explicit approval
- **Encrypted Token Storage** - AES-256-GCM encryption for OAuth tokens at rest
- **Rate Limiting** - Token bucket protection (100 req/min default)
- **Multiple Transports** - stdio (local), HTTP/SSE (remote deployments)

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- Google Cloud project with Gmail API enabled

### 1. Install

```bash
git clone https://github.com/your-org/gmail-mcp-server.git
cd gmail-mcp-server
poetry install
```

### 2. Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create OAuth 2.0 Client ID with type **"Desktop app"** (required for local server flow)
3. Enable Gmail API in your project
4. Note your Client ID and Client Secret

### 3. Environment Variables

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export TOKEN_ENCRYPTION_KEY=$(openssl rand -hex 32)
```

### 4. Add to Claude Code

Create or update `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "gmail": {
      "command": "poetry",
      "args": ["run", "python", "-m", "gmail_mcp"],
      "cwd": "/path/to/gmail-mcp-server",
      "env": {
        "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
        "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}",
        "TOKEN_ENCRYPTION_KEY": "${TOKEN_ENCRYPTION_KEY}"
      }
    }
  }
}
```

### 5. Verify Connection

Restart Claude Code, then run `/mcp` to verify the Gmail server is connected.

---

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth 2.0 Client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 Client Secret |
| `TOKEN_ENCRYPTION_KEY` | 64-character hex string (256-bit AES key) |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `READ_ONLY` | `false` | Read-only mode — only `gmail.readonly` scope, no write tools |
| `TRANSPORT` | `stdio` | Transport mode: `stdio`, `http`, `sse`, `streamable-http` |
| `PORT` | `3000` | HTTP server port (for http/sse transport) |
| `OAUTH_PORT` | `3000` | OAuth callback port (fallback: 3001, 3002) |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `RATE_LIMIT_MAX` | `100` | Max requests per minute per user |
| `HITL_TIMEOUT_MS` | `300000` | Approval expiration (5 min default) |
| `TOKEN_STORAGE_PATH` | `~/.gmail-mcp/tokens/` | Custom token storage location |

### Transport Modes

| Mode | Use Case |
|------|----------|
| `stdio` | Local development with Claude Code/Desktop |
| `http` / `sse` | Remote deployments (Replit, Docker) |
| `streamable-http` | Stateless deployments |

### Read-Only Mode

Set `READ_ONLY=true` for safe, read-only Gmail access — ideal for a global MCP config shared across all projects.

**What changes:**

| | Full Mode (default) | Read-Only Mode |
|---|---|---|
| OAuth scopes | 4 scopes (readonly, modify, compose, labels) | 1 scope (`gmail.readonly`) |
| Tools registered | 16 (3 auth + 7 read + 6 write) | 9 (3 auth + 6 read) |
| Write tools visible | Yes (with HITL approval) | No — Claude can't see them |
| Consent screen | 4 checkboxes | 1 checkbox |

**Global read-only config** (`~/.claude/.mcp.json`):

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
        "READ_ONLY": "true"
      }
    }
  }
}
```

To override in a specific project (e.g., for full access), add a project-level `.mcp.json` without `READ_ONLY` or set it to `"false"`.

**Note:** Switching between modes requires re-authentication (`gmail_login`) since Google doesn't upgrade scopes on existing tokens.

---

## User Guide

### Authentication Tools

| Tool | Purpose |
|------|---------|
| `gmail_login` | Sign in via Google OAuth (opens browser) |
| `gmail_logout` | Sign out and clear stored tokens |
| `gmail_get_auth_status` | Check if authenticated |

**Example prompts:**
- "Sign me into Gmail"
- "Am I logged into Gmail?"
- "Sign out of Gmail"

---

### Read Operations

These tools read data without modifying your inbox. No approval required.

| Tool | Description | Read-Only |
|------|-------------|-----------|
| `gmail_triage_inbox` | Categorize emails by urgency (urgent, social, newsletter, other) | Yes |
| `gmail_search` | Search using Gmail query syntax | Yes |
| `gmail_summarize_thread` | Get full thread content for summarization | Yes |
| `gmail_draft_reply` | Get context for composing a reply | Yes |
| `gmail_chat_inbox` | Natural language inbox queries | Yes |
| `gmail_download_email` | Download email as .eml, HTML, and attachments | Yes |
| `gmail_apply_labels` | Add or remove labels from messages | No* |

*`gmail_apply_labels` requires `gmail.modify` scope and is excluded in read-only mode.

**Example prompts:**

```
"Triage my inbox"
"Show me unread emails from today"
"Search for emails from boss@company.com"
"Find emails with attachments from last week"
"Summarize this email thread"
"Help me reply to this email"
"Add the 'Important' label to these messages"
```

**Gmail Query Syntax (for `gmail_search`):**
- `from:sender@example.com` - From specific sender
- `to:recipient@example.com` - To specific recipient
- `subject:keyword` - Subject contains keyword
- `after:2024/01/01` - After date
- `has:attachment` - Has attachments
- `is:unread` - Unread messages
- `label:important` - Specific label

---

### Write Operations (HITL Required)

All write operations use **Human-in-the-Loop** approval:

1. Tool returns a preview + `approval_id`
2. Claude shows you the preview and asks for confirmation
3. You approve, tool executes with the `approval_id`

| Tool | Description |
|------|-------------|
| `gmail_send_email` | Compose and send emails |
| `gmail_archive_email` | Remove from inbox (keeps in All Mail) |
| `gmail_delete_email` | Move to trash (deleted after 30 days) |
| `gmail_unsubscribe` | Extract unsubscribe link from newsletters |
| `gmail_create_label` | Create a new label |
| `gmail_organize_labels` | Rename, delete, or update label visibility |

**Example prompts:**

```
"Send an email to john@example.com about the meeting tomorrow"
"Archive all newsletters from this week"
"Delete these promotional emails"
"Help me unsubscribe from this newsletter"
"Create a label called 'Projects'"
"Rename the 'Old' label to 'Archive'"
```

**Approval Flow Example:**

```
You: "Send an email to john@example.com about the meeting"

Claude: "I'll compose this email for you:

To: john@example.com
Subject: Meeting Tomorrow
Body: Hi John, I wanted to confirm our meeting tomorrow at 2pm...

Would you like me to send this?"

You: "Yes, send it"

Claude: "Email sent successfully!"
```

---

## How It Works

### Architecture

```
┌──────────┐      ┌─────────┐      ┌─────────────────┐      ┌───────────┐
│   User   │ <──> │  Claude │ <──> │ Gmail MCP Server│ <──> │ Gmail API │
└──────────┘      └─────────┘      └─────────────────┘      └───────────┘
                       │                    │
                       │              ┌─────┴─────┐
                   MCP Protocol       │  Encrypted │
                  (JSON-RPC)          │   Tokens   │
                                      └───────────┘
```

### Security Model

| Layer | Protection |
|-------|------------|
| **HITL Approval** | All write operations require explicit user confirmation |
| **Token Encryption** | AES-256-GCM with unique IV per token |
| **Rate Limiting** | Token bucket algorithm prevents API quota exhaustion |
| **Audit Logging** | JSON-formatted logs to stderr for all operations |
| **Input Validation** | Pydantic schemas validate all tool parameters |

### HITL Two-Step Flow

```python
# Step 1: No approval_id → Return preview
{
  "status": "pending_approval",
  "approval_id": "uuid-here",
  "expires_at": "2024-01-01T12:05:00Z",
  "preview": { "to": "...", "subject": "...", "body": "..." },
  "message": "ACTION NOT TAKEN. Please review and confirm."
}

# Step 2: With approval_id → Execute
{
  "status": "success",
  "data": { "message_id": "..." }
}
```

Approvals expire after 5 minutes (configurable via `HITL_TIMEOUT_MS`).

### Project Structure

```
gmail_mcp/
├── __main__.py           # Entry point, transport selection
├── server.py             # FastMCP server, tool registration
├── tools/
│   ├── auth/             # gmail_login, gmail_logout, gmail_get_auth_status
│   ├── read/             # 6 read-only tools
│   └── write/            # 6 HITL-protected write tools
├── auth/
│   ├── oauth.py          # Google OAuth flow (local server)
│   ├── tokens.py         # AES-256-GCM encryption
│   └── storage.py        # Encrypted file storage
├── gmail/
│   ├── client.py         # Authenticated Gmail API client
│   ├── messages.py       # Message operations
│   ├── threads.py        # Thread operations
│   └── labels.py         # Label management
├── hitl/
│   ├── manager.py        # Approval lifecycle
│   └── models.py         # Pydantic models
├── middleware/
│   ├── rate_limiter.py   # Token bucket rate limiting
│   ├── audit_logger.py   # JSON logging to stderr
│   └── validator.py      # Input validation
└── schemas/
    └── tools.py          # Tool parameter models
```

---

## Troubleshooting

### Port Already in Use

```
OSError: [Errno 48] Address already in use
```

The OAuth callback server tries ports 3000, 3001, 3002 in sequence. To use a different port:

```bash
export OAUTH_PORT=4000
```

### Browser Doesn't Open

If running in a headless environment (SSH, Docker):
1. Copy the URL from the logs and open manually
2. Or pre-authenticate locally and copy the token file to the server

### "Loopback Flow Has Been Blocked" (Error 400)

Your OAuth client type is incorrect. Google blocks loopback redirects for non-desktop apps.

**Fix:** In [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
1. Delete the existing OAuth client
2. Create new OAuth 2.0 Client ID with type **"Desktop app"**
3. Update your environment variables with new credentials

### Token Storage Errors

- Ensure `~/.gmail-mcp/tokens/` exists and is writable
- Verify `TOKEN_ENCRYPTION_KEY` is exactly 64 hex characters
- If key changed, delete old token files and re-authenticate

### State Mismatch Error

CSRF protection triggered. Don't reuse browser tabs from old auth attempts. Restart the login flow.

### Authentication Fails Silently

Check logs with `LOG_LEVEL=DEBUG`:

```bash
LOG_LEVEL=DEBUG python -m gmail_mcp
```

---

## Development

### Setup

```bash
poetry install
poetry shell
```

### Run Tests

```bash
pytest --cov
```

### Code Quality

```bash
ruff check . && ruff format . && mypy .
```

### Run Server Locally

```bash
# stdio transport (default)
python -m gmail_mcp

# HTTP transport
TRANSPORT=http python -m gmail_mcp
```

---

## Known Limitations

1. **Single-User Mode** - Currently operates with `user_id="default"`. For multi-account, run separate server instances with different `TOKEN_STORAGE_PATH`.

2. **No Device Flow** - Gmail scopes are "restricted" and cannot use device flow. Local server flow requires a browser.

3. **Headless Deployments** - Require workarounds:
   - Pre-authenticate locally, copy token file to server
   - Use Google Workspace service account with domain-wide delegation

---

## License

MIT

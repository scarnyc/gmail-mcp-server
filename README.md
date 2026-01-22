# gmail-mcp-server

MCP server enabling Claude to manage Gmail inboxes via conversational interface.

## Setup

```bash
poetry install && poetry shell
```

## Usage

```bash
# stdio transport (local MCP)
python -m gmail_mcp

# HTTP transport (remote)
TRANSPORT=http python -m gmail_mcp
```

## Configuration

Copy `.env.example` to `.env` and configure your Google OAuth credentials.

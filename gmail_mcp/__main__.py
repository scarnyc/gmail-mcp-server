"""Entry point for Gmail MCP Server."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv


def configure_logging() -> None:
    """Configure logging to stderr (STDIO-safe).

    Sends all logs to stderr so they don't interfere with MCP's
    STDIO transport which uses stdout for JSON-RPC messages.

    Respects LOG_LEVEL env var (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = logging.getLevelNamesMapping().get(log_level_str, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )
    # Reduce noise from Google libraries
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)


def validate_environment() -> bool:
    """Validate required environment variables.

    Returns:
        True if all required variables are present and valid, False otherwise.
    """
    logger = logging.getLogger(__name__)

    required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "TOKEN_ENCRYPTION_KEY"]
    missing = [var for var in required if not os.getenv(var)]

    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        return False

    # TOKEN_ENCRYPTION_KEY must be 64 hex chars (256 bits)
    key = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    if len(key) != 64:
        logger.error("TOKEN_ENCRYPTION_KEY must be 64 hex characters (256 bits)")
        return False

    # Validate key is valid hex
    try:
        bytes.fromhex(key)
    except ValueError:
        logger.error("TOKEN_ENCRYPTION_KEY must be valid hexadecimal")
        return False

    return True


def main() -> None:
    """Main entry point.

    Loads environment, validates configuration, and starts the MCP server
    with the appropriate transport (stdio or http).
    """
    # Load .env file if present
    load_dotenv()

    # Configure logging first
    configure_logging()
    logger = logging.getLogger(__name__)

    # Validate environment
    if not validate_environment():
        logger.error("Environment validation failed. Exiting.")
        sys.exit(1)

    # Import server after environment is validated
    from gmail_mcp.server import mcp

    # Select transport based on environment
    transport = os.getenv("TRANSPORT", "stdio").lower()

    match transport:
        case "sse" | "http":
            # SSE transport for remote deployments (Replit, etc.)
            # Use uvicorn for custom host/port configuration
            host = os.getenv("HOST", "0.0.0.0")
            port = int(os.getenv("PORT", "3000"))
            logger.info(
                "Starting Gmail MCP Server with SSE transport on %s:%d", host, port
            )
            try:
                import uvicorn

                uvicorn.run(mcp.sse_app(), host=host, port=port, log_level="info")
            except ImportError:
                logger.error("uvicorn required for SSE transport: pip install uvicorn")
                sys.exit(1)
        case "streamable-http":
            # Streamable HTTP for stateless deployments
            logger.info("Starting Gmail MCP Server with streamable-http transport")
            mcp.run(transport="streamable-http")
        case _:
            # STDIO transport for local development (default)
            logger.info("Starting Gmail MCP Server with STDIO transport")
            mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

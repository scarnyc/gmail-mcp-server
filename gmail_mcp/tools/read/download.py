"""Gmail email download tool.

Downloads an email as .eml file, saves HTML body as .html,
and extracts file attachments to a local directory.
"""

from __future__ import annotations

import email
import email.policy
import logging
import re
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from gmail_mcp.gmail.client import gmail_client
from gmail_mcp.gmail.messages import (
    get_attachment_data,
    get_message,
    get_raw_message,
    parse_headers,
)
from gmail_mcp.schemas.tools import DownloadEmailParams
from gmail_mcp.tools.base import (
    build_error_response,
    build_success_response,
    execute_tool,
)
from gmail_mcp.utils.errors import GmailMCPError

logger = logging.getLogger(__name__)

MAX_FILENAME_LENGTH = 100


def _sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_ ")
    return sanitized[:MAX_FILENAME_LENGTH] or "email"


def _build_filename(prefix: str, subject: str, date_str: str) -> str:
    """Build a clean filename base from prefix, subject, and date."""
    date_part = ""
    if date_str:
        try:
            dt = parsedate_to_datetime(date_str)
            date_part = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date_part = _sanitize_filename(date_str)

    subject_part = _sanitize_filename(subject) if subject else "no_subject"
    parts = [p for p in [prefix, subject_part, date_part] if p]
    return "_".join(parts)


def _extract_html_body(msg: email.message.EmailMessage) -> str | None:
    """Extract the HTML body from a parsed email message."""
    if msg.get_content_type() == "text/html":
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")

    return None


def _extract_attachments(
    msg: email.message.EmailMessage,
) -> list[tuple[str, bytes]]:
    """Extract file attachments from a parsed email."""
    attachments: list[tuple[str, bytes]] = []

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        filename = part.get_filename()

        if filename or "attachment" in content_disposition:
            data = part.get_payload(decode=True)
            if data:
                safe_name = _sanitize_filename(filename or "attachment")
                if filename and "." in filename:
                    ext = filename.rsplit(".", 1)[-1][:10]
                    if not safe_name.endswith(f".{ext}"):
                        safe_name = f"{safe_name}.{ext}"
                attachments.append((safe_name, data))

    return attachments


async def gmail_download_email(
    params: DownloadEmailParams, user_id: str = "default"
) -> dict[str, Any]:
    """Download an email as .eml, .html, and extracted attachments.

    Fetches the raw RFC 2822 email via Gmail API, saves it as .eml,
    saves any HTML body as .html, and extracts file attachments
    to the output directory.

    Args:
        params: Download parameters (message_id, output_dir, filename_prefix).
        user_id: User identifier for Gmail authentication.

    Returns:
        Standardized response with paths to all saved files.

    Example response:
        {
            "status": "success",
            "data": {
                "eml_path": "/path/to/email.eml",
                "html_path": "/path/to/email.html",
                "attachments": ["/path/to/invoice.pdf"],
                "subject": "Your Receipt",
                "from": "billing@example.com",
                "date": "2025-01-20"
            },
            "message": "Downloaded email: eml, html, 1 attachment"
        }
    """

    def _execute() -> dict[str, Any]:
        service = gmail_client.get_service(user_id)

        # 1. Fetch raw email bytes
        raw_bytes = get_raw_message(service, params.message_id)

        # 2. Get metadata for filename construction
        metadata = get_message(service, params.message_id, format="metadata")
        headers = parse_headers(metadata)
        subject = headers.get("Subject", "")
        date_str = headers.get("Date", "")
        from_addr = headers.get("From", "")

        # 3. Build filename base and create output directory
        filename_base = _build_filename(params.filename_prefix, subject, date_str)
        output_path = Path(params.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        saved_files: dict[str, Any] = {
            "subject": subject,
            "from": from_addr,
            "date": date_str,
        }

        # 4. Save .eml file
        eml_path = output_path / f"{filename_base}.eml"
        eml_path.write_bytes(raw_bytes)
        saved_files["eml_path"] = str(eml_path)
        logger.info("Saved .eml: %s", eml_path)

        # 5. Parse email for HTML body and attachments
        msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

        # 6. Save HTML body as .html (if available)
        html_body = _extract_html_body(msg)
        if html_body:
            html_path = output_path / f"{filename_base}.html"
            html_path.write_text(html_body, encoding="utf-8")
            saved_files["html_path"] = str(html_path)
            logger.info("Saved HTML: %s", html_path)
        else:
            saved_files["html_path"] = None

        # 7. Extract and save attachments
        attachments = _extract_attachments(msg)
        attachment_paths: list[str] = []
        for att_name, att_data in attachments:
            att_path = output_path / f"{filename_base}_{att_name}"
            att_path.write_bytes(att_data)
            attachment_paths.append(str(att_path))
            logger.info("Saved attachment: %s", att_path)

        # 8. Check Gmail API metadata for large attachments
        payload = metadata.get("payload", {})
        for part in payload.get("parts", []):
            att_id = part.get("body", {}).get("attachmentId")
            api_filename = part.get("filename", "")
            if att_id and api_filename:
                safe_api_name = _sanitize_filename(api_filename)
                already_saved = any(safe_api_name in p for p in attachment_paths)
                if not already_saved:
                    try:
                        att_data = get_attachment_data(
                            service, params.message_id, att_id
                        )
                        att_path = output_path / f"{filename_base}_{safe_api_name}"
                        att_path.write_bytes(att_data)
                        attachment_paths.append(str(att_path))
                        logger.info("Saved API attachment: %s", att_path)
                    except Exception as e:
                        logger.warning(
                            "Failed to download attachment %s: %s",
                            api_filename,
                            e,
                        )

        saved_files["attachments"] = attachment_paths

        # Build summary message
        parts_saved = ["eml"]
        if saved_files.get("html_path"):
            parts_saved.append("html")
        att_count = len(attachment_paths)
        if att_count:
            parts_saved.append(f"{att_count} attachment{'s' if att_count != 1 else ''}")

        return build_success_response(
            data=saved_files,
            message=f"Downloaded email: {', '.join(parts_saved)}",
            count=len(attachment_paths),
        )

    try:
        return await execute_tool(
            tool_name="gmail_download_email",
            params=params.model_dump(),
            operation=_execute,
            user_id=user_id,
        )
    except GmailMCPError as e:
        logger.error("Download failed: %s", e)
        return build_error_response(
            error=str(e),
            error_code=e.__class__.__name__,
        )
    except Exception as e:
        logger.exception("Unexpected error in gmail_download_email")
        return build_error_response(
            error=f"Unexpected error: {e}",
            error_code="UnexpectedError",
        )

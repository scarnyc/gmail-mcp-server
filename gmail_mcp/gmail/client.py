"""Authenticated Gmail API client factory."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from gmail_mcp.auth.oauth import GMAIL_SCOPES, GOOGLE_TOKEN_URI
from gmail_mcp.auth.storage import token_storage
from gmail_mcp.utils.errors import AuthenticationError

logger = logging.getLogger(__name__)


class GmailClient:
    """Factory for authenticated Gmail API services.

    Handles token loading, validation, refresh, and caching of Gmail API
    service objects per user.
    """

    def __init__(self) -> None:
        self._services: dict[str, Resource] = {}
        self._credentials: dict[str, Credentials] = {}
        self._lock = threading.Lock()

    def get_service(self, user_id: str = "default") -> Resource:
        """Get authenticated Gmail API service for user.

        Args:
            user_id: User identifier (defaults to "default").

        Returns:
            Gmail API Resource object.

        Raises:
            AuthenticationError: If user is not authenticated or token refresh fails.
        """
        with self._lock:
            # Check cache
            if user_id in self._services:
                creds = self._credentials.get(user_id)
                if creds and creds.valid:
                    return self._services[user_id]
                # Token expired, try refresh
                if creds and creds.expired and creds.refresh_token:
                    try:
                        return self._refresh_and_cache(user_id, creds)
                    except Exception as e:
                        logger.warning("Token refresh failed for %s: %s", user_id, e)
                        self._invalidate_unlocked(user_id)

            # Load from storage
            token_data = token_storage.load(user_id)
            if not token_data:
                raise AuthenticationError(
                    f"User {user_id} not authenticated. "
                    "Please complete OAuth flow first."
                )

            # Build credentials
            creds = self._build_credentials(token_data)

            # Check if refresh needed
            if creds.expired and creds.refresh_token:
                try:
                    return self._refresh_and_cache(user_id, creds)
                except Exception as e:
                    logger.error("Token refresh failed: %s", e)
                    raise AuthenticationError(f"Token refresh failed: {e}") from e

            if not creds.valid:
                raise AuthenticationError(
                    f"Invalid credentials for {user_id}. Please re-authenticate."
                )

            # Build and cache service
            service = build("gmail", "v1", credentials=creds)
            self._services[user_id] = service
            self._credentials[user_id] = creds

            logger.info("Created Gmail service for user %s", user_id)
            return service

    def _build_credentials(self, token_data: dict[str, Any]) -> Credentials:
        """Build Credentials object from token data."""
        expiry = None
        if "expiry" in token_data:
            try:
                expiry = datetime.fromisoformat(token_data["expiry"])
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse token expiry '%s': %s",
                    token_data.get("expiry"),
                    e,
                )

        return Credentials(  # type: ignore[no-untyped-call]
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", GOOGLE_TOKEN_URI),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", GMAIL_SCOPES),
            expiry=expiry,
        )

    def _refresh_and_cache(self, user_id: str, creds: Credentials) -> Resource:
        """Refresh credentials and rebuild service."""
        from google.auth.transport.requests import Request

        creds.refresh(Request())

        # Update stored token
        # NOTE: client_secret is NOT stored for security - retrieved from env at refresh
        token_data = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "scopes": list(creds.scopes) if creds.scopes else GMAIL_SCOPES,
        }
        if creds.expiry:
            token_data["expiry"] = creds.expiry.isoformat()

        token_storage.save(user_id, token_data)

        # Rebuild service
        service = build("gmail", "v1", credentials=creds)
        self._services[user_id] = service
        self._credentials[user_id] = creds

        logger.info("Refreshed token and rebuilt service for %s", user_id)
        return service

    def _invalidate_unlocked(self, user_id: str) -> None:
        """Clear cached service for user (must hold lock)."""
        self._services.pop(user_id, None)
        self._credentials.pop(user_id, None)
        logger.debug("Invalidated cache for user %s", user_id)

    def invalidate(self, user_id: str) -> None:
        """Clear cached service for user."""
        with self._lock:
            self._invalidate_unlocked(user_id)

    def is_authenticated(self, user_id: str = "default") -> bool:
        """Check if user has valid stored credentials."""
        return token_storage.exists(user_id)


# Global singleton
gmail_client = GmailClient()

"""Rate limiting middleware using token bucket algorithm."""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

from gmail_mcp.utils.errors import RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class Bucket:
    """Token bucket for rate limiting."""

    tokens: float
    last_update: float
    max_tokens: float
    refill_rate: float  # tokens per second


class RateLimiter:
    """Per-user rate limiter using token bucket algorithm.

    Each user has their own bucket that refills at a constant rate.
    Requests consume tokens; when empty, requests are rejected.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int = 60,
    ):
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window.
                Defaults to RATE_LIMIT_MAX env var or 100.
            window_seconds: Time window in seconds (default 60).
        """
        self._max_requests = max_requests or int(os.getenv("RATE_LIMIT_MAX", "100"))
        self._window_seconds = window_seconds
        self._refill_rate = self._max_requests / window_seconds
        self._buckets: dict[str, Bucket] = {}
        self._lock = threading.Lock()

        logger.info(
            "RateLimiter initialized: %d requests per %d seconds",
            self._max_requests,
            window_seconds,
        )

    def _get_bucket(self, user_id: str) -> Bucket:
        """Get or create bucket for user."""
        if user_id not in self._buckets:
            self._buckets[user_id] = Bucket(
                tokens=float(self._max_requests),
                last_update=time.monotonic(),
                max_tokens=float(self._max_requests),
                refill_rate=self._refill_rate,
            )
        return self._buckets[user_id]

    def _refill(self, bucket: Bucket) -> None:
        """Refill bucket based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket.last_update
        bucket.tokens = min(
            bucket.max_tokens,
            bucket.tokens + elapsed * bucket.refill_rate,
        )
        bucket.last_update = now

    def check(self, user_id: str = "default") -> bool:
        """Check if request is allowed without consuming a token.

        Args:
            user_id: User identifier.

        Returns:
            True if request would be allowed, False otherwise.
        """
        with self._lock:
            bucket = self._get_bucket(user_id)
            self._refill(bucket)
            return bucket.tokens >= 1.0

    def consume(self, user_id: str = "default", tokens: int = 1) -> None:
        """Consume tokens for a request.

        Args:
            user_id: User identifier.
            tokens: Number of tokens to consume.

        Raises:
            RateLimitError: If not enough tokens available.
        """
        with self._lock:
            bucket = self._get_bucket(user_id)
            self._refill(bucket)

            if bucket.tokens < tokens:
                wait_time = (tokens - bucket.tokens) / bucket.refill_rate
                logger.warning(
                    "Rate limit exceeded for %s. Retry after %.1f seconds",
                    user_id,
                    wait_time,
                )
                raise RateLimitError(
                    f"Rate limit exceeded. Retry after {wait_time:.1f} seconds.",
                    details={
                        "user_id": user_id,
                        "retry_after_seconds": round(wait_time, 1),
                        "remaining": int(bucket.tokens),
                    },
                )

            bucket.tokens -= tokens
            logger.debug(
                "Consumed %d token(s) for %s. Remaining: %.1f",
                tokens,
                user_id,
                bucket.tokens,
            )

    def remaining(self, user_id: str = "default") -> int:
        """Get remaining tokens for user.

        Args:
            user_id: User identifier.

        Returns:
            Number of remaining tokens (rounded down).
        """
        with self._lock:
            bucket = self._get_bucket(user_id)
            self._refill(bucket)
            return int(bucket.tokens)

    def reset(self, user_id: str) -> None:
        """Reset bucket for user to full capacity."""
        with self._lock:
            if user_id in self._buckets:
                del self._buckets[user_id]
                logger.debug("Reset rate limit bucket for %s", user_id)

    def cleanup_stale(self, max_age_seconds: float = 3600) -> int:
        """Remove stale buckets that haven't been used recently.

        This prevents unbounded memory growth from inactive users.

        Args:
            max_age_seconds: Maximum age since last update to keep bucket.
                Defaults to 1 hour.

        Returns:
            Number of buckets removed.
        """
        now = time.monotonic()
        removed = 0

        with self._lock:
            stale_users = [
                user_id
                for user_id, bucket in self._buckets.items()
                if now - bucket.last_update > max_age_seconds
            ]

            for user_id in stale_users:
                del self._buckets[user_id]
                removed += 1

            if removed > 0:
                logger.debug(
                    "Cleaned up %d stale rate limit buckets (older than %ds)",
                    removed,
                    max_age_seconds,
                )

        return removed


# Global singleton
rate_limiter = RateLimiter()

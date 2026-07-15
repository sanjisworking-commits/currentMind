"""Shared validation helpers used across domain models.

Centralizes UTC timestamp normalization, HTTP(S) URL validation, and
non-empty text validation so individual domain models do not each
reimplement the same rules.
"""

from datetime import UTC, datetime
from urllib.parse import urlparse


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize aware datetimes to UTC."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def validate_http_url(value: str) -> str:
    """Validate that a string is an absolute HTTP or HTTPS URL."""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must use the http or https scheme")
    if not parsed.netloc:
        raise ValueError("URL must include a network location")
    return value


def non_empty_text(value: str) -> str:
    """Reject empty or whitespace-only strings, returning the stripped value."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("value must not be empty or whitespace-only")
    return stripped

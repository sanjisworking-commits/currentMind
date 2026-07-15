"""Indian Express UPSC Current Affairs RSS source adapter.

Implements `ArticleSource` by fetching the feed over HTTP with `httpx`,
parsing it with `feedparser`, and mapping each entry into a source-neutral
`ArticleCandidate`. No feedparser or Indian Express-specific structure ever
leaves this module.
"""

import html
import logging
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
from pydantic import ValidationError

from app.application.sources import ArticleSourceError
from app.domain.article import ArticleCandidate

logger = logging.getLogger(__name__)

SOURCE_NAME = "indian_express"
DEFAULT_TIMEOUT_SECONDS = 10.0
USER_AGENT = "CurrentMind/0.1 (+personal UPSC study tool)"


class _TagStripper(HTMLParser):
    """Extracts plain text from a string, discarding any HTML tags."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _strip_tags(text: str) -> str:
    stripper = _TagStripper()
    stripper.feed(text)
    stripper.close()
    return stripper.get_text()


def _clean_text(value: Any) -> str:
    """Unescape HTML entities, strip any tags, and normalize whitespace."""
    if not isinstance(value, str):
        return ""
    unescaped = html.unescape(value)
    stripped = _strip_tags(unescaped)
    return " ".join(stripped.split())


def _external_id(entry: Any) -> str | None:
    entry_id = entry.get("id")
    if isinstance(entry_id, str) and entry_id.strip():
        return entry_id.strip()
    guid = entry.get("guid")
    if isinstance(guid, str) and guid.strip():
        return guid.strip()
    return None


def _published_at(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct is None:
            continue
        try:
            year, month, day, hour, minute, second = struct[:6]
            return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
        except (TypeError, ValueError):
            continue
    return None


def _categories(entry: Any) -> list[str]:
    seen: set[str] = set()
    categories: list[str] = []
    for tag in entry.get("tags") or []:
        term = tag.get("term") if hasattr(tag, "get") else None
        cleaned = _clean_text(term)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        categories.append(cleaned)
    return categories


def _validate_feed_url(value: str) -> str:
    """Strip whitespace and require an absolute http(s) URL with a network location."""
    cleaned = value.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"feed_url must use the http or https scheme, got: {value!r}")
    if not parsed.netloc:
        raise ValueError(f"feed_url must include a network location, got: {value!r}")
    return cleaned


def _entry_to_candidate(entry: Any) -> ArticleCandidate | None:
    """Map one feedparser entry to an `ArticleCandidate`, or `None` if invalid."""
    try:
        candidate = ArticleCandidate(
            source=SOURCE_NAME,
            external_id=_external_id(entry),
            title=_clean_text(entry.get("title", "")),
            url=(entry.get("link") or "").strip(),
            author=_clean_text(entry.get("author", "")) or None,
            published_at=_published_at(entry),
            categories=_categories(entry),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        logger.warning(
            "Skipping invalid RSS entry (link=%r, guid=%r): %s",
            entry.get("link"),
            entry.get("id"),
            exc,
        )
        return None
    return candidate


class IndianExpressRSSSource:
    """Discovers article candidates from the Indian Express UPSC RSS feed."""

    def __init__(
        self,
        feed_url: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._feed_url = _validate_feed_url(feed_url)
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def discover_articles(self) -> list[ArticleCandidate]:
        """Fetch and parse the feed, returning deduplicated article candidates.

        Raises:
            ArticleSourceError: if the feed cannot be fetched, is empty or
                not a recognized RSS/Atom document, cannot be parsed at all,
                or parses to zero usable candidates despite containing
                entries.
        """
        logger.info("RSS fetch started url=%s", self._feed_url)
        content = self._fetch()
        logger.info("RSS fetch completed url=%s bytes=%d", self._feed_url, len(content))

        parsed = feedparser.parse(content)
        entries = parsed.entries

        if parsed.bozo:
            if not entries:
                logger.error(
                    "RSS feed unparseable url=%s reason=%s",
                    self._feed_url,
                    parsed.get("bozo_exception"),
                )
                raise ArticleSourceError(
                    f"RSS feed at {self._feed_url} could not be parsed"
                ) from parsed.get("bozo_exception")
            logger.warning(
                "RSS feed not well-formed but %d entries recovered url=%s",
                len(entries),
                self._feed_url,
            )

        logger.info("Parsed %d RSS entries url=%s", len(entries), self._feed_url)

        if not entries:
            if not parsed.get("version"):
                logger.error(
                    "RSS feed url=%s is empty or not a recognized feed format", self._feed_url
                )
                raise ArticleSourceError(
                    f"RSS feed at {self._feed_url} is empty or not a recognized feed"
                )
            logger.info("RSS feed url=%s contained zero entries", self._feed_url)
            return []

        candidates: list[ArticleCandidate] = []
        seen_external_ids: set[str] = set()
        seen_urls: set[str] = set()
        invalid_count = 0
        duplicate_count = 0

        for entry in entries:
            candidate = _entry_to_candidate(entry)
            if candidate is None:
                invalid_count += 1
                continue

            is_duplicate = (
                candidate.external_id is not None and candidate.external_id in seen_external_ids
            ) or candidate.url in seen_urls
            if is_duplicate:
                duplicate_count += 1
                continue

            if candidate.external_id is not None:
                seen_external_ids.add(candidate.external_id)
            seen_urls.add(candidate.url)
            candidates.append(candidate)

        if not candidates:
            logger.error(
                "RSS feed url=%s parsed %d entries but produced zero usable "
                "candidates (invalid=%d, duplicates=%d)",
                self._feed_url,
                len(entries),
                invalid_count,
                duplicate_count,
            )
            raise ArticleSourceError(
                f"RSS feed at {self._feed_url} produced no usable article candidates"
            )

        logger.info(
            "Discovered %d article candidates from %s (invalid=%d, duplicates=%d)",
            len(candidates),
            self._feed_url,
            invalid_count,
            duplicate_count,
        )
        return candidates

    def _fetch(self) -> bytes:
        headers = {"User-Agent": USER_AGENT}
        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                transport=self._transport,
                headers=headers,
            ) as client:
                response = client.get(self._feed_url)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error(
                "RSS fetch timed out url=%s timeout=%s", self._feed_url, self._timeout_seconds
            )
            raise ArticleSourceError(
                f"Timed out fetching RSS feed at {self._feed_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "RSS fetch returned non-success status url=%s status=%s",
                self._feed_url,
                exc.response.status_code,
            )
            raise ArticleSourceError(
                f"RSS feed at {self._feed_url} returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("RSS fetch failed url=%s error=%s", self._feed_url, exc)
            raise ArticleSourceError(f"Failed to fetch RSS feed at {self._feed_url}") from exc
        return response.content

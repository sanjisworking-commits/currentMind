import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.application.sources import ArticleSourceError
from app.infrastructure.rss_source import USER_AGENT, IndianExpressRSSSource

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "rss"
FEED_URL = "https://indianexpress.com/feed"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _transport_returning(fixture_name: str, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=_fixture_bytes(fixture_name))

    return httpx.MockTransport(handler)


def _transport_recording(
    fixture_name: str, calls: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=_fixture_bytes(fixture_name))

    return httpx.MockTransport(handler)


def _transport_returning_bytes(content: bytes, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=content)

    return httpx.MockTransport(handler)


def _source(transport: httpx.MockTransport, **kwargs: float) -> IndianExpressRSSSource:
    return IndianExpressRSSSource(feed_url=FEED_URL, transport=transport, **kwargs)


# --- Valid entry mapping -----------------------------------------------------


def test_valid_entry_mapping_and_utc_dates() -> None:
    source = _source(_transport_returning("valid_feed.xml"))

    candidates = source.discover_articles()

    assert len(candidates) == 2
    first = candidates[0]
    assert first.source == "indian_express"
    assert first.title == "Cabinet approves new scheme for rural development"
    assert first.url == "https://indianexpress.com/article/one"
    assert first.external_id == "ie-article-one"
    assert first.author == "Jane Doe"
    assert first.categories == ["Polity", "Governance"]
    assert first.published_at == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    assert first.published_at is not None
    assert first.published_at.tzinfo == UTC


def test_preserves_feed_order() -> None:
    source = _source(_transport_returning("valid_feed.xml"))

    candidates = source.discover_articles()

    assert [c.url for c in candidates] == [
        "https://indianexpress.com/article/one",
        "https://indianexpress.com/article/two",
    ]


# --- Missing optional metadata ------------------------------------------------


def test_missing_optional_metadata_is_handled_safely() -> None:
    source = _source(_transport_returning("partial_metadata_feed.xml"))

    candidates = source.discover_articles()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Article missing optional fields"
    assert candidate.author is None
    assert candidate.published_at is None
    assert candidate.categories == []
    assert candidate.external_id is None


def test_malformed_publication_date_does_not_invalidate_entry() -> None:
    source = _source(_transport_returning("malformed_date_feed.xml"))

    candidates = source.discover_articles()

    assert len(candidates) == 1
    assert candidates[0].published_at is None


# --- Malformed required fields / partial success -----------------------------


def test_partial_success_skips_invalid_entries() -> None:
    source = _source(_transport_returning("malformed_entry_feed.xml"))

    candidates = source.discover_articles()

    assert len(candidates) == 1
    assert candidates[0].title == "Valid Article Among Bad Ones"


def test_raises_when_no_usable_candidates() -> None:
    source = _source(_transport_returning("all_invalid_feed.xml"))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


# --- Empty feed ---------------------------------------------------------------


def test_empty_feed_returns_empty_list() -> None:
    source = _source(_transport_returning("empty_feed.xml"))

    assert source.discover_articles() == []


# --- Malformed feed -------------------------------------------------------------


def test_raises_on_unparseable_feed() -> None:
    source = _source(_transport_returning("unparseable_feed.xml"))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


def test_malformed_feed_with_recoverable_entries_still_partially_recovers() -> None:
    source = _source(_transport_returning("bozo_recoverable_feed.xml"))

    candidates = source.discover_articles()

    assert len(candidates) == 2
    assert [c.title for c in candidates] == ["Bad & Article", "Good Article"]


# --- Empty or unrecognized response body ----------------------------------------
# (test_empty_feed_returns_empty_list above already proves a valid, well-formed
# empty RSS feed still returns [] rather than raising.)


def test_raises_on_empty_byte_response() -> None:
    source = _source(_transport_returning_bytes(b""))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


def test_raises_on_whitespace_only_response() -> None:
    source = _source(_transport_returning_bytes(b"   \n\t  "))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


def test_raises_on_non_feed_html_response() -> None:
    html_body = b"<html><head><title>Not a feed</title></head><body>hi</body></html>"
    source = _source(_transport_returning_bytes(html_body))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


# --- Deduplication -------------------------------------------------------------


def test_dedup_same_url_different_external_id() -> None:
    source = _source(_transport_returning("duplicate_entries_feed.xml"))

    candidates = source.discover_articles()

    urls = [c.url for c in candidates]
    assert urls.count("https://indianexpress.com/dup-a") == 1


def test_dedup_same_external_id_different_url() -> None:
    source = _source(_transport_returning("duplicate_entries_feed.xml"))

    candidates = source.discover_articles()

    ids = [c.external_id for c in candidates]
    assert ids.count("dup-id-1") == 1


def test_dedup_first_occurrence_wins_and_order_preserved() -> None:
    source = _source(_transport_returning("duplicate_entries_feed.xml"))

    candidates = source.discover_articles()

    assert [c.external_id for c in candidates] == ["dup-id-1", "dup-id-3"]
    assert candidates[0].title == "First"


# --- HTML entity / tag cleanup --------------------------------------------------


def test_cleans_html_entities_and_tags_in_metadata() -> None:
    source = _source(_transport_returning("html_entities_feed.xml"))

    candidates = source.discover_articles()

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Government & Parliament debate on Article 370"
    assert candidate.categories == ["Polity & Law Section"]


# --- HTTP-level failures --------------------------------------------------------


def test_raises_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    source = _source(httpx.MockTransport(handler))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


def test_raises_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    source = _source(httpx.MockTransport(handler))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


def test_raises_on_non_success_status() -> None:
    source = _source(_transport_returning("valid_feed.xml", status_code=503))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()


# --- Constructor validation ------------------------------------------------------


@pytest.mark.parametrize("timeout_seconds", [0, -1.0])
def test_rejects_non_positive_timeout(timeout_seconds: float) -> None:
    with pytest.raises(ValueError):
        IndianExpressRSSSource(feed_url=FEED_URL, timeout_seconds=timeout_seconds)


@pytest.mark.parametrize(
    "feed_url",
    [
        "",
        "   ",
        "/feed",
        "feed",
        "ftp://example.com/feed",
        "http://",
        "https://",
    ],
    ids=[
        "blank",
        "whitespace-only",
        "relative-absolute-path",
        "relative-bare-word",
        "ftp-scheme",
        "http-missing-netloc",
        "https-missing-netloc",
    ],
)
def test_rejects_invalid_feed_url(feed_url: str) -> None:
    with pytest.raises(ValueError):
        IndianExpressRSSSource(feed_url=feed_url)


@pytest.mark.parametrize(
    "feed_url",
    ["http://example.com/feed", "https://example.com/feed"],
    ids=["http", "https"],
)
def test_accepts_valid_http_and_https_feed_urls(feed_url: str) -> None:
    IndianExpressRSSSource(feed_url=feed_url)


def test_strips_surrounding_whitespace_from_feed_url() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=_fixture_bytes("valid_feed.xml"))

    source = IndianExpressRSSSource(
        feed_url=f"  {FEED_URL}  ", transport=httpx.MockTransport(handler)
    )

    source.discover_articles()

    assert str(calls[0].url) == FEED_URL


# --- Request behaviour: user-agent, redirects, no article-page requests ---------


def test_sends_expected_user_agent() -> None:
    calls: list[httpx.Request] = []
    source = _source(_transport_recording("valid_feed.xml", calls))

    source.discover_articles()

    assert calls[0].headers["user-agent"] == USER_AGENT


def test_follows_redirects() -> None:
    calls: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        if str(request.url) == FEED_URL:
            return httpx.Response(
                302, headers={"location": "https://indianexpress.com/feed-final"}
            )
        return httpx.Response(200, content=_fixture_bytes("valid_feed.xml"))

    source = _source(httpx.MockTransport(handler))

    candidates = source.discover_articles()

    assert len(candidates) == 2
    assert [str(url) for url in calls] == [FEED_URL, "https://indianexpress.com/feed-final"]


def test_only_requests_the_feed_url_never_an_article_page() -> None:
    calls: list[httpx.Request] = []
    source = _source(_transport_recording("valid_feed.xml", calls))

    source.discover_articles()

    assert len(calls) == 1
    assert str(calls[0].url) == FEED_URL


# --- Logging ----------------------------------------------------------------------


def test_logs_lifecycle_events(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.infrastructure.rss_source")
    source = _source(_transport_returning("malformed_entry_feed.xml"))

    source.discover_articles()

    assert "RSS fetch started" in caplog.text
    assert "RSS fetch completed" in caplog.text
    assert "Skipping invalid RSS entry" in caplog.text


def test_logs_error_and_raises_when_no_usable_candidates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.infrastructure.rss_source")
    source = _source(_transport_returning("all_invalid_feed.xml"))

    with pytest.raises(ArticleSourceError):
        source.discover_articles()

    assert "produced zero usable" in caplog.text

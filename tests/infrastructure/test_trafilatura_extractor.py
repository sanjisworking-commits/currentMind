import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
import trafilatura

from app.domain.extraction import ExtractionStatus
from app.infrastructure import trafilatura_extractor as extractor_module
from app.infrastructure.trafilatura_extractor import (
    DEFAULT_MIN_CONTENT_LENGTH,
    USER_AGENT,
    TrafilaturaArticleExtractor,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "html"
ARTICLE_URL = "https://indianexpress.com/article/one"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _transport_returning(
    fixture_name: str,
    status_code: int = 200,
    content_type: str | None = "text/html; charset=utf-8",
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type is not None else {}
        return httpx.Response(status_code, headers=headers, content=_fixture_bytes(fixture_name))

    return httpx.MockTransport(handler)


def _transport_returning_bytes(
    content: bytes,
    status_code: int = 200,
    content_type: str | None = "text/html; charset=utf-8",
    extra_headers: dict[str, str] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        headers: dict[str, str] = dict(extra_headers or {})
        if content_type is not None:
            headers["content-type"] = content_type
        return httpx.Response(status_code, headers=headers, content=content)

    return httpx.MockTransport(handler)


def _transport_streaming_bytes(
    content: bytes, content_type: str | None = "text/html"
) -> httpx.MockTransport:
    """Return a response with no Content-Length header (chunked transfer)."""

    def body() -> Any:
        yield content

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type is not None else {}
        return httpx.Response(200, headers=headers, content=body())

    return httpx.MockTransport(handler)


def _transport_recording(
    fixture_name: str, calls: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=_fixture_bytes(fixture_name)
        )

    return httpx.MockTransport(handler)


def _extractor(transport: httpx.MockTransport, **kwargs: Any) -> TrafilaturaArticleExtractor:
    return TrafilaturaArticleExtractor(transport=transport, **kwargs)


def _never_called_transport() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("no HTTP request should have been made")

    return httpx.MockTransport(handler), calls


# --- URL validation: caller contract violations ------------------------------


@pytest.mark.parametrize(
    "url",
    ["", "   ", "/feed", "feed", "ftp://example.com/a", "file:///etc/passwd", "http://", "https://"],
    ids=[
        "blank",
        "whitespace-only",
        "relative-absolute-path",
        "relative-bare-word",
        "ftp-scheme",
        "file-scheme",
        "http-missing-netloc",
        "https-missing-netloc",
    ],
)
def test_rejects_invalid_url(url: str) -> None:
    transport, calls = _never_called_transport()
    extractor = _extractor(transport)

    with pytest.raises(ValueError):
        extractor.extract(url)

    assert calls == []


def test_rejects_non_string_url() -> None:
    transport, calls = _never_called_transport()
    extractor = _extractor(transport)

    with pytest.raises(ValueError):
        extractor.extract(None)  # type: ignore[arg-type]

    assert calls == []


@pytest.mark.parametrize(
    "url",
    ["http://example.com/a", "https://example.com/a"],
    ids=["http", "https"],
)
def test_accepts_valid_http_and_https_urls(url: str) -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(url)

    assert result.status == ExtractionStatus.SUCCESS


def test_strips_surrounding_whitespace_from_url() -> None:
    calls: list[httpx.Request] = []
    extractor = _extractor(_transport_recording("indian_express_article.html", calls))

    extractor.extract(f"  {ARTICLE_URL}  ")

    assert str(calls[0].url) == ARTICLE_URL


# --- Constructor validation ---------------------------------------------------


@pytest.mark.parametrize("timeout_seconds", [0, -1.0])
def test_rejects_non_positive_timeout(timeout_seconds: float) -> None:
    with pytest.raises(ValueError):
        TrafilaturaArticleExtractor(timeout_seconds=timeout_seconds)


@pytest.mark.parametrize("min_content_length", [0, -1])
def test_rejects_non_positive_min_content_length(min_content_length: int) -> None:
    with pytest.raises(ValueError):
        TrafilaturaArticleExtractor(min_content_length=min_content_length)


@pytest.mark.parametrize("max_response_bytes", [0, -1])
def test_rejects_non_positive_max_response_bytes(max_response_bytes: int) -> None:
    with pytest.raises(ValueError):
        TrafilaturaArticleExtractor(max_response_bytes=max_response_bytes)


# --- Representative extraction (real Trafilatura) -----------------------------


def test_extracts_clean_text_from_indian_express_like_fixture() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS
    assert result.error_reason is None
    assert result.text is not None
    assert "Cabinet approves new scheme for rural development" in result.text
    assert "The Union Cabinet on Tuesday approved a new scheme" in result.text


def test_extracts_clean_text_from_generic_non_indian_express_fixture() -> None:
    extractor = _extractor(_transport_returning("generic_article.html"))

    result = extractor.extract("https://dailypolicydigest.example.com/rbi-policy")

    assert result.status == ExtractionStatus.SUCCESS
    assert result.text is not None
    assert "Reserve Bank of India's latest monetary policy committee" in result.text


def test_paragraph_breaks_preserved() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.text is not None
    lines = [line for line in result.text.split("\n") if line]
    assert len(lines) >= 4
    assert any(
        line.startswith("The scheme, which will be implemented over the next five years")
        for line in lines
    )
    assert "Officials said the scheme would be funded jointly" in "\n".join(lines)


def test_navigation_text_excluded() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.text is not None
    assert "UPSC Current Affairs" not in result.text


def test_advertisement_text_excluded() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.text is not None
    assert "Subscribe now and get 50% off" not in result.text


def test_related_stories_and_footer_excluded() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.text is not None
    assert "Government announces new urban housing policy" not in result.text
    assert "Advertise With Us" not in result.text
    assert "Copyright 2026 Indian Express" not in result.text


def test_noisy_page_excludes_nav_ads_related_and_footer() -> None:
    extractor = _extractor(_transport_returning("noisy_article.html"))

    result = extractor.extract("https://indianexpress.com/article/verdict")

    assert result.status == ExtractionStatus.SUCCESS
    assert result.text is not None
    assert "The Supreme Court on Thursday delivered a significant verdict" in result.text
    assert "Sponsored: Best investment plans" not in result.text
    assert "Read our exclusive analysis with a premium subscription" not in result.text
    assert "Also Read" not in result.text
    assert "What changes under the new coastal regulation zone" not in result.text
    assert "Great article, very informative" not in result.text
    assert "About Us | Contact Us | Advertise | Careers" not in result.text


def test_whitespace_normalized() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.text is not None
    assert result.text == result.text.strip("\n")
    assert "\n\n\n" not in result.text
    for line in result.text.split("\n"):
        assert line == line.strip()


def test_malformed_html_does_not_raise() -> None:
    extractor = _extractor(_transport_returning("malformed.html"))

    result = extractor.extract("https://example.com/broken")

    assert result.status in (ExtractionStatus.SUCCESS, ExtractionStatus.INSUFFICIENT_CONTENT)


# --- Minimum-content threshold -------------------------------------------------


def test_below_threshold_short_fixture_returns_insufficient_content() -> None:
    extractor = _extractor(_transport_returning("short_article.html"))

    result = extractor.extract("https://indianexpress.com/article/short")

    assert result.status == ExtractionStatus.INSUFFICIENT_CONTENT
    assert result.text is not None
    assert len(result.text) < DEFAULT_MIN_CONTENT_LENGTH
    assert result.error_reason is not None


def test_threshold_exactly_met_is_success(monkeypatch: pytest.MonkeyPatch) -> None:
    exact_text = "x" * DEFAULT_MIN_CONTENT_LENGTH
    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: exact_text)
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS
    assert result.text == exact_text


def test_one_character_below_threshold_is_insufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    short_text = "x" * (DEFAULT_MIN_CONTENT_LENGTH - 1)
    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: short_text)
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.INSUFFICIENT_CONTENT
    assert result.text == short_text


def test_none_result_is_insufficient_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: None)
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.INSUFFICIENT_CONTENT
    assert result.text is None
    assert result.error_reason is not None


def test_empty_string_result_is_insufficient_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: "")
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.INSUFFICIENT_CONTENT
    assert result.text is None


def test_unexpected_trafilatura_exception_is_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*args: Any, **kwargs: Any) -> str | None:
        raise RuntimeError("boom")

    monkeypatch.setattr(trafilatura, "extract", boom)
    caplog.set_level(logging.ERROR, logger="app.infrastructure.trafilatura_extractor")
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNEXPECTED_ERROR
    assert result.error_reason is not None
    assert "RuntimeError" in result.error_reason
    assert "Unexpected extraction failure" in caplog.text
    assert any(record.exc_info for record in caplog.records)


def test_unexpected_cleanup_exception_is_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: "valid extracted text")

    def boom_clean_text(text: str) -> str:
        raise RuntimeError("cleanup boom")

    monkeypatch.setattr(extractor_module, "_clean_text", boom_clean_text)
    caplog.set_level(logging.ERROR, logger="app.infrastructure.trafilatura_extractor")
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNEXPECTED_ERROR
    assert result.error_reason is not None
    assert "RuntimeError" in result.error_reason
    assert "Unexpected extraction failure" in caplog.text
    assert any(record.exc_info for record in caplog.records)


# --- Network and HTTP status mapping -------------------------------------------


def test_timeout_maps_to_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    extractor = _extractor(httpx.MockTransport(handler))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.NETWORK_ERROR
    assert result.error_reason is not None


def test_connection_error_maps_to_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    extractor = _extractor(httpx.MockTransport(handler))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.NETWORK_ERROR


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503])
def test_transient_status_codes_map_to_network_error(status_code: int) -> None:
    extractor = _extractor(
        _transport_returning("indian_express_article.html", status_code=status_code)
    )

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.NETWORK_ERROR
    assert result.error_reason is not None
    assert str(status_code) in result.error_reason


@pytest.mark.parametrize("status_code", [401, 403, 404, 410])
def test_permanent_4xx_status_codes_map_to_unsupported_page(status_code: int) -> None:
    extractor = _extractor(
        _transport_returning("indian_express_article.html", status_code=status_code)
    )

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None
    assert str(status_code) in result.error_reason


def test_non_followable_redirect_without_location_is_unsupported_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> str | None:
        raise AssertionError("Trafilatura must not be invoked for a non-2xx final response")

    monkeypatch.setattr(trafilatura, "extract", fail_if_called)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, content=b"")

    extractor = _extractor(httpx.MockTransport(handler))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None
    assert "302" in result.error_reason


def test_304_not_modified_final_response_is_unsupported_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> str | None:
        raise AssertionError("Trafilatura must not be invoked for a non-2xx final response")

    monkeypatch.setattr(trafilatura, "extract", fail_if_called)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, content=b"")

    extractor = _extractor(httpx.MockTransport(handler))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None
    assert "304" in result.error_reason


# --- Redirects ------------------------------------------------------------------


def test_follows_redirect_and_extracts_from_final_url() -> None:
    calls: list[httpx.URL] = []
    final_url = "https://indianexpress.com/article/one-final"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        if str(request.url) == ARTICLE_URL:
            return httpx.Response(302, headers={"location": final_url})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=_fixture_bytes("indian_express_article.html"),
        )

    extractor = _extractor(httpx.MockTransport(handler))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS
    assert [str(url) for url in calls] == [ARTICLE_URL, final_url]


def test_final_redirected_url_is_passed_to_trafilatura(monkeypatch: pytest.MonkeyPatch) -> None:
    final_url = "https://indianexpress.com/article/one-final"
    captured_urls: list[str | None] = []

    def fake_extract(body: Any, url: str | None = None, **kwargs: Any) -> str | None:
        captured_urls.append(url)
        return "x" * DEFAULT_MIN_CONTENT_LENGTH

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == ARTICLE_URL:
            return httpx.Response(302, headers={"location": final_url})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=_fixture_bytes("indian_express_article.html"),
        )

    monkeypatch.setattr(trafilatura, "extract", fake_extract)
    extractor = _extractor(httpx.MockTransport(handler))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS
    assert captured_urls == [final_url]


def test_only_requests_article_url_once_without_redirect() -> None:
    calls: list[httpx.Request] = []
    extractor = _extractor(_transport_recording("indian_express_article.html", calls))

    extractor.extract(ARTICLE_URL)

    assert len(calls) == 1
    assert str(calls[0].url) == ARTICLE_URL


def test_no_rss_feed_request_is_ever_made() -> None:
    calls: list[httpx.Request] = []
    extractor = _extractor(_transport_recording("indian_express_article.html", calls))

    extractor.extract(ARTICLE_URL)

    assert all(str(call.url) == ARTICLE_URL for call in calls)


# --- Content-type handling -------------------------------------------------------


@pytest.mark.parametrize(
    "content_type", ["text/html", "text/html; charset=utf-8", "application/xhtml+xml"]
)
def test_accepts_supported_content_types(content_type: str) -> None:
    extractor = _extractor(
        _transport_returning("indian_express_article.html", content_type=content_type)
    )

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("application/pdf", b"%PDF-1.4 not a real pdf but has the right header"),
        ("image/png", b"\x89PNG\r\n\x1a\nrest of fake png"),
        ("application/json", b'{"not": "an article"}'),
        ("text/plain", b"Just plain text, not HTML."),
        ("application/octet-stream", b"\x00\x01\x02binary junk"),
    ],
    ids=["pdf", "image", "json", "text-plain", "octet-stream"],
)
def test_rejects_unsupported_content_types_before_trafilatura(
    monkeypatch: pytest.MonkeyPatch, content_type: str, body: bytes
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> str | None:
        raise AssertionError("Trafilatura must not be invoked for unsupported content types")

    monkeypatch.setattr(trafilatura, "extract", fail_if_called)
    extractor = _extractor(_transport_returning_bytes(body, content_type=content_type))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None
    assert content_type in result.error_reason


def test_missing_content_type_with_html_body_is_processed() -> None:
    extractor = _extractor(_transport_returning("indian_express_article.html", content_type=None))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS


def test_missing_content_type_with_pdf_signature_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args: Any, **kwargs: Any) -> str | None:
        raise AssertionError("Trafilatura must not be invoked for binary signatures")

    monkeypatch.setattr(trafilatura, "extract", fail_if_called)
    body = b"%PDF-1.4\n%more binary pdf content here"
    extractor = _extractor(_transport_returning_bytes(body, content_type=None))

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE


# --- Response-size enforcement ---------------------------------------------------


def test_declared_oversized_content_length_is_rejected() -> None:
    body = _fixture_bytes("short_article.html")
    extractor = _extractor(
        _transport_returning_bytes(
            body, extra_headers={"content-length": "50000000"}
        ),
        max_response_bytes=1000,
    )

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None
    assert "Declared response size" in result.error_reason


def test_missing_content_length_streamed_content_exceeding_limit_is_rejected() -> None:
    body = b"<html><body>" + (b"a" * 5000) + b"</body></html>"
    extractor = _extractor(_transport_streaming_bytes(body), max_response_bytes=1000)

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None
    assert "exceeds limit" in result.error_reason


def test_response_exactly_at_size_limit_is_not_rejected_for_size() -> None:
    body = _fixture_bytes("indian_express_article.html")
    extractor = _extractor(
        _transport_returning_bytes(body), max_response_bytes=len(body)
    )

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.SUCCESS
    assert result.error_reason is None


def test_response_one_byte_above_size_limit_is_rejected() -> None:
    body = _fixture_bytes("indian_express_article.html")
    extractor = _extractor(
        _transport_returning_bytes(body), max_response_bytes=len(body) - 1
    )

    result = extractor.extract(ARTICLE_URL)

    assert result.status == ExtractionStatus.UNSUPPORTED_PAGE
    assert result.error_reason is not None


# --- Request behaviour: User-Agent -----------------------------------------------


def test_sends_expected_user_agent() -> None:
    calls: list[httpx.Request] = []
    extractor = _extractor(_transport_recording("indian_express_article.html", calls))

    extractor.extract(ARTICLE_URL)

    assert calls[0].headers["user-agent"] == USER_AGENT


# --- Logging ----------------------------------------------------------------------


def test_logs_lifecycle_events(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.infrastructure.trafilatura_extractor")
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    extractor.extract(ARTICLE_URL)

    assert "Extraction started" in caplog.text
    assert "Page fetch completed" in caplog.text
    assert "Trafilatura extraction completed" in caplog.text


def test_logs_insufficient_content(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.infrastructure.trafilatura_extractor")
    extractor = _extractor(_transport_returning("short_article.html"))

    extractor.extract(ARTICLE_URL)

    assert "Insufficient extracted content" in caplog.text


def test_logs_do_not_include_full_article_text(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.infrastructure.trafilatura_extractor")
    extractor = _extractor(_transport_returning("indian_express_article.html"))

    result = extractor.extract(ARTICLE_URL)

    assert result.text is not None
    assert result.text not in caplog.text

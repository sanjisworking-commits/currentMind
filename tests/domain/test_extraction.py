from datetime import UTC

import pytest
from pydantic import ValidationError

from app.domain.extraction import ExtractedArticle, ExtractionStatus


def test_valid_successful_extraction() -> None:
    article = ExtractedArticle(
        url="https://indianexpress.com/article",
        status=ExtractionStatus.SUCCESS,
        text="Clean article body.",
    )
    assert article.status == ExtractionStatus.SUCCESS
    assert article.error_reason is None
    assert article.extracted_at.tzinfo == UTC


def test_valid_failed_extraction_requires_error_reason() -> None:
    article = ExtractedArticle(
        url="https://indianexpress.com/article",
        status=ExtractionStatus.NETWORK_ERROR,
        error_reason="Connection timed out.",
    )
    assert article.text is None


def test_insufficient_content_may_preserve_partial_text() -> None:
    article = ExtractedArticle(
        url="https://indianexpress.com/article",
        status=ExtractionStatus.INSUFFICIENT_CONTENT,
        text="Too short.",
        error_reason="Extracted text below minimum length.",
    )
    assert article.text == "Too short."


def test_other_failure_statuses_allow_none_text() -> None:
    article = ExtractedArticle(
        url="https://indianexpress.com/article",
        status=ExtractionStatus.UNSUPPORTED_PAGE,
        error_reason="Page format not supported.",
    )
    assert article.text is None


def test_success_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(url="https://example.com/a", status=ExtractionStatus.SUCCESS)


def test_success_rejects_whitespace_only_text() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(
            url="https://example.com/a",
            status=ExtractionStatus.SUCCESS,
            text="   ",
        )


def test_success_rejects_error_reason() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(
            url="https://example.com/a",
            status=ExtractionStatus.SUCCESS,
            text="Body",
            error_reason="Should not be here",
        )


def test_failure_requires_error_reason() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(url="https://example.com/a", status=ExtractionStatus.NETWORK_ERROR)


def test_failure_rejects_whitespace_only_error_reason() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(
            url="https://example.com/a",
            status=ExtractionStatus.NETWORK_ERROR,
            error_reason="   ",
        )


def test_rejects_non_http_url() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(
            url="ftp://example.com/a",
            status=ExtractionStatus.NETWORK_ERROR,
            error_reason="n/a",
        )


def test_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ExtractedArticle(
            url="https://example.com/a",
            status="bogus",  # type: ignore[arg-type]
            error_reason="x",
        )


def test_assignment_rejects_failure_status_without_error_reason() -> None:
    article = ExtractedArticle(
        url="https://example.com/a",
        status=ExtractionStatus.SUCCESS,
        text="Body",
    )
    with pytest.raises(ValidationError):
        article.status = ExtractionStatus.NETWORK_ERROR
    assert article.status == ExtractionStatus.SUCCESS


def test_assignment_rejects_clearing_text_on_success() -> None:
    article = ExtractedArticle(
        url="https://example.com/a",
        status=ExtractionStatus.SUCCESS,
        text="Body",
    )
    with pytest.raises(ValidationError):
        article.text = None
    assert article.text == "Body"


def test_assignment_rejects_adding_error_reason_to_success() -> None:
    article = ExtractedArticle(
        url="https://example.com/a",
        status=ExtractionStatus.SUCCESS,
        text="Body",
    )
    with pytest.raises(ValidationError):
        article.error_reason = "Should not be here"
    assert article.error_reason is None


def test_assignment_rejects_removing_error_reason_from_failure() -> None:
    article = ExtractedArticle(
        url="https://example.com/a",
        status=ExtractionStatus.NETWORK_ERROR,
        error_reason="Connection timed out.",
    )
    with pytest.raises(ValidationError):
        article.error_reason = None
    assert article.error_reason == "Connection timed out."

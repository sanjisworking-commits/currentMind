from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.article import Article, ArticleCandidate
from app.domain.enums import ProcessingStatus


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def test_valid_article_candidate() -> None:
    candidate = ArticleCandidate(
        source="indian_express",
        external_id="123",
        title="A Title",
        url="https://indianexpress.com/article",
        author="Jane Doe",
        published_at=_utc(2026, 7, 1),
        categories=["polity"],
    )
    assert candidate.source == "indian_express"
    assert candidate.published_at == _utc(2026, 7, 1)


def test_article_candidate_default_categories_are_independent() -> None:
    first = ArticleCandidate(source="s", title="t", url="https://example.com/a")
    second = ArticleCandidate(source="s", title="t", url="https://example.com/b")
    first.categories.append("x")
    assert second.categories == []


@pytest.mark.parametrize("url", ["ftp://example.com/a", "example.com/a", ""])
def test_article_candidate_rejects_non_http_url(url: str) -> None:
    with pytest.raises(ValidationError):
        ArticleCandidate(source="s", title="t", url=url)


def test_article_candidate_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        ArticleCandidate(source="s", title="   ", url="https://example.com/a")


def test_article_candidate_rejects_naive_published_at() -> None:
    with pytest.raises(ValidationError):
        ArticleCandidate(
            source="s",
            title="t",
            url="https://example.com/a",
            published_at=datetime(2026, 7, 1),
        )


def test_article_candidate_normalizes_non_utc_published_at() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    candidate = ArticleCandidate(
        source="s",
        title="t",
        url="https://example.com/a",
        published_at=datetime(2026, 7, 1, 12, 0, tzinfo=ist),
    )
    assert candidate.published_at is not None
    assert candidate.published_at.tzinfo == UTC


def _article_kwargs() -> dict[str, Any]:
    return {
        "source": "indian_express",
        "title": "A Title",
        "url": "https://indianexpress.com/article",
        "processing_status": ProcessingStatus.DISCOVERED,
    }


def test_valid_article_has_generated_id_and_utc_timestamps() -> None:
    article = Article(**_article_kwargs())
    assert article.id is not None
    assert article.created_at.tzinfo == UTC
    assert article.updated_at.tzinfo == UTC


def test_article_ids_are_unique_by_default() -> None:
    first = Article(**_article_kwargs())
    second = Article(**_article_kwargs())
    assert first.id != second.id


def test_article_rejects_unknown_processing_status() -> None:
    kwargs = _article_kwargs()
    kwargs["processing_status"] = "bogus"
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_rejects_updated_before_created() -> None:
    kwargs = _article_kwargs()
    kwargs["created_at"] = _utc(2026, 7, 2)
    kwargs["updated_at"] = _utc(2026, 7, 1)
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_allows_updated_equal_created() -> None:
    same = _utc(2026, 7, 1)
    kwargs = _article_kwargs()
    kwargs["created_at"] = same
    kwargs["updated_at"] = same
    article = Article(**kwargs)
    assert article.updated_at == article.created_at


def test_article_rejects_naive_timestamp() -> None:
    kwargs = _article_kwargs()
    kwargs["created_at"] = datetime(2026, 7, 1)
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_rejects_invalid_url() -> None:
    kwargs = _article_kwargs()
    kwargs["url"] = "not-a-url"
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_rejects_empty_source() -> None:
    kwargs = _article_kwargs()
    kwargs["source"] = "  "
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_rejects_unknown_field() -> None:
    kwargs = _article_kwargs()
    kwargs["nonexistent_field"] = "x"
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_candidate_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ArticleCandidate(
            source="s",
            title="t",
            url="https://example.com/a",
            bogus="x",  # type: ignore[call-arg]
        )


def test_article_assignment_rejects_invalid_processing_status() -> None:
    article = Article(**_article_kwargs())
    original_status = article.processing_status
    with pytest.raises(ValidationError):
        article.processing_status = "bogus"  # type: ignore[assignment]
    assert article.processing_status == original_status


def test_article_assignment_rejects_naive_datetime() -> None:
    article = Article(**_article_kwargs())
    original_updated_at = article.updated_at
    with pytest.raises(ValidationError):
        article.updated_at = datetime(2026, 7, 1)
    assert article.updated_at == original_updated_at


def test_article_assignment_rejects_updated_before_created() -> None:
    kwargs = _article_kwargs()
    kwargs["created_at"] = _utc(2026, 7, 2)
    kwargs["updated_at"] = _utc(2026, 7, 2)
    article = Article(**kwargs)
    original_updated_at = article.updated_at
    with pytest.raises(ValidationError):
        article.updated_at = _utc(2026, 7, 1)
    assert article.updated_at == original_updated_at


def test_article_assignment_rejects_created_after_updated() -> None:
    kwargs = _article_kwargs()
    kwargs["created_at"] = _utc(2026, 7, 1)
    kwargs["updated_at"] = _utc(2026, 7, 2)
    article = Article(**kwargs)
    original_created_at = article.created_at
    with pytest.raises(ValidationError):
        article.created_at = _utc(2026, 7, 3)
    assert article.created_at == original_created_at


@pytest.mark.parametrize(
    "categories", [["polity", ""], ["polity", "   "]], ids=["empty", "whitespace"]
)
def test_article_candidate_rejects_blank_category(categories: list[str]) -> None:
    with pytest.raises(ValidationError):
        ArticleCandidate(source="s", title="t", url="https://example.com/a", categories=categories)


def test_article_candidate_rejects_duplicate_categories() -> None:
    with pytest.raises(ValidationError):
        ArticleCandidate(
            source="s",
            title="t",
            url="https://example.com/a",
            categories=["polity", "Polity ", " polity"],
        )


def test_article_candidate_strips_category_whitespace() -> None:
    candidate = ArticleCandidate(
        source="s",
        title="t",
        url="https://example.com/a",
        categories=[" polity ", "economy"],
    )
    assert candidate.categories == ["polity", "economy"]


def test_article_rejects_blank_category() -> None:
    kwargs = _article_kwargs()
    kwargs["categories"] = ["polity", "  "]
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_article_rejects_duplicate_categories() -> None:
    kwargs = _article_kwargs()
    kwargs["categories"] = ["polity", "polity"]
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_failed_article_with_reason_is_valid() -> None:
    kwargs = _article_kwargs()
    kwargs["processing_status"] = ProcessingStatus.FAILED
    kwargs["failure_reason"] = "Network timeout while extracting content."
    article = Article(**kwargs)
    assert article.failure_reason == "Network timeout while extracting content."


def test_failed_article_without_reason_rejected() -> None:
    kwargs = _article_kwargs()
    kwargs["processing_status"] = ProcessingStatus.FAILED
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_non_failed_article_with_reason_rejected() -> None:
    kwargs = _article_kwargs()
    kwargs["processing_status"] = ProcessingStatus.DISCOVERED
    kwargs["failure_reason"] = "Should not be here"
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_failed_article_rejects_whitespace_only_reason() -> None:
    kwargs = _article_kwargs()
    kwargs["processing_status"] = ProcessingStatus.FAILED
    kwargs["failure_reason"] = "   "
    with pytest.raises(ValidationError):
        Article(**kwargs)


def test_assignment_to_failed_without_reason_rejected_and_preserves_state() -> None:
    article = Article(**_article_kwargs())
    original_status = article.processing_status
    with pytest.raises(ValidationError):
        article.processing_status = ProcessingStatus.FAILED
    assert article.processing_status == original_status
    assert article.failure_reason is None


def test_assignment_of_reason_without_failed_status_rejected_and_preserves_state() -> None:
    article = Article(**_article_kwargs())
    with pytest.raises(ValidationError):
        article.failure_reason = "Some reason"
    assert article.failure_reason is None


def test_clearing_failure_state_and_moving_to_non_failed_status() -> None:
    kwargs = _article_kwargs()
    kwargs["processing_status"] = ProcessingStatus.FAILED
    kwargs["failure_reason"] = "Extraction failed."
    failed_article = Article(**kwargs)

    recovered_kwargs = failed_article.model_dump()
    recovered_kwargs["processing_status"] = ProcessingStatus.DISCOVERED
    recovered_kwargs["failure_reason"] = None
    recovered = Article(**recovered_kwargs)

    assert recovered.processing_status == ProcessingStatus.DISCOVERED
    assert recovered.failure_reason is None

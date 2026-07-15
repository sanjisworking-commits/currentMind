"""Factory helpers for building valid domain objects in persistence tests."""

from datetime import datetime
from uuid import UUID, uuid4

from app.domain.article import Article
from app.domain.enums import ProcessingStatus
from app.domain.learning_note import LearningNote


def make_article(
    *,
    source: str = "indian_express",
    external_id: str | None = "ext-1",
    title: str = "A Title",
    url: str = "https://indianexpress.com/article",
    author: str | None = "Jane Doe",
    published_at: datetime | None = None,
    categories: list[str] | None = None,
    raw_text: str | None = None,
    processing_status: ProcessingStatus = ProcessingStatus.DISCOVERED,
    failure_reason: str | None = None,
) -> Article:
    """Build a valid `Article` with sensible defaults, overridable per test."""
    return Article(
        source=source,
        external_id=external_id,
        title=title,
        url=url,
        author=author,
        published_at=published_at,
        categories=categories if categories is not None else ["polity"],
        raw_text=raw_text,
        processing_status=processing_status,
        failure_reason=failure_reason,
    )


def make_learning_note(
    *,
    article_id: UUID | None = None,
    summary: str = "Summary text.",
    why_it_matters: str = "Why it matters.",
    revision_note: str = "Revision note.",
    model_name: str = "gpt-test",
    prompt_version: str = "v1",
) -> LearningNote:
    """Build a valid `LearningNote` with sensible defaults, overridable per test."""
    return LearningNote(
        article_id=article_id if article_id is not None else uuid4(),
        summary=summary,
        why_it_matters=why_it_matters,
        revision_note=revision_note,
        model_name=model_name,
        prompt_version=prompt_version,
    )

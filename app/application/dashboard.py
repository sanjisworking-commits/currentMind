"""Read-only application query boundary for the dashboard.

`DashboardQueryService` reads persisted Articles and Learning Notes through the
existing repository ports and assembles small, immutable read models
(`ArticleCard`, `ArticleDetail`) shaped for the dashboard's two pages. It
performs no writes and never touches the processing pipeline, the generator,
the extractor, or the article source.

This module depends only on application ports and domain types - never on
FastAPI, Starlette, Jinja2, SQLAlchemy, Alembic, or any external SDK - so the
presentation layer can render it without reaching into infrastructure, and it
can be tested with plain fakes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.repositories import ArticleRepository, LearningNoteRepository
from app.domain.article import Article
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import LearningNote

# Bounded number of most-recent Articles shown on the home page. Kept small
# deliberately: the home page issues one list query plus one Learning Note
# lookup per Article (1 + N, N <= HOME_ARTICLE_LIMIT), which is well within
# budget for a local single-user SQLite dashboard.
HOME_ARTICLE_LIMIT = 30

# Maximum number of topic tags shown on a home-page card.
MAX_TOPIC_TAGS = 5

# Maximum length of the non-persisted summary excerpt shown on a card. The
# full summary always remains available on the detail page.
SUMMARY_EXCERPT_MAX_CHARS = 320

_ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class ArticleCard:
    """Immutable home-page card. Exposes only what the home template needs.

    Deliberately excludes `raw_text`, the full `Article`/`LearningNote`,
    provider/prompt metadata, and any database object.
    """

    article_id: UUID
    title: str
    source: str
    published_at: datetime | None
    processing_status: ProcessingStatus
    has_learning_note: bool
    summary_excerpt: str | None
    gs_papers: tuple[GSPaper, ...]
    topic_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArticleDetail:
    """Immutable detail-page read model of display-safe Article fields.

    Carries only the Article fields that are safe to display - notably never
    `raw_text` - plus the structured `LearningNote`, whose content is the
    subject of the detail page. The template never receives a full `Article`
    or any database row.
    """

    article_id: UUID
    title: str
    source: str
    url: str
    author: str | None
    published_at: datetime | None
    categories: tuple[str, ...]
    processing_status: ProcessingStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    learning_note: LearningNote | None


def summarize_for_card(summary: str) -> str:
    """Build a deterministic, non-persisted card excerpt from a full summary.

    Collapses internal whitespace for card display and, when the normalized
    text exceeds `SUMMARY_EXCERPT_MAX_CHARS`, truncates at a word boundary
    where possible and appends a single Unicode ellipsis. Operates on Unicode
    code points (never bytes), so the result is always valid text. The
    persisted Learning Note is never modified, and the full summary remains
    available on the detail page.
    """
    normalized = " ".join(summary.split())
    if len(normalized) <= SUMMARY_EXCERPT_MAX_CHARS:
        return normalized
    window = normalized[:SUMMARY_EXCERPT_MAX_CHARS]
    boundary = window.rfind(" ")
    truncated = window[:boundary] if boundary > 0 else window
    return truncated.rstrip() + _ELLIPSIS


def select_topic_tags(article: Article, note: LearningNote | None) -> tuple[str, ...]:
    """Select up to `MAX_TOPIC_TAGS` topic tags from a single source.

    Uses one source only, in deterministic first-non-empty priority: the
    Learning Note's `syllabus_topics`, then its `subjects`, then the Article's
    `categories`. Sources are never merged, and original order is preserved.
    """
    source: list[str]
    if note is not None and note.syllabus_topics:
        source = note.syllabus_topics
    elif note is not None and note.subjects:
        source = note.subjects
    elif article.categories:
        source = article.categories
    else:
        source = []
    return tuple(source[:MAX_TOPIC_TAGS])


class DashboardQuery(Protocol):
    """Read-only query surface the dashboard presentation layer depends on."""

    def list_recent_articles(self, *, limit: int = HOME_ARTICLE_LIMIT) -> tuple[ArticleCard, ...]:
        """Return the most recent Articles as immutable home-page cards."""
        ...

    def get_article_detail(self, article_id: UUID) -> ArticleDetail | None:
        """Return the detail read model for `article_id`, or None if absent."""
        ...


class DashboardQueryService:
    """Assembles dashboard read models from the repository ports.

    Structurally implements `DashboardQuery`. Read-only: it calls only
    `ArticleRepository.list_recent`/`get_with_learning_note` and
    `LearningNoteRepository.get_by_article_id`, never a write method, and
    never the processing pipeline.
    """

    def __init__(
        self,
        *,
        article_repository: ArticleRepository,
        learning_note_repository: LearningNoteRepository,
    ) -> None:
        self._articles = article_repository
        self._notes = learning_note_repository

    def list_recent_articles(self, *, limit: int = HOME_ARTICLE_LIMIT) -> tuple[ArticleCard, ...]:
        """Return up to `limit` recent Articles as cards.

        Issues exactly one `list_recent()` query, then one
        `get_by_article_id()` per returned Article - deliberately not
        `get_with_learning_note()`, which would re-read each Article.
        """
        articles = self._articles.list_recent(limit=limit)
        return tuple(
            self._to_card(article, self._notes.get_by_article_id(article.id))
            for article in articles
        )

    def get_article_detail(self, article_id: UUID) -> ArticleDetail | None:
        """Return the detail read model, or None when the Article does not exist."""
        pair = self._articles.get_with_learning_note(article_id)
        if pair is None:
            return None
        return self._to_detail(pair.article, pair.learning_note)

    @staticmethod
    def _to_card(article: Article, note: LearningNote | None) -> ArticleCard:
        return ArticleCard(
            article_id=article.id,
            title=article.title,
            source=article.source,
            published_at=article.published_at,
            processing_status=article.processing_status,
            has_learning_note=note is not None,
            summary_excerpt=summarize_for_card(note.summary) if note is not None else None,
            gs_papers=tuple(note.gs_papers) if note is not None else (),
            topic_tags=select_topic_tags(article, note),
        )

    @staticmethod
    def _to_detail(article: Article, note: LearningNote | None) -> ArticleDetail:
        return ArticleDetail(
            article_id=article.id,
            title=article.title,
            source=article.source,
            url=article.url,
            author=article.author,
            published_at=article.published_at,
            categories=tuple(article.categories),
            processing_status=article.processing_status,
            failure_reason=article.failure_reason,
            created_at=article.created_at,
            updated_at=article.updated_at,
            learning_note=note,
        )

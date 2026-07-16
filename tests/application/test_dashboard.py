"""Tests for `app.application.dashboard`: the read-only query service.

Uses small counting fakes that implement only the repository read methods the
service is allowed to call, and raise if any write method is invoked - so the
tests also prove the dashboard never writes.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.dashboard import (
    HOME_ARTICLE_LIMIT,
    MAX_TOPIC_TAGS,
    SUMMARY_EXCERPT_MAX_CHARS,
    ArticleCard,
    ArticleDetail,
    DashboardQueryService,
    select_topic_tags,
    summarize_for_card,
)
from app.application.repositories import ArticleWithLearningNote, RepositoryError
from app.domain.article import Article
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import LearningNote, MainsQuestion, PrelimsQuestion


class CountingArticleRepository:
    """Read-only article repository fake that records call counts."""

    def __init__(
        self,
        articles: list[Article] | None = None,
        *,
        list_error: Exception | None = None,
        detail_error: Exception | None = None,
    ) -> None:
        self._articles = {a.id: a for a in (articles or [])}
        self._order = [a.id for a in (articles or [])]
        self._notes: dict[UUID, LearningNote] = {}
        self.list_recent_calls = 0
        self.list_recent_limits: list[int] = []
        self.get_with_learning_note_calls = 0
        self._list_error = list_error
        self._detail_error = detail_error

    def link_note(self, note: LearningNote) -> None:
        self._notes[note.article_id] = note

    def list_recent(self, limit: int = 20) -> list[Article]:
        self.list_recent_calls += 1
        self.list_recent_limits.append(limit)
        if self._list_error is not None:
            raise self._list_error
        return [self._articles[i] for i in self._order][:limit]

    def get_with_learning_note(self, article_id: UUID) -> ArticleWithLearningNote | None:
        self.get_with_learning_note_calls += 1
        if self._detail_error is not None:
            raise self._detail_error
        article = self._articles.get(article_id)
        if article is None:
            return None
        return ArticleWithLearningNote(
            article=article, learning_note=self._notes.get(article_id)
        )

    # Write methods must never be called by the dashboard.
    def add(self, article: Article) -> None:  # pragma: no cover - guard
        raise AssertionError("dashboard must not call add()")

    def update(self, article: Article) -> None:  # pragma: no cover - guard
        raise AssertionError("dashboard must not call update()")


class CountingNoteRepository:
    """Read-only learning-note repository fake that records call counts."""

    def __init__(self) -> None:
        self._notes: dict[UUID, LearningNote] = {}
        self.get_by_article_id_calls: list[UUID] = []

    def seed(self, note: LearningNote) -> None:
        self._notes[note.article_id] = note

    def get_by_article_id(self, article_id: UUID) -> LearningNote | None:
        self.get_by_article_id_calls.append(article_id)
        return self._notes.get(article_id)

    def add(self, note: LearningNote) -> None:  # pragma: no cover - guard
        raise AssertionError("dashboard must not call add()")


def _article(
    *,
    title: str = "A Title",
    status: ProcessingStatus = ProcessingStatus.ANALYZED,
    categories: list[str] | None = None,
    raw_text: str | None = "SENSITIVE-RAW-TEXT",
    created_at: datetime | None = None,
) -> Article:
    return Article(
        source="indian_express",
        external_id=None,
        title=title,
        url="https://indianexpress.com/upsc/article",
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=categories if categories is not None else ["polity"],
        raw_text=raw_text,
        processing_status=status,
        created_at=created_at or datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=created_at or datetime(2026, 7, 1, tzinfo=UTC),
    )


def _note(
    article_id: UUID,
    *,
    summary: str = "Full summary text.",
    subjects: list[str] | None = None,
    syllabus_topics: list[str] | None = None,
) -> LearningNote:
    return LearningNote(
        article_id=article_id,
        summary=summary,
        why_it_matters="Why.",
        gs_papers=[GSPaper.GS2],
        subjects=subjects if subjects is not None else ["polity"],
        syllabus_topics=syllabus_topics if syllabus_topics is not None else ["governance"],
        revision_note="Revise.",
        keywords=["fed"],
        model_name="gpt-test",
        prompt_version="v1",
    )


def _service(
    articles: CountingArticleRepository, notes: CountingNoteRepository
) -> DashboardQueryService:
    return DashboardQueryService(
        article_repository=articles,  # type: ignore[arg-type]
        learning_note_repository=notes,
    )


# --- summary excerpt ----------------------------------------------------------


def test_short_summary_is_returned_normalized_unchanged() -> None:
    assert summarize_for_card("A  short   summary.") == "A short summary."


def test_long_summary_is_truncated_at_word_boundary_with_ellipsis() -> None:
    long = "word " * 200
    excerpt = summarize_for_card(long)
    assert len(excerpt) <= SUMMARY_EXCERPT_MAX_CHARS + 1  # + ellipsis
    assert excerpt.endswith("…")
    assert "  " not in excerpt
    assert not excerpt[:-1].endswith(" ")


def test_summary_excerpt_is_valid_unicode_on_multibyte_content() -> None:
    long = "नमस्ते दुनिया " * 100
    excerpt = summarize_for_card(long)
    # Round-trips through UTF-8 without error -> valid Unicode, no byte slicing.
    assert excerpt.encode("utf-8").decode("utf-8") == excerpt
    assert excerpt.endswith("…")


def test_summarize_does_not_mutate_source() -> None:
    original = "word " * 200
    copy = str(original)
    summarize_for_card(original)
    assert original == copy


# --- topic-tag selection ------------------------------------------------------


def test_topic_tags_prefer_syllabus_topics() -> None:
    article = _article(categories=["cat-a"])
    note = _note(article.id, subjects=["subj-a"], syllabus_topics=["syl-a", "syl-b"])
    assert select_topic_tags(article, note) == ("syl-a", "syl-b")


def test_topic_tags_fall_back_to_subjects_then_categories() -> None:
    article = _article(categories=["cat-a"])
    note_no_syllabus = _note(article.id, subjects=["subj-a"], syllabus_topics=[])
    assert select_topic_tags(article, note_no_syllabus) == ("subj-a",)
    note_empty = _note(article.id, subjects=[], syllabus_topics=[])
    assert select_topic_tags(article, note_empty) == ("cat-a",)
    assert select_topic_tags(article, None) == ("cat-a",)


def test_topic_tags_are_capped_and_ordered() -> None:
    article = _article()
    topics = [f"t{i}" for i in range(10)]
    note = _note(article.id, syllabus_topics=topics)
    tags = select_topic_tags(article, note)
    assert tags == tuple(topics[:MAX_TOPIC_TAGS])
    assert len(tags) == MAX_TOPIC_TAGS


# --- list_recent_articles -----------------------------------------------------


def test_list_recent_defaults_to_home_limit() -> None:
    articles = CountingArticleRepository([_article()])
    notes = CountingNoteRepository()
    _service(articles, notes).list_recent_articles()
    assert articles.list_recent_limits == [HOME_ARTICLE_LIMIT]
    assert HOME_ARTICLE_LIMIT == 30


def test_list_recent_honors_caller_limit() -> None:
    articles = CountingArticleRepository([_article()])
    notes = CountingNoteRepository()
    _service(articles, notes).list_recent_articles(limit=5)
    assert articles.list_recent_limits == [5]


def test_empty_result_returns_empty_tuple() -> None:
    cards = _service(CountingArticleRepository([]), CountingNoteRepository()).list_recent_articles()
    assert cards == ()


def test_one_list_query_and_one_note_lookup_per_article_no_re_read() -> None:
    arts = [_article(title=f"T{i}") for i in range(3)]
    articles = CountingArticleRepository(arts)
    notes = CountingNoteRepository()
    for a in arts:
        notes.seed(_note(a.id))

    _service(articles, notes).list_recent_articles()

    assert articles.list_recent_calls == 1
    assert len(notes.get_by_article_id_calls) == 3
    assert notes.get_by_article_id_calls == [a.id for a in arts]
    # No per-card Article re-read via get_with_learning_note.
    assert articles.get_with_learning_note_calls == 0


def test_note_lookups_bounded_by_thirty() -> None:
    arts = [_article(title=f"T{i}") for i in range(HOME_ARTICLE_LIMIT)]
    articles = CountingArticleRepository(arts)
    notes = CountingNoteRepository()
    _service(articles, notes).list_recent_articles()
    assert len(notes.get_by_article_id_calls) <= HOME_ARTICLE_LIMIT


def test_analyzed_card_carries_summary_gs_and_tags() -> None:
    article = _article(status=ProcessingStatus.ANALYZED)
    articles = CountingArticleRepository([article])
    notes = CountingNoteRepository()
    notes.seed(_note(article.id, syllabus_topics=["governance", "polity"]))

    (card,) = _service(articles, notes).list_recent_articles()

    assert isinstance(card, ArticleCard)
    assert card.has_learning_note is True
    assert card.summary_excerpt == "Full summary text."
    assert card.gs_papers == (GSPaper.GS2,)
    assert card.topic_tags == ("governance", "polity")


def test_incomplete_card_has_no_note_no_summary_no_gs() -> None:
    article = _article(status=ProcessingStatus.DISCOVERED, categories=["polity"])
    articles = CountingArticleRepository([article])
    notes = CountingNoteRepository()

    (card,) = _service(articles, notes).list_recent_articles()

    assert card.has_learning_note is False
    assert card.summary_excerpt is None
    assert card.gs_papers == ()
    assert card.topic_tags == ("polity",)  # falls back to categories


def test_recent_ordering_is_preserved_from_repository() -> None:
    arts = [_article(title=f"T{i}") for i in range(3)]
    articles = CountingArticleRepository(arts)
    notes = CountingNoteRepository()
    cards = _service(articles, notes).list_recent_articles()
    assert [c.title for c in cards] == ["T0", "T1", "T2"]


def test_list_result_is_immutable_tuple() -> None:
    articles = CountingArticleRepository([_article()])
    cards = _service(articles, CountingNoteRepository()).list_recent_articles()
    assert isinstance(cards, tuple)


# --- get_article_detail -------------------------------------------------------


def test_detail_found_with_note() -> None:
    article = _article()
    articles = CountingArticleRepository([article])
    notes = CountingNoteRepository()
    note = _note(article.id)
    articles.link_note(note)

    detail = _service(articles, notes).get_article_detail(article.id)

    assert isinstance(detail, ArticleDetail)
    assert detail.article_id == article.id
    assert detail.learning_note is not None
    assert detail.learning_note.summary == "Full summary text."


def test_detail_found_without_note() -> None:
    article = _article(status=ProcessingStatus.EXTRACTED)
    articles = CountingArticleRepository([article])
    detail = _service(articles, CountingNoteRepository()).get_article_detail(article.id)
    assert detail is not None
    assert detail.learning_note is None
    assert detail.processing_status is ProcessingStatus.EXTRACTED


def test_detail_missing_returns_none() -> None:
    detail = _service(
        CountingArticleRepository([]), CountingNoteRepository()
    ).get_article_detail(uuid4())
    assert detail is None


def test_detail_read_model_has_no_raw_text_attribute() -> None:
    article = _article(raw_text="SENSITIVE-RAW-TEXT")
    articles = CountingArticleRepository([article])
    detail = _service(articles, CountingNoteRepository()).get_article_detail(article.id)
    assert detail is not None
    assert not hasattr(detail, "raw_text")


def test_card_read_model_has_no_raw_text_attribute() -> None:
    article = _article(raw_text="SENSITIVE-RAW-TEXT")
    (card,) = _service(
        CountingArticleRepository([article]), CountingNoteRepository()
    ).list_recent_articles()
    assert not hasattr(card, "raw_text")


# --- error propagation --------------------------------------------------------


def test_list_repository_error_propagates() -> None:
    articles = CountingArticleRepository([], list_error=RepositoryError("db down"))
    with pytest.raises(RepositoryError):
        _service(articles, CountingNoteRepository()).list_recent_articles()


def test_detail_repository_error_propagates() -> None:
    articles = CountingArticleRepository([], detail_error=RepositoryError("db down"))
    with pytest.raises(RepositoryError):
        _service(articles, CountingNoteRepository()).get_article_detail(uuid4())


def test_prelims_and_mains_survive_round_trip_into_detail() -> None:
    article = _article()
    articles = CountingArticleRepository([article])
    note = LearningNote(
        article_id=article.id,
        summary="s",
        why_it_matters="w",
        revision_note="r",
        prelims_questions=[
            PrelimsQuestion(
                question="Q?", options=["A", "B", "C", "D"], correct_option=2, explanation="E"
            )
        ],
        mains_questions=[MainsQuestion(question="Discuss.")],
        model_name="m",
        prompt_version="v1",
    )
    articles.link_note(note)
    detail = _service(articles, CountingNoteRepository()).get_article_detail(article.id)
    assert detail is not None and detail.learning_note is not None
    assert detail.learning_note.prelims_questions[0].correct_option == 2

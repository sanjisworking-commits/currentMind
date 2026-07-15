"""End-to-end pipeline tests across real SQLite persistence.

"End-to-end" here means: fixture `ArticleCandidate` → real
`ProcessNewsFeedService` → fake extractor → real SQLite `ArticleRepository`
→ fake `LearningNoteGenerator` → real SQLite `LearningNoteRepository` →
persisted-state assertions. Only the external network/LLM providers are
replaced; every session, transaction, mapper, and Alembic-migrated schema is
real, applied to an isolated temporary database (see `conftest.py`). No live
RSS, article page, or OpenAI access ever occurs.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.application.processing import (
    PipelineStage,
    ProcessNewsFeedService,
    reconstruct_article,
)
from app.application.repositories import (
    ArticleRepository,
    LearningNoteRepository,
    RepositoryError,
)
from app.domain.article import Article, ArticleCandidate
from app.domain.enums import ProcessingStatus
from app.domain.extraction import ExtractedArticle, ExtractionStatus
from app.domain.learning_note import LearningNote
from app.infrastructure.database import create_engine_from_url, create_session_factory
from app.infrastructure.sqlite_repositories import (
    SQLiteArticleRepository,
    SQLiteLearningNoteRepository,
)
from tests.application.processing_fakes import FakeArticleExtractor, FakeArticleSource

_URL = "https://indianexpress.com/upsc/e2e-article"
_TEXT = "Real database end-to-end article body text about a UPSC topic." * 4


class _NoteGenerator:
    """Deterministic fake generator producing one note per given article."""

    def __init__(self) -> None:
        self.calls: list[Article] = []

    def generate(self, article: Article) -> LearningNote:
        self.calls.append(article)
        return LearningNote(
            article_id=article.id,
            summary="Summary.",
            why_it_matters="Why.",
            revision_note="Revise.",
            model_name="gpt-test",
            prompt_version="v1",
        )


def _candidate(url: str = _URL, external_id: str | None = "e2e-1") -> ArticleCandidate:
    return ArticleCandidate(
        source="indian_express",
        external_id=external_id,
        title="An E2E Title",
        url=url,
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=["polity"],
    )


def _build_service(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
    *,
    candidates: list[ArticleCandidate] | None = None,
    extraction: ExtractedArticle | None = None,
) -> tuple[ProcessNewsFeedService, FakeArticleSource, FakeArticleExtractor, _NoteGenerator]:
    source = FakeArticleSource(candidates if candidates is not None else [_candidate()])
    extractor = FakeArticleExtractor(
        {
            _URL: extraction
            if extraction is not None
            else ExtractedArticle(url=_URL, status=ExtractionStatus.SUCCESS, text=_TEXT)
        }
    )
    generator = _NoteGenerator()
    service = ProcessNewsFeedService(
        article_source=source,
        article_extractor=extractor,
        article_repository=article_repository,
        learning_note_repository=learning_note_repository,
        learning_note_generator=generator,
    )
    return service, source, extractor, generator


def test_new_article_travels_through_the_complete_pipeline(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    service, _, _, _ = _build_service(article_repository, learning_note_repository)

    summary = service.process()

    assert summary.new_articles == 1
    assert summary.successfully_extracted == 1
    assert summary.successfully_analyzed == 1
    assert summary.failed == 0

    stored = article_repository.get_by_url(_URL)
    assert stored is not None
    assert stored.processing_status is ProcessingStatus.ANALYZED
    assert stored.raw_text == _TEXT
    note = learning_note_repository.get_by_article_id(stored.id)
    assert note is not None
    assert note.article_id == stored.id


def test_article_and_note_survive_engine_reopen(migrated_db_url: str) -> None:
    engine = create_engine_from_url(migrated_db_url)
    session_factory = create_session_factory(engine)
    service, _, _, _ = _build_service(
        SQLiteArticleRepository(session_factory),
        SQLiteLearningNoteRepository(session_factory),
    )
    service.process()
    engine.dispose()

    reopened = create_engine_from_url(migrated_db_url)
    try:
        fresh_factory = create_session_factory(reopened)
        articles = SQLiteArticleRepository(fresh_factory)
        notes = SQLiteLearningNoteRepository(fresh_factory)
        stored = articles.get_by_url(_URL)
        assert stored is not None
        assert stored.processing_status is ProcessingStatus.ANALYZED
        assert notes.get_by_article_id(stored.id) is not None
    finally:
        reopened.dispose()


def test_rerun_creates_no_duplicate_article_or_note(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    service, _, _, generator = _build_service(article_repository, learning_note_repository)

    first = service.process()
    second = service.process()

    assert first.successfully_analyzed == 1
    assert second.duplicates_skipped == 1
    assert second.new_articles == 0
    assert second.successfully_analyzed == 0
    assert len(generator.calls) == 1

    assert len(article_repository.list_recent(limit=50)) == 1
    stored = article_repository.get_by_url(_URL)
    assert stored is not None
    assert learning_note_repository.get_by_article_id(stored.id) is not None


def test_stale_article_status_is_reconciled_against_existing_note(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    service, _, _, generator = _build_service(article_repository, learning_note_repository)
    service.process()

    stored = article_repository.get_by_url(_URL)
    assert stored is not None
    # Manually regress the status to simulate an interrupted earlier run.
    article_repository.update(
        reconstruct_article(
            stored,
            processing_status=ProcessingStatus.ANALYSIS_PENDING,
            failure_reason=None,
        )
    )

    summary = service.process()

    assert summary.reconciled == 1
    assert summary.failed == 0
    assert len(generator.calls) == 1  # never regenerated
    refreshed = article_repository.get_by_id(stored.id)
    assert refreshed is not None
    assert refreshed.processing_status is ProcessingStatus.ANALYZED


def test_extraction_failure_state_persists(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    service, _, _, _ = _build_service(
        article_repository,
        learning_note_repository,
        extraction=ExtractedArticle(
            url=_URL, status=ExtractionStatus.NETWORK_ERROR, error_reason="timed out"
        ),
    )

    summary = service.process()

    assert summary.failed == 1
    stored = article_repository.get_by_url(_URL)
    assert stored is not None
    assert stored.processing_status is ProcessingStatus.FAILED
    assert stored.failure_reason == "extraction: network error"
    assert stored.raw_text is None


def test_feed_window_manual_retry_succeeds(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    failing_service, _, _, _ = _build_service(
        article_repository,
        learning_note_repository,
        extraction=ExtractedArticle(
            url=_URL, status=ExtractionStatus.NETWORK_ERROR, error_reason="timed out"
        ),
    )
    failing_service.process()

    retry_service, _, _, _ = _build_service(article_repository, learning_note_repository)
    skipped = retry_service.process(retry_failed=False)
    assert skipped.duplicates_skipped == 1

    retried = retry_service.process(retry_failed=True)
    assert retried.successfully_analyzed == 1
    stored = article_repository.get_by_url(_URL)
    assert stored is not None
    assert stored.processing_status is ProcessingStatus.ANALYZED
    assert stored.failure_reason is None


def test_targeted_retry_works_after_article_leaves_the_feed(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    failing_service, _, _, _ = _build_service(
        article_repository,
        learning_note_repository,
        extraction=ExtractedArticle(
            url=_URL, status=ExtractionStatus.NETWORK_ERROR, error_reason="timed out"
        ),
    )
    failing_service.process()
    stored = article_repository.get_by_url(_URL)
    assert stored is not None

    # The article is gone from the feed; only retry_article can reach it.
    retry_service, source, _, _ = _build_service(
        article_repository, learning_note_repository, candidates=[]
    )
    result = retry_service.retry_article(stored.id)

    assert result.analyzed is True
    assert source.calls == 0
    refreshed = article_repository.get_by_id(stored.id)
    assert refreshed is not None
    assert refreshed.processing_status is ProcessingStatus.ANALYZED
    assert learning_note_repository.get_by_article_id(stored.id) is not None


class _FinalizationFailingArticles:
    """Wraps the real repository, failing only the ANALYZED finalization once."""

    def __init__(self, inner: ArticleRepository) -> None:
        self._inner = inner
        self.fail_finalization = True

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def update(self, article: Article) -> None:
        if self.fail_finalization and article.processing_status is ProcessingStatus.ANALYZED:
            raise RepositoryError("simulated database failure during finalization")
        self._inner.update(article)


def test_finalization_failure_leaves_durable_note_then_next_run_reconciles(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    wrapped = _FinalizationFailingArticles(article_repository)
    service, _, _, generator = _build_service(
        wrapped,  # type: ignore[arg-type]
        learning_note_repository,
    )

    first = service.process()

    assert first.successfully_analyzed == 0
    assert first.failed == 1
    assert first.failure_details[0].stage is PipelineStage.FINALIZATION
    stored = article_repository.get_by_url(_URL)
    assert stored is not None
    # Durable note, article resting at the last durable checkpoint.
    assert learning_note_repository.get_by_article_id(stored.id) is not None
    assert stored.processing_status is ProcessingStatus.ANALYSIS_PENDING

    wrapped.fail_finalization = False
    second = service.process()

    assert second.reconciled == 1
    assert second.failed == 0
    assert len(generator.calls) == 1  # the note was never regenerated
    refreshed = article_repository.get_by_id(stored.id)
    assert refreshed is not None
    assert refreshed.processing_status is ProcessingStatus.ANALYZED


def test_changed_url_is_persisted_without_duplicate_creation(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
) -> None:
    old_url = "https://indianexpress.com/upsc/old-e2e-url"
    seeded = Article(
        source="indian_express",
        external_id="e2e-1",
        title="An E2E Title",
        url=old_url,
        processing_status=ProcessingStatus.DISCOVERED,
    )
    article_repository.add(seeded)

    service, _, extractor, _ = _build_service(article_repository, learning_note_repository)

    summary = service.process()

    assert summary.new_articles == 0
    assert summary.successfully_analyzed == 1
    assert extractor.calls == [_URL]
    assert len(article_repository.list_recent(limit=50)) == 1
    refreshed = article_repository.get_by_id(seeded.id)
    assert refreshed is not None
    assert refreshed.url == _URL
    assert isinstance(refreshed.id, UUID)

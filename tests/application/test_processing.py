"""Tests for `app.application.processing`: the feed-processing pipeline.

Every test uses handwritten fakes (see `processing_fakes.py`) - no database,
no network, no live provider. These tests exercise the real
`ProcessNewsFeedService`: identity resolution, state reconstruction, stage
mapping, retry semantics, reconciliation, failure isolation, summary
counting, and privacy - never a fake pipeline.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.learning_notes import (
    LearningNoteProviderError,
    LearningNoteValidationError,
)
from app.application.processing import (
    REASON_ANALYSIS_PROVIDER,
    REASON_ANALYSIS_VALIDATION,
    REASON_MISSING_NOTE,
    REASON_NOTE_SAVE_FAILED,
    ArticleNotFoundError,
    ArticleProcessingResult,
    FailureDetail,
    PipelineStage,
    ProcessingSummary,
    ProcessNewsFeedService,
    new_article_from_candidate,
    reconstruct_article,
)
from app.application.repositories import DuplicateArticleError, RepositoryError
from app.application.sources import ArticleSourceError
from app.domain.article import Article, ArticleCandidate
from app.domain.enums import ProcessingStatus
from app.domain.extraction import ExtractedArticle, ExtractionStatus
from app.domain.learning_note import LearningNote
from tests.application.processing_fakes import (
    FakeArticleExtractor,
    FakeArticleSource,
    FakeLearningNoteGenerator,
    HostileExtractor,
    InMemoryArticleRepository,
    InMemoryLearningNoteRepository,
)

_URL = "https://indianexpress.com/upsc/article-one"
_TEXT = "Accepted extracted article body text about a UPSC topic." * 4


def _candidate(
    *,
    url: str = _URL,
    external_id: str | None = "ext-1",
    title: str = "A Title",
) -> ArticleCandidate:
    return ArticleCandidate(
        source="indian_express",
        external_id=external_id,
        title=title,
        url=url,
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=["polity"],
    )


def _note_for(article_id: object) -> LearningNote:
    return LearningNote(
        article_id=article_id,  # type: ignore[arg-type]
        summary="Summary.",
        why_it_matters="Why.",
        revision_note="Revise.",
        model_name="gpt-test",
        prompt_version="v1",
    )


def _success_extraction(url: str = _URL) -> ExtractedArticle:
    return ExtractedArticle(url=url, status=ExtractionStatus.SUCCESS, text=_TEXT)


def _make_service(
    *,
    source: FakeArticleSource | None = None,
    extractor: object | None = None,
    articles: InMemoryArticleRepository | None = None,
    notes: InMemoryLearningNoteRepository | None = None,
    generator: FakeLearningNoteGenerator | None = None,
) -> tuple[
    ProcessNewsFeedService,
    FakeArticleSource,
    FakeArticleExtractor,
    InMemoryArticleRepository,
    InMemoryLearningNoteRepository,
    FakeLearningNoteGenerator,
]:
    articles = articles if articles is not None else InMemoryArticleRepository()
    notes = notes if notes is not None else InMemoryLearningNoteRepository(articles)
    source = source if source is not None else FakeArticleSource([_candidate()])
    extractor_obj = (
        extractor if extractor is not None else FakeArticleExtractor({_URL: _success_extraction()})
    )
    generator = generator if generator is not None else FakeLearningNoteGenerator()
    service = ProcessNewsFeedService(
        article_source=source,
        article_extractor=extractor_obj,  # type: ignore[arg-type]
        article_repository=articles,
        learning_note_repository=notes,
        learning_note_generator=generator,
    )
    return service, source, extractor_obj, articles, notes, generator  # type: ignore[return-value]


def _seed_article(
    articles: InMemoryArticleRepository,
    *,
    status: ProcessingStatus,
    raw_text: str | None = None,
    failure_reason: str | None = None,
    url: str = _URL,
    external_id: str | None = "ext-1",
) -> Article:
    article = Article(
        source="indian_express",
        external_id=external_id,
        title="A Title",
        url=url,
        raw_text=raw_text,
        processing_status=status,
        failure_reason=failure_reason,
    )
    articles.seed(article)
    return article


def _scripted_note_generator(articles: InMemoryArticleRepository) -> FakeLearningNoteGenerator:
    """Generator whose one scripted note targets whichever article it is given."""

    class _Generator(FakeLearningNoteGenerator):
        def generate(self, article: Article) -> LearningNote:
            self.calls.append(article)
            return _note_for(article.id)

    return _Generator()


# --- new article success path -------------------------------------------------


def test_new_article_full_success() -> None:
    articles = InMemoryArticleRepository()
    service, _, _, _, notes, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert summary.total_discovered == 1
    assert summary.new_articles == 1
    assert summary.duplicates_skipped == 0
    assert summary.successfully_extracted == 1
    assert summary.successfully_analyzed == 1
    assert summary.reconciled == 0
    assert summary.failed == 0
    assert summary.failure_details == ()

    stored = articles.list_recent()[0]
    assert stored.processing_status is ProcessingStatus.ANALYZED
    assert stored.raw_text == _TEXT
    assert stored.failure_reason is None
    assert notes.get_by_article_id(stored.id) is not None


def test_new_article_counters_overlap_not_partition() -> None:
    """One fully successful new candidate increments three different counters."""
    articles = InMemoryArticleRepository()
    service, _, _, _, _, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )
    summary = service.process()
    assert (
        summary.new_articles + summary.duplicates_skipped + summary.failed
        != summary.new_articles
        + summary.duplicates_skipped
        + summary.failed
        + summary.successfully_extracted
        + summary.successfully_analyzed
    )
    assert summary.successfully_extracted == 1
    assert summary.successfully_analyzed == 1


# --- resumption of existing incomplete articles --------------------------------


def test_existing_discovered_article_is_resumed() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(articles, status=ProcessingStatus.DISCOVERED)
    service, _, extractor, _, notes, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert summary.new_articles == 0
    assert summary.duplicates_skipped == 0
    assert summary.successfully_extracted == 1
    assert summary.successfully_analyzed == 1
    assert extractor.calls == [_URL]
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED
    assert notes.get_by_article_id(seeded.id) is not None


def test_existing_extracted_article_resumes_analysis_without_reextraction() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=_TEXT)
    service, _, extractor, _, _, generator = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert extractor.calls == []
    assert summary.successfully_extracted == 0
    assert summary.successfully_analyzed == 1
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED


def test_analysis_pending_article_resumes_analysis_without_reextraction() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(articles, status=ProcessingStatus.ANALYSIS_PENDING, raw_text=_TEXT)
    service, _, extractor, _, _, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert extractor.calls == []
    assert summary.successfully_analyzed == 1
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED


def test_extracted_status_with_blank_raw_text_reextracts() -> None:
    """An inconsistent EXTRACTED-with-no-text state re-runs extraction."""
    articles = InMemoryArticleRepository()
    _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=None)
    service, _, extractor, _, _, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert extractor.calls == [_URL]
    assert summary.successfully_extracted == 1
    assert summary.successfully_analyzed == 1


# --- skip and reconcile -------------------------------------------------------


def test_analyzed_article_with_note_is_skipped() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(articles, status=ProcessingStatus.ANALYZED, raw_text=_TEXT)
    notes.seed(_note_for(seeded.id))
    service, _, extractor, _, _, generator = _make_service(articles=articles, notes=notes)

    summary = service.process()

    assert summary.duplicates_skipped == 1
    assert summary.successfully_analyzed == 0
    assert summary.reconciled == 0
    assert extractor.calls == []
    assert generator.calls == []


def test_stale_status_with_existing_note_is_reconciled() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(articles, status=ProcessingStatus.ANALYSIS_PENDING, raw_text=_TEXT)
    notes.seed(_note_for(seeded.id))
    service, _, _, _, _, generator = _make_service(articles=articles, notes=notes)

    summary = service.process()

    assert summary.reconciled == 1
    assert summary.successfully_analyzed == 0
    assert generator.calls == []
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED
    assert articles.stored(seeded.id).failure_reason is None


def test_failed_article_with_existing_note_is_reconciled_without_retry_flag() -> None:
    """Note-existence reconciliation is not gated by retry_failed."""
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(
        articles,
        status=ProcessingStatus.FAILED,
        raw_text=_TEXT,
        failure_reason="analysis: provider failure",
    )
    notes.seed(_note_for(seeded.id))
    service, _, _, _, _, generator = _make_service(articles=articles, notes=notes)

    summary = service.process(retry_failed=False)

    assert summary.reconciled == 1
    assert generator.calls == []
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED


def test_analyzed_article_without_note_is_invariant_violation() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(articles, status=ProcessingStatus.ANALYZED, raw_text=_TEXT)
    service, _, _, _, _, generator = _make_service(articles=articles)

    summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.FINALIZATION
    assert detail.reason_category == "invariant_violation"
    assert detail.message == REASON_MISSING_NOTE
    assert generator.calls == []
    stored = articles.stored(seeded.id)
    assert stored.processing_status is ProcessingStatus.FAILED
    assert stored.failure_reason == REASON_MISSING_NOTE


# --- failed-article retry semantics ---------------------------------------------


def test_failed_article_skipped_by_default() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(
        articles,
        status=ProcessingStatus.FAILED,
        failure_reason="extraction: network error",
    )
    service, _, extractor, _, _, generator = _make_service(articles=articles)

    summary = service.process()

    assert summary.duplicates_skipped == 1
    assert summary.failed == 0
    assert extractor.calls == []
    assert generator.calls == []
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.FAILED


def test_failed_article_retried_when_rediscovered_with_retry_flag() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(
        articles,
        status=ProcessingStatus.FAILED,
        failure_reason="extraction: network error",
    )
    service, _, extractor, _, notes, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process(retry_failed=True)

    assert extractor.calls == [_URL]
    assert summary.successfully_extracted == 1
    assert summary.successfully_analyzed == 1
    stored = articles.stored(seeded.id)
    assert stored.processing_status is ProcessingStatus.ANALYZED
    assert stored.failure_reason is None
    assert notes.get_by_article_id(seeded.id) is not None


def test_failed_article_with_text_retries_analysis_only() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(
        articles,
        status=ProcessingStatus.FAILED,
        raw_text=_TEXT,
        failure_reason="analysis: provider failure",
    )
    service, _, extractor, _, _, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process(retry_failed=True)

    assert extractor.calls == []
    assert summary.successfully_extracted == 0
    assert summary.successfully_analyzed == 1
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED


# --- targeted retry_article ------------------------------------------------------


def test_retry_article_succeeds_when_absent_from_feed() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(
        articles,
        status=ProcessingStatus.FAILED,
        failure_reason="extraction: network error",
    )
    source = FakeArticleSource([])  # article no longer in the feed window
    service, _, _, _, notes, _ = _make_service(
        source=source, articles=articles, generator=_scripted_note_generator(articles)
    )

    result = service.retry_article(seeded.id)

    assert result.analyzed is True
    assert result.failure is None
    assert source.calls == 0
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED
    assert notes.get_by_article_id(seeded.id) is not None


def test_retry_article_never_calls_the_source() -> None:
    articles = InMemoryArticleRepository()
    seeded = _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=_TEXT)
    source = FakeArticleSource([_candidate()])
    service, _, _, _, _, _ = _make_service(
        source=source, articles=articles, generator=_scripted_note_generator(articles)
    )

    service.retry_article(seeded.id)

    assert source.calls == 0


def test_retry_article_reconciles_when_note_already_exists() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(articles, status=ProcessingStatus.ANALYSIS_PENDING, raw_text=_TEXT)
    notes.seed(_note_for(seeded.id))
    service, _, _, _, _, generator = _make_service(articles=articles, notes=notes)

    result = service.retry_article(seeded.id)

    assert result.reconciled is True
    assert generator.calls == []


def test_retry_article_missing_id_raises_article_not_found() -> None:
    service, _, _, _, _, _ = _make_service()
    with pytest.raises(ArticleNotFoundError):
        service.retry_article(uuid4())


# --- identity resolution ----------------------------------------------------------


def test_identity_conflict_between_url_and_external_id_matches() -> None:
    articles = InMemoryArticleRepository()
    _seed_article(articles, status=ProcessingStatus.ANALYZED, url=_URL, external_id="other")
    _seed_article(
        articles,
        status=ProcessingStatus.ANALYZED,
        url="https://indianexpress.com/upsc/article-two",
        external_id="ext-1",
    )
    before_count = len(articles.list_recent())
    service, _, _, _, _, _ = _make_service(articles=articles)

    summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.IDENTITY_RESOLUTION
    assert detail.reason_category == "identity_conflict"
    assert detail.article_id is None
    assert len(articles.list_recent()) == before_count


def test_insert_race_recovers_through_existing_article_path() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    racing_article = Article(
        source="indian_express",
        external_id="ext-1",
        title="A Title",
        url=_URL,
        raw_text=_TEXT,
        processing_status=ProcessingStatus.ANALYZED,
    )

    def slip_in_competitor(article: Article) -> None:
        if articles.get_by_url(_URL) is None:
            articles.seed(racing_article)
            notes.seed(_note_for(racing_article.id))

    articles.before_add = slip_in_competitor
    service, _, _, _, _, generator = _make_service(articles=articles, notes=notes)

    summary = service.process()

    assert summary.new_articles == 0
    assert summary.failed == 0
    assert summary.duplicates_skipped == 1
    assert generator.calls == []


def test_source_discovery_failure_propagates_without_summary() -> None:
    source = FakeArticleSource(error=ArticleSourceError("feed unavailable"))
    service, _, _, _, _, _ = _make_service(source=source)
    with pytest.raises(ArticleSourceError):
        service.process()


# --- changed candidate URL ---------------------------------------------------------


def test_changed_url_is_persisted_before_extraction() -> None:
    articles = InMemoryArticleRepository()
    old_url = "https://indianexpress.com/upsc/old-url"
    seeded = _seed_article(
        articles, status=ProcessingStatus.DISCOVERED, url=old_url, external_id="ext-1"
    )
    new_url = _URL
    extractor = FakeArticleExtractor({new_url: _success_extraction(new_url)})
    service, _, _, _, _, _ = _make_service(
        articles=articles, extractor=extractor, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    # Extraction was called with the refreshed URL, never the stale one.
    assert extractor.calls == [new_url]
    stored = articles.stored(seeded.id)
    assert stored.url == new_url
    assert stored.id == seeded.id
    assert stored.created_at == seeded.created_at
    assert summary.new_articles == 0
    assert summary.successfully_analyzed == 1
    assert len(articles.list_recent()) == 1


def test_url_refresh_race_becomes_identity_conflict() -> None:
    articles = InMemoryArticleRepository()
    old_url = "https://indianexpress.com/upsc/old-url"
    seeded = _seed_article(
        articles, status=ProcessingStatus.DISCOVERED, url=old_url, external_id="ext-1"
    )

    def fail_refresh(article: Article) -> Exception | None:
        if article.id == seeded.id and article.url == _URL:
            return DuplicateArticleError("an article with this url already exists")
        return None

    articles.fail_update_when = fail_refresh
    service, _, extractor, _, _, _ = _make_service(articles=articles)

    summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.IDENTITY_RESOLUTION
    assert detail.reason_category == "identity_conflict"
    assert detail.article_id == seeded.id
    assert extractor.calls == []


# --- extraction outcomes -------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected_reason", "expected_category"),
    [
        (
            ExtractionStatus.INSUFFICIENT_CONTENT,
            "extraction: insufficient content",
            "insufficient_content",
        ),
        (ExtractionStatus.NETWORK_ERROR, "extraction: network error", "network_error"),
        (ExtractionStatus.UNSUPPORTED_PAGE, "extraction: unsupported page", "unsupported_page"),
        (ExtractionStatus.UNEXPECTED_ERROR, "extraction: unexpected error", "unexpected_error"),
    ],
)
def test_extraction_failure_mapping(
    status: ExtractionStatus, expected_reason: str, expected_category: str
) -> None:
    articles = InMemoryArticleRepository()
    extractor = FakeArticleExtractor(
        {
            _URL: ExtractedArticle(
                url=_URL,
                status=status,
                text="partial text" if status is ExtractionStatus.INSUFFICIENT_CONTENT else None,
                error_reason="a reason from the extractor",
            )
        }
    )
    service, _, _, _, _, generator = _make_service(articles=articles, extractor=extractor)

    summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.EXTRACTION
    assert detail.reason_category == expected_category
    assert detail.message == expected_reason
    assert generator.calls == []

    stored = articles.list_recent()[0]
    assert stored.processing_status is ProcessingStatus.FAILED
    assert stored.failure_reason == expected_reason
    # Unusable partial extraction text is never persisted.
    assert stored.raw_text is None


# --- analysis outcomes ----------------------------------------------------------------


def test_provider_failure_marks_failed_and_retains_text() -> None:
    articles = InMemoryArticleRepository()
    generator = FakeLearningNoteGenerator([LearningNoteProviderError("provider blew up")])
    service, _, _, _, _, _ = _make_service(articles=articles, generator=generator)

    summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.ANALYSIS
    assert detail.reason_category == "provider_failure"
    assert detail.message == REASON_ANALYSIS_PROVIDER

    stored = articles.list_recent()[0]
    assert stored.processing_status is ProcessingStatus.FAILED
    assert stored.failure_reason == REASON_ANALYSIS_PROVIDER
    assert stored.raw_text == _TEXT


def test_validation_exhaustion_marks_failed_and_retains_text() -> None:
    articles = InMemoryArticleRepository()
    generator = FakeLearningNoteGenerator([LearningNoteValidationError("exhausted")])
    service, _, _, _, _, _ = _make_service(articles=articles, generator=generator)

    summary = service.process()

    detail = summary.failure_details[0]
    assert detail.reason_category == "validation_exhausted"
    assert detail.message == REASON_ANALYSIS_VALIDATION
    stored = articles.list_recent()[0]
    assert stored.failure_reason == REASON_ANALYSIS_VALIDATION
    assert stored.raw_text == _TEXT


def test_generator_receives_analysis_pending_article() -> None:
    articles = InMemoryArticleRepository()
    generator = _scripted_note_generator(articles)
    service, _, _, _, _, _ = _make_service(articles=articles, generator=generator)

    service.process()

    assert len(generator.calls) == 1
    assert generator.calls[0].processing_status is ProcessingStatus.ANALYSIS_PENDING


# --- persistence failures and recovery ---------------------------------------------


def test_learning_note_add_failure_marks_failed() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    notes.fail_add_when = lambda note: RepositoryError("database is down")
    service, _, _, _, _, _ = _make_service(
        articles=articles, notes=notes, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.PERSISTENCE
    assert detail.reason_category == "note_save_failed"
    stored = articles.list_recent()[0]
    assert stored.processing_status is ProcessingStatus.FAILED
    assert stored.failure_reason == REASON_NOTE_SAVE_FAILED
    assert stored.raw_text == _TEXT


def test_duplicate_learning_note_is_reconciled_not_replaced() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=_TEXT)
    original_note = _note_for(seeded.id)

    def seed_before_add(note: LearningNote) -> Exception | None:
        # Simulate a competing note appearing between generation and add.
        if notes.get_by_article_id(seeded.id) is None:
            notes.seed(original_note)
        return None

    notes.fail_add_when = seed_before_add
    service, _, _, _, _, _ = _make_service(
        articles=articles, notes=notes, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert summary.reconciled == 1
    assert summary.successfully_analyzed == 0
    assert summary.failed == 0
    # The pre-existing note was reused, never replaced.
    persisted = notes.get_by_article_id(seeded.id)
    assert persisted is not None
    assert persisted.id == original_note.id
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED


def test_finalization_failure_after_durable_note() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=_TEXT)

    def fail_final_update(article: Article) -> Exception | None:
        if article.processing_status is ProcessingStatus.ANALYZED:
            return RepositoryError("database went away")
        return None

    articles.fail_update_when = fail_final_update
    service, _, _, _, _, _ = _make_service(
        articles=articles, notes=notes, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert summary.successfully_analyzed == 0
    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.stage is PipelineStage.FINALIZATION
    assert detail.reason_category == "finalization_failed"

    # The note is durable and the article rests at its last durable
    # checkpoint - never a deliberate FAILED + existing-note state.
    assert notes.get_by_article_id(seeded.id) is not None
    stored = articles.stored(seeded.id)
    assert stored.processing_status is ProcessingStatus.ANALYSIS_PENDING
    failed_updates = [
        a for a in articles.update_calls if a.processing_status is ProcessingStatus.FAILED
    ]
    assert failed_updates == []


def test_next_run_reconciles_after_finalization_failure() -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=_TEXT)

    def fail_final_update(article: Article) -> Exception | None:
        if article.processing_status is ProcessingStatus.ANALYZED:
            return RepositoryError("database went away")
        return None

    articles.fail_update_when = fail_final_update
    service, _, _, _, _, generator = _make_service(
        articles=articles, notes=notes, generator=_scripted_note_generator(articles)
    )
    service.process()

    articles.fail_update_when = lambda article: None
    second = service.process()

    assert second.reconciled == 1
    assert second.failed == 0
    # The generator ran exactly once, in the first run only.
    assert len(generator.calls) == 1
    assert articles.stored(seeded.id).processing_status is ProcessingStatus.ANALYZED


# --- failure isolation ---------------------------------------------------------------


def test_one_failure_does_not_stop_later_candidates() -> None:
    url_ok_1 = "https://indianexpress.com/upsc/ok-one"
    url_bad = "https://indianexpress.com/upsc/bad"
    url_ok_2 = "https://indianexpress.com/upsc/ok-two"
    candidates = [
        _candidate(url=url_ok_1, external_id="a"),
        _candidate(url=url_bad, external_id="b"),
        _candidate(url=url_ok_2, external_id="c"),
    ]
    articles = InMemoryArticleRepository()
    extractor = FakeArticleExtractor(
        {
            url_ok_1: _success_extraction(url_ok_1),
            url_bad: ExtractedArticle(
                url=url_bad,
                status=ExtractionStatus.NETWORK_ERROR,
                error_reason="timed out",
            ),
            url_ok_2: _success_extraction(url_ok_2),
        }
    )
    service, _, _, _, _, _ = _make_service(
        source=FakeArticleSource(candidates),
        articles=articles,
        extractor=extractor,
        generator=_scripted_note_generator(articles),
    )

    summary = service.process()

    assert summary.total_discovered == 3
    assert summary.new_articles == 3
    assert summary.successfully_analyzed == 2
    assert summary.failed == 1
    assert extractor.calls == [url_ok_1, url_bad, url_ok_2]


def test_unexpected_extractor_exception_is_isolated() -> None:
    url_bad = "https://indianexpress.com/upsc/bad"
    url_ok = "https://indianexpress.com/upsc/ok"
    articles = InMemoryArticleRepository()

    class _SplitExtractor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def extract(self, url: str) -> ExtractedArticle:
            self.calls.append(url)
            if url == url_bad:
                raise RuntimeError("unexpected defect with sensitive stuff inside")
            return _success_extraction(url_ok)

    extractor = _SplitExtractor()
    service, _, _, _, _, _ = _make_service(
        source=FakeArticleSource(
            [_candidate(url=url_bad, external_id="a"), _candidate(url=url_ok, external_id="b")]
        ),
        articles=articles,
        extractor=extractor,
        generator=_scripted_note_generator(articles),
    )

    summary = service.process()

    assert summary.failed == 1
    assert summary.successfully_analyzed == 1
    detail = summary.failure_details[0]
    assert detail.reason_category == "unexpected_error"
    assert detail.message == "pipeline: unexpected error"
    # Best-effort FAILED mark happened for the bad article (no durable note).
    bad = articles.get_by_url(url_bad)
    assert bad is not None
    assert bad.processing_status is ProcessingStatus.FAILED


def test_unexpected_failure_produces_exactly_one_failure_detail() -> None:
    articles = InMemoryArticleRepository()
    extractor = HostileExtractor(RuntimeError("boom"))
    service, _, _, _, _, _ = _make_service(articles=articles, extractor=extractor)

    summary = service.process()

    assert summary.failed == 1
    assert len(summary.failure_details) == 1


# --- summary semantics -----------------------------------------------------------------


def test_no_service_level_mutable_counters() -> None:
    """A second run's summary reflects only that run, never accumulated state."""
    articles = InMemoryArticleRepository()
    service, _, _, _, _, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    first = service.process()
    second = service.process()

    assert first.new_articles == 1
    assert first.successfully_analyzed == 1
    assert second.new_articles == 0
    assert second.successfully_analyzed == 0
    assert second.duplicates_skipped == 1
    assert second.total_discovered == 1


def test_summary_has_no_false_partition_invariant() -> None:
    """A resumed article makes new+skipped+failed < total untrue as a partition."""
    articles = InMemoryArticleRepository()
    _seed_article(articles, status=ProcessingStatus.EXTRACTED, raw_text=_TEXT)
    service, _, _, _, _, _ = _make_service(
        articles=articles, generator=_scripted_note_generator(articles)
    )

    summary = service.process()

    assert summary.total_discovered == 1
    assert summary.new_articles == 0
    assert summary.duplicates_skipped == 0
    assert summary.failed == 0
    assert summary.successfully_analyzed == 1
    assert (
        summary.new_articles + summary.duplicates_skipped + summary.failed
        != summary.total_discovered
    )


def test_failure_details_are_deterministic_feed_order() -> None:
    url_bad_1 = "https://indianexpress.com/upsc/bad-one"
    url_bad_2 = "https://indianexpress.com/upsc/bad-two"
    articles = InMemoryArticleRepository()
    extractor = FakeArticleExtractor(
        {
            url_bad_1: ExtractedArticle(
                url=url_bad_1, status=ExtractionStatus.NETWORK_ERROR, error_reason="x"
            ),
            url_bad_2: ExtractedArticle(
                url=url_bad_2,
                status=ExtractionStatus.INSUFFICIENT_CONTENT,
                error_reason="y",
            ),
        }
    )
    service, _, _, _, _, _ = _make_service(
        source=FakeArticleSource(
            [
                _candidate(url=url_bad_1, external_id="a"),
                _candidate(url=url_bad_2, external_id="b"),
            ]
        ),
        articles=articles,
        extractor=extractor,
    )

    summary = service.process()

    assert summary.failed == 2
    first_url, second_url = (detail.url for detail in summary.failure_details)
    assert first_url is not None and "bad-one" in first_url
    assert second_url is not None and "bad-two" in second_url
    assert summary.failed == len(summary.failure_details)


def test_processing_summary_rejects_negative_counts() -> None:
    with pytest.raises(ValueError, match="negative"):
        ProcessingSummary(
            total_discovered=-1,
            new_articles=0,
            duplicates_skipped=0,
            successfully_extracted=0,
            successfully_analyzed=0,
            reconciled=0,
            failed=0,
            failure_details=(),
        )


def test_processing_summary_rejects_failed_count_mismatch() -> None:
    with pytest.raises(ValueError, match="failure_details"):
        ProcessingSummary(
            total_discovered=1,
            new_articles=0,
            duplicates_skipped=0,
            successfully_extracted=0,
            successfully_analyzed=0,
            reconciled=0,
            failed=1,
            failure_details=(),
        )


def test_article_processing_result_rejects_contradictory_flags() -> None:
    detail = FailureDetail(
        article_id=None,
        source="indian_express",
        external_id=None,
        url=None,
        stage=PipelineStage.ANALYSIS,
        reason_category="provider_failure",
        message="analysis: provider failure",
    )
    with pytest.raises(ValueError, match="skipped"):
        ArticleProcessingResult(article_id=None, skipped=True, analyzed=True)
    with pytest.raises(ValueError, match="analyzed and reconciled"):
        ArticleProcessingResult(article_id=None, analyzed=True, reconciled=True)
    with pytest.raises(ValueError, match="analyzed"):
        ArticleProcessingResult(article_id=None, analyzed=True, failure=detail)
    with pytest.raises(ValueError, match="reconciled"):
        ArticleProcessingResult(article_id=None, reconciled=True, failure=detail)


# --- privacy ---------------------------------------------------------------------------


def test_logs_and_failure_details_contain_no_article_or_provider_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body_marker = "UNMISTAKABLE-ARTICLE-BODY-MARKER"
    provider_marker = "UNMISTAKABLE-PROVIDER-ERROR-DETAIL"
    articles = InMemoryArticleRepository()
    extractor = FakeArticleExtractor(
        {_URL: ExtractedArticle(url=_URL, status=ExtractionStatus.SUCCESS, text=body_marker * 20)}
    )
    generator = FakeLearningNoteGenerator([LearningNoteProviderError(provider_marker)])
    service, _, _, _, _, _ = _make_service(
        articles=articles, extractor=extractor, generator=generator
    )

    with caplog.at_level(logging.INFO):
        summary = service.process()

    assert body_marker not in caplog.text
    assert provider_marker not in caplog.text
    for detail in summary.failure_details:
        assert body_marker not in detail.message
        assert provider_marker not in detail.message


def test_failure_detail_url_strips_query_parameters() -> None:
    url = "https://indianexpress.com/upsc/bad?utm_source=feed&token=SECRET"
    articles = InMemoryArticleRepository()
    extractor = FakeArticleExtractor(
        {url: ExtractedArticle(url=url, status=ExtractionStatus.NETWORK_ERROR, error_reason="x")}
    )
    service, _, _, _, _, _ = _make_service(
        source=FakeArticleSource([_candidate(url=url, external_id="q")]),
        articles=articles,
        extractor=extractor,
    )

    summary = service.process()

    detail = summary.failure_details[0]
    assert detail.url == "https://indianexpress.com/upsc/bad"
    assert detail.url is not None and "SECRET" not in detail.url


# --- reconstruct_article and new_article_from_candidate ---------------------------------


def test_reconstruct_article_runs_full_validation() -> None:
    article = Article(
        source="indian_express",
        title="T",
        url=_URL,
        processing_status=ProcessingStatus.DISCOVERED,
    )
    with pytest.raises(ValueError):
        reconstruct_article(
            article, processing_status=ProcessingStatus.FAILED, failure_reason=None
        )


def test_rejected_reconstruction_leaves_original_unchanged() -> None:
    article = Article(
        source="indian_express",
        title="T",
        url=_URL,
        raw_text=_TEXT,
        processing_status=ProcessingStatus.EXTRACTED,
    )
    snapshot = article.model_dump()
    with pytest.raises(ValueError):
        reconstruct_article(
            article, processing_status=ProcessingStatus.FAILED, failure_reason="   "
        )
    assert article.model_dump() == snapshot


def test_reconstruct_article_preserves_identity_and_clears_reason() -> None:
    article = Article(
        source="indian_express",
        external_id="ext-9",
        title="T",
        url=_URL,
        raw_text=_TEXT,
        processing_status=ProcessingStatus.FAILED,
        failure_reason="analysis: provider failure",
    )
    rebuilt = reconstruct_article(
        article, processing_status=ProcessingStatus.EXTRACTED, failure_reason=None
    )
    assert rebuilt.id == article.id
    assert rebuilt.created_at == article.created_at
    assert rebuilt.external_id == article.external_id
    assert rebuilt.raw_text == _TEXT
    assert rebuilt.failure_reason is None
    assert rebuilt is not article
    assert article.processing_status is ProcessingStatus.FAILED  # original untouched


def test_reconstruct_article_raw_text_sentinel_vs_explicit_none() -> None:
    article = Article(
        source="indian_express",
        title="T",
        url=_URL,
        raw_text=_TEXT,
        processing_status=ProcessingStatus.EXTRACTED,
    )
    unchanged = reconstruct_article(
        article, processing_status=ProcessingStatus.ANALYSIS_PENDING, failure_reason=None
    )
    cleared = reconstruct_article(
        article,
        processing_status=ProcessingStatus.DISCOVERED,
        failure_reason=None,
        raw_text=None,
    )
    assert unchanged.raw_text == _TEXT
    assert cleared.raw_text is None


def test_reconstruct_article_updated_at_is_monotonic_utc() -> None:
    article = Article(
        source="indian_express",
        title="T",
        url=_URL,
        processing_status=ProcessingStatus.DISCOVERED,
    )
    past = datetime(2020, 1, 1, tzinfo=UTC)
    rebuilt = reconstruct_article(
        article,
        processing_status=ProcessingStatus.EXTRACTED,
        failure_reason=None,
        raw_text=_TEXT,
        updated_at=past,
    )
    assert rebuilt.updated_at >= article.updated_at
    assert rebuilt.updated_at.tzinfo == UTC


def test_new_article_from_candidate_maps_fields_and_copies_categories() -> None:
    candidate = _candidate()
    article = new_article_from_candidate(candidate)

    assert article.source == candidate.source
    assert article.external_id == candidate.external_id
    assert article.title == candidate.title
    assert article.url == candidate.url
    assert article.author == candidate.author
    assert article.published_at == candidate.published_at
    assert article.categories == candidate.categories
    assert article.categories is not candidate.categories
    assert article.raw_text is None
    assert article.processing_status is ProcessingStatus.DISCOVERED
    assert article.failure_reason is None
    assert article.updated_at.tzinfo == UTC

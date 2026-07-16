"""Cross-surface privacy regression tests.

These fill genuinely uncovered privacy paths, distinct from the existing
per-adapter and dashboard privacy tests:

* the full `process-feed` CLI path (compose -> process -> printed summary),
  which the existing CLI tests only exercise for a discovery-failure stub;
* the `retry-article` CLI stderr path;
* an extractor `error_reason` carrying a secret, which is never marker-tested
  elsewhere;
* a `RepositoryError` carrying a secret, raised during processing, reaching
  the CLI.

Every test drives real production code (`ProcessNewsFeedService`, `app.cli`)
with fakes that embed distinctive secret markers, and asserts the markers
never reach stdout, stderr, logs, or persisted failure state, while the fixed
safe stage/category messages remain present. No live service is called.
"""

import logging
from datetime import UTC, datetime

import pytest

import app.cli as cli
from app.application.learning_notes import LearningNoteProviderError
from app.application.processing import ProcessNewsFeedService
from app.application.repositories import RepositoryError
from app.domain.article import Article, ArticleCandidate
from app.domain.enums import ProcessingStatus
from app.domain.extraction import ExtractedArticle, ExtractionStatus
from app.domain.learning_note import LearningNote
from tests.application.processing_fakes import (
    FakeArticleExtractor,
    FakeArticleSource,
    FakeLearningNoteGenerator,
    InMemoryArticleRepository,
    InMemoryLearningNoteRepository,
)

SECRET_ARTICLE_BODY_MARKER = "SECRET-ARTICLE-BODY-MARKER-8x1"
SECRET_PROVIDER_OUTPUT_MARKER = "SECRET-PROVIDER-OUTPUT-MARKER-8x2"
SECRET_EXTRACTOR_REASON_MARKER = "SECRET-EXTRACTOR-REASON-MARKER-8x3"
SECRET_DATABASE_URL_MARKER = "SECRET-DATABASE-DETAIL-MARKER-8x4"
SECRET_QUERY_TOKEN_MARKER = "SECRET-QUERY-TOKEN-8x5"

_ALL_MARKERS = (
    SECRET_ARTICLE_BODY_MARKER,
    SECRET_PROVIDER_OUTPUT_MARKER,
    SECRET_EXTRACTOR_REASON_MARKER,
    SECRET_DATABASE_URL_MARKER,
    SECRET_QUERY_TOKEN_MARKER,
)

_URL = f"https://indianexpress.com/upsc/article?token={SECRET_QUERY_TOKEN_MARKER}"
_ACCEPTED_TEXT = "Accepted extracted body about a UPSC topic. " * 5


def _candidate(url: str = _URL, external_id: str = "priv-1") -> ArticleCandidate:
    return ArticleCandidate(
        source="indian_express",
        external_id=external_id,
        title="A Title",
        url=url,
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=["polity"],
    )


def _note_for(article_id: object) -> LearningNote:
    return LearningNote(
        article_id=article_id,  # type: ignore[arg-type]
        summary="s",
        why_it_matters="w",
        revision_note="r",
        model_name="gpt-test",
        prompt_version="v1",
    )


def _assert_no_markers(*texts: str) -> None:
    blob = "\n".join(texts)
    for marker in _ALL_MARKERS:
        assert marker not in blob, f"leaked marker {marker!r}"


def test_process_feed_cli_never_leaks_markers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The full CLI process-feed path keeps every secret out of stdout/stderr/logs."""
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    # Article A: extraction succeeds (accepted text carries a body marker),
    # then the generator fails with a provider error carrying a marker.
    url_a = _URL
    # Article B: extraction fails with an error_reason carrying a marker.
    url_b = f"https://indianexpress.com/upsc/other?token={SECRET_QUERY_TOKEN_MARKER}"
    source = FakeArticleSource([_candidate(url_a, "a"), _candidate(url_b, "b")])
    extractor = FakeArticleExtractor(
        {
            url_a: ExtractedArticle(
                url=url_a,
                status=ExtractionStatus.SUCCESS,
                text=f"{_ACCEPTED_TEXT} {SECRET_ARTICLE_BODY_MARKER}",
            ),
            url_b: ExtractedArticle(
                url=url_b,
                status=ExtractionStatus.NETWORK_ERROR,
                error_reason=f"boom {SECRET_EXTRACTOR_REASON_MARKER}",
            ),
        }
    )
    generator = FakeLearningNoteGenerator(
        [LearningNoteProviderError(f"provider said {SECRET_PROVIDER_OUTPUT_MARKER}")]
    )
    service = ProcessNewsFeedService(
        article_source=source,
        article_extractor=extractor,
        article_repository=articles,
        learning_note_repository=notes,
        learning_note_generator=generator,
    )
    monkeypatch.setattr(cli, "_compose_service", lambda settings: service)

    with caplog.at_level(logging.INFO):
        exit_code = cli.main(["process-feed"])

    out = capsys.readouterr()
    assert exit_code == 1
    _assert_no_markers(out.out, out.err, caplog.text)
    # Fixed, safe stage/category messages remain visible.
    assert "failed:" in out.out
    assert "analysis: provider failure" in out.out
    assert "extraction: network error" in out.out


def test_retry_article_cli_never_leaks_provider_marker(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    seeded = Article(
        source="indian_express",
        external_id="priv-2",
        title="A Title",
        url="https://indianexpress.com/upsc/seeded",
        raw_text=f"{_ACCEPTED_TEXT} {SECRET_ARTICLE_BODY_MARKER}",
        processing_status=ProcessingStatus.FAILED,
        failure_reason="analysis: provider failure",
    )
    articles.seed(seeded)
    generator = FakeLearningNoteGenerator(
        [LearningNoteProviderError(f"provider said {SECRET_PROVIDER_OUTPUT_MARKER}")]
    )
    service = ProcessNewsFeedService(
        article_source=FakeArticleSource([]),
        article_extractor=FakeArticleExtractor({}),
        article_repository=articles,
        learning_note_repository=notes,
        learning_note_generator=generator,
    )
    monkeypatch.setattr(cli, "_compose_service", lambda settings: service)

    with caplog.at_level(logging.INFO):
        exit_code = cli.main(["retry-article", str(seeded.id)])

    out = capsys.readouterr()
    assert exit_code == 1
    _assert_no_markers(out.out, out.err, caplog.text)
    assert "analysis: provider failure" in out.err


def test_extractor_error_reason_marker_not_persisted_or_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An extractor error_reason carrying a secret never reaches the persisted
    failure reason, the FailureDetail message, or the logs.
    """
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    url = "https://indianexpress.com/upsc/extract-fail"
    extractor = FakeArticleExtractor(
        {
            url: ExtractedArticle(
                url=url,
                status=ExtractionStatus.UNSUPPORTED_PAGE,
                error_reason=f"unsupported because {SECRET_EXTRACTOR_REASON_MARKER}",
            )
        }
    )
    service = ProcessNewsFeedService(
        article_source=FakeArticleSource([_candidate(url, "c")]),
        article_extractor=extractor,
        article_repository=articles,
        learning_note_repository=notes,
        learning_note_generator=FakeLearningNoteGenerator([]),
    )

    with caplog.at_level(logging.INFO):
        summary = service.process()

    assert summary.failed == 1
    detail = summary.failure_details[0]
    assert detail.message == "extraction: unsupported page"
    assert SECRET_EXTRACTOR_REASON_MARKER not in detail.message
    assert SECRET_EXTRACTOR_REASON_MARKER not in caplog.text
    stored = articles.get_by_url(url)
    assert stored is not None
    assert stored.failure_reason == "extraction: unsupported page"
    assert SECRET_EXTRACTOR_REASON_MARKER not in (stored.failure_reason or "")


def test_repository_error_marker_not_leaked_through_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A RepositoryError carrying a secret, raised during finalization, never
    reaches CLI output or logs; only a fixed safe message does.
    """
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    url = "https://indianexpress.com/upsc/repo-fail"

    def fail_analyzed_update(article: Article) -> Exception | None:
        if article.processing_status is ProcessingStatus.ANALYZED:
            return RepositoryError(f"db url {SECRET_DATABASE_URL_MARKER}")
        return None

    articles.fail_update_when = fail_analyzed_update

    class _Gen(FakeLearningNoteGenerator):
        def generate(self, article: Article) -> LearningNote:
            self.calls.append(article)
            return _note_for(article.id)

    extractor = FakeArticleExtractor(
        {url: ExtractedArticle(url=url, status=ExtractionStatus.SUCCESS, text=_ACCEPTED_TEXT)}
    )
    service = ProcessNewsFeedService(
        article_source=FakeArticleSource([_candidate(url, "d")]),
        article_extractor=extractor,
        article_repository=articles,
        learning_note_repository=notes,
        learning_note_generator=_Gen(),
    )
    monkeypatch.setattr(cli, "_compose_service", lambda settings: service)

    with caplog.at_level(logging.INFO):
        exit_code = cli.main(["process-feed"])

    out = capsys.readouterr()
    assert exit_code == 1
    _assert_no_markers(out.out, out.err, caplog.text)
    # The finalization failure is reported with a fixed safe message.
    assert "persistence: article finalization failed" in out.out

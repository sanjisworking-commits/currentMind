"""Tests for the `app.cli` command-line entry point.

Composition is either monkeypatched (`app.cli._compose_service` replaced by a
service built from fakes) or exercised for real against an isolated temporary
database with fake credentials - never against the development database, live
Indian Express, or live OpenAI. All assertions cover exit codes and captured
stdout/stderr.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

import app.cli as cli
from app.application.processing import (
    ArticleNotFoundError,
    ArticleProcessingResult,
    FailureDetail,
    PipelineStage,
    ProcessingSummary,
    ProcessNewsFeedService,
)
from app.application.sources import ArticleSourceError
from app.domain.article import ArticleCandidate
from app.domain.extraction import ExtractedArticle, ExtractionStatus
from app.domain.learning_note import LearningNote
from tests.application.processing_fakes import (
    FakeArticleExtractor,
    FakeArticleSource,
    InMemoryArticleRepository,
    InMemoryLearningNoteRepository,
)

_URL = "https://indianexpress.com/upsc/cli-article"
_TEXT = "CLI test article body text about a UPSC topic." * 5


class _NoteGenerator:
    def generate(self, article: object) -> LearningNote:
        return LearningNote(
            article_id=article.id,  # type: ignore[attr-defined]
            summary="Summary.",
            why_it_matters="Why.",
            revision_note="Revise.",
            model_name="gpt-test",
            prompt_version="v1",
        )


def _candidate() -> ArticleCandidate:
    return ArticleCandidate(
        source="indian_express",
        external_id="cli-1",
        title="A CLI Title",
        url=_URL,
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=["polity"],
    )


def _fake_service(
    *,
    candidates: list[ArticleCandidate] | None = None,
    extraction: ExtractedArticle | None = None,
) -> tuple[ProcessNewsFeedService, InMemoryArticleRepository, InMemoryLearningNoteRepository]:
    articles = InMemoryArticleRepository()
    notes = InMemoryLearningNoteRepository(articles)
    service = ProcessNewsFeedService(
        article_source=FakeArticleSource(
            candidates if candidates is not None else [_candidate()]
        ),
        article_extractor=FakeArticleExtractor(
            {
                _URL: extraction
                if extraction is not None
                else ExtractedArticle(url=_URL, status=ExtractionStatus.SUCCESS, text=_TEXT)
            }
        ),
        article_repository=articles,
        learning_note_repository=notes,
        learning_note_generator=_NoteGenerator(),
    )
    return service, articles, notes


def _patch_service(
    monkeypatch: pytest.MonkeyPatch, service: ProcessNewsFeedService
) -> None:
    monkeypatch.setattr(cli, "_compose_service", lambda settings: service)


# --- process-feed -----------------------------------------------------------------


def test_process_feed_success_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    service, _, _ = _fake_service()
    _patch_service(monkeypatch, service)

    exit_code = cli.main(["process-feed"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "total discovered:       1" in captured.out
    assert "new articles:           1" in captured.out
    assert "successfully analyzed:  1" in captured.out
    assert "failed:                 0" in captured.out


def test_process_feed_article_failure_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    service, _, _ = _fake_service(
        extraction=ExtractedArticle(
            url=_URL, status=ExtractionStatus.NETWORK_ERROR, error_reason="timed out"
        )
    )
    _patch_service(monkeypatch, service)

    exit_code = cli.main(["process-feed"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "failed:                 1" in captured.out
    assert "extraction: network error" in captured.out


def test_process_feed_passes_retry_failed_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, bool] = {}

    class _RecordingService:
        def process(self, *, retry_failed: bool = False) -> ProcessingSummary:
            recorded["retry_failed"] = retry_failed
            return ProcessingSummary(
                total_discovered=0,
                new_articles=0,
                duplicates_skipped=0,
                successfully_extracted=0,
                successfully_analyzed=0,
                reconciled=0,
                failed=0,
                failure_details=(),
            )

    monkeypatch.setattr(cli, "_compose_service", lambda settings: _RecordingService())

    assert cli.main(["process-feed"]) == 0
    assert recorded["retry_failed"] is False
    assert cli.main(["process-feed", "--retry-failed"]) == 0
    assert recorded["retry_failed"] is True


def test_process_feed_discovery_failure_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _FailingService:
        def process(self, *, retry_failed: bool = False) -> ProcessingSummary:
            raise ArticleSourceError("RSS feed at https://example.test/feed could not be parsed")

    monkeypatch.setattr(cli, "_compose_service", lambda settings: _FailingService())

    exit_code = cli.main(["process-feed"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Feed discovery failed" in captured.err


# --- retry-article -----------------------------------------------------------------


def test_retry_article_success_exit_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = ArticleProcessingResult(article_id=uuid4(), analyzed=True, extracted=True)

    class _RetryService:
        def retry_article(self, article_id: object) -> ArticleProcessingResult:
            return result

    monkeypatch.setattr(cli, "_compose_service", lambda settings: _RetryService())

    exit_code = cli.main(["retry-article", str(uuid4())])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "analyzed successfully" in captured.out


def test_retry_article_failure_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    article_id = uuid4()
    result = ArticleProcessingResult(
        article_id=article_id,
        failure=FailureDetail(
            article_id=article_id,
            source="indian_express",
            external_id=None,
            url=None,
            stage=PipelineStage.ANALYSIS,
            reason_category="provider_failure",
            message="analysis: provider failure",
        ),
    )

    class _RetryService:
        def retry_article(self, article_id: object) -> ArticleProcessingResult:
            return result

    monkeypatch.setattr(cli, "_compose_service", lambda settings: _RetryService())

    exit_code = cli.main(["retry-article", str(article_id)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "analysis: provider failure" in captured.err


def test_retry_article_invalid_uuid_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    composed: list[bool] = []
    monkeypatch.setattr(
        cli, "_compose_service", lambda settings: composed.append(True)
    )

    exit_code = cli.main(["retry-article", "not-a-uuid"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "not a valid UUID" in captured.err
    assert composed == []  # invalid input is rejected before composition


def test_retry_article_missing_article_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _RetryService:
        def retry_article(self, article_id: object) -> ArticleProcessingResult:
            raise ArticleNotFoundError(f"no article with id {article_id} exists")

    monkeypatch.setattr(cli, "_compose_service", lambda settings: _RetryService())

    exit_code = cli.main(["retry-article", str(uuid4())])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no article with id" in captured.err


# --- composition and configuration ---------------------------------------------------


def _set_valid_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli-test.db'}")
    monkeypatch.setenv("RSS_URL", "https://feed.invalid/upsc/feed/")


def test_missing_api_key_exit_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _set_valid_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    exit_code = cli.main(["process-feed"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "OPENAI_API_KEY is required" in captured.err


def test_unmigrated_database_prints_safe_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    # Real composition path: valid (fake) credentials, but the database file
    # has never been migrated, so the readiness probe fails.
    _set_valid_env(monkeypatch, tmp_path)

    exit_code = cli.main(["process-feed"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Database unavailable or schema not initialized" in captured.err
    assert "alembic upgrade head" in captured.err
    # No raw database/driver detail leaks to the user.
    combined = (captured.out + captured.err).lower()
    assert "sqlalchemy" not in combined
    assert "operationalerror" not in combined
    assert "no such table" not in combined


def test_cli_never_touches_development_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _set_valid_env(monkeypatch, tmp_path)
    dev_db = Path("database/currentmind.db")
    existed_before = dev_db.exists()

    cli.main(["process-feed"])
    capsys.readouterr()

    assert dev_db.exists() == existed_before

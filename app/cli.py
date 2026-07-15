"""Command-line entry point for the CurrentMind processing pipeline.

This module is the composition root: it is the only place that assembles the
concrete infrastructure adapters (SQLite repositories, Indian Express RSS
source, Trafilatura extractor, OpenAI generator) into a
`ProcessNewsFeedService`. It never runs Alembic migrations itself - the
schema must already exist (`uv run alembic upgrade head`).

Commands:

    uv run python -m app.cli process-feed
    uv run python -m app.cli process-feed --retry-failed
    uv run python -m app.cli retry-article <ARTICLE_UUID>

Exit codes: 0 for a completed command with no Article-level failures; 1 for a
configuration failure, discovery failure, lookup failure, database failure,
or one or more Article-level failures.
"""

import argparse
import sys
from uuid import UUID

from app.application.processing import (
    ArticleNotFoundError,
    ArticleProcessingResult,
    ProcessingSummary,
    ProcessNewsFeedService,
)
from app.application.repositories import RepositoryError
from app.application.sources import ArticleSourceError
from app.infrastructure.config import Settings
from app.infrastructure.database import create_engine_from_url, create_session_factory
from app.infrastructure.logging import configure_logging
from app.infrastructure.openai_generator import OpenAILearningNoteGenerator
from app.infrastructure.rss_source import IndianExpressRSSSource
from app.infrastructure.sqlite_repositories import (
    SQLiteArticleRepository,
    SQLiteLearningNoteRepository,
)
from app.infrastructure.trafilatura_extractor import TrafilaturaArticleExtractor

_DB_NOT_READY_MESSAGE = (
    "Database unavailable or schema not initialized. Verify DATABASE_URL and run:\n"
    "  uv run alembic upgrade head"
)


class CompositionError(Exception):
    """Raised when the CLI cannot assemble a working processing service.

    Its message is always safe to print: configuration problems name only the
    missing variable, and database problems use the fixed readiness message -
    never raw driver or SQLAlchemy detail.
    """


def _require_setting(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise CompositionError(
            f"{name} is required. Set it in the environment or in the .env file."
        )
    return value


def _compose_service(settings: Settings) -> ProcessNewsFeedService:
    """Assemble the concrete processing service, verifying prerequisites.

    Raises:
        CompositionError: if required configuration is missing, or the
            database is unavailable or not yet migrated.
    """
    api_key = _require_setting(settings.openai_api_key, "OPENAI_API_KEY")
    model_name = _require_setting(settings.llm_model, "LLM_MODEL")

    engine = create_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)
    article_repository = SQLiteArticleRepository(session_factory)
    learning_note_repository = SQLiteLearningNoteRepository(session_factory)
    try:
        article_repository.list_recent(limit=1)
    except RepositoryError as exc:
        raise CompositionError(_DB_NOT_READY_MESSAGE) from exc

    return ProcessNewsFeedService(
        article_source=IndianExpressRSSSource(settings.rss_url),
        article_extractor=TrafilaturaArticleExtractor(),
        article_repository=article_repository,
        learning_note_repository=learning_note_repository,
        learning_note_generator=OpenAILearningNoteGenerator(
            model_name=model_name, api_key=api_key
        ),
    )


def _print_summary(summary: ProcessingSummary) -> None:
    print(f"total discovered:       {summary.total_discovered}")
    print(f"new articles:           {summary.new_articles}")
    print(f"duplicates skipped:     {summary.duplicates_skipped}")
    print(f"successfully extracted: {summary.successfully_extracted}")
    print(f"successfully analyzed:  {summary.successfully_analyzed}")
    print(f"reconciled:             {summary.reconciled}")
    print(f"failed:                 {summary.failed}")
    if summary.failure_details:
        print("failures:")
        for detail in summary.failure_details:
            identity = str(detail.article_id) if detail.article_id else (detail.url or "-")
            print(f"  - [{detail.stage}/{detail.reason_category}] {detail.message} ({identity})")


def _print_retry_result(result: ArticleProcessingResult) -> None:
    if result.analyzed:
        print("Article analyzed successfully.")
    elif result.reconciled:
        print("Article reconciled: existing Learning Note reused; status corrected to analyzed.")
    elif result.skipped:
        print("Article skipped: already fully processed.")
    elif result.failure is not None:
        detail = result.failure
        print(
            f"Retry failed: [{detail.stage}/{detail.reason_category}] {detail.message}",
            file=sys.stderr,
        )


def _run_process_feed(service: ProcessNewsFeedService, *, retry_failed: bool) -> int:
    try:
        summary = service.process(retry_failed=retry_failed)
    except ArticleSourceError as exc:
        print(f"Feed discovery failed: {exc}", file=sys.stderr)
        return 1
    _print_summary(summary)
    return 0 if summary.failed == 0 else 1


def _run_retry_article(service: ProcessNewsFeedService, article_id: UUID) -> int:
    try:
        result = service.retry_article(article_id)
    except ArticleNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except RepositoryError:
        print(_DB_NOT_READY_MESSAGE, file=sys.stderr)
        return 1
    _print_retry_result(result)
    return 0 if result.failure is None else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="currentmind",
        description="Process UPSC current-affairs articles into Learning Notes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    feed = subparsers.add_parser(
        "process-feed",
        help="Discover, extract, analyze, and persist articles from the RSS feed.",
    )
    feed.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Also retry failed articles that are rediscovered in the current feed. "
            "Use retry-article for a failed article no longer present in the feed."
        ),
    )

    retry = subparsers.add_parser(
        "retry-article",
        help=(
            "Retry one persisted article by UUID, regardless of whether it still "
            "appears in the RSS feed. Never calls feed discovery."
        ),
    )
    retry.add_argument("article_id", help="UUID of the persisted article to retry")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    args = build_parser().parse_args(argv)

    article_id: UUID | None = None
    if args.command == "retry-article":
        try:
            article_id = UUID(args.article_id)
        except ValueError:
            print(f"Invalid article id: {args.article_id!r} is not a valid UUID.", file=sys.stderr)
            return 1

    settings = Settings()
    configure_logging(settings.log_level)

    try:
        service = _compose_service(settings)
    except CompositionError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "process-feed":
        return _run_process_feed(service, retry_failed=args.retry_failed)
    assert article_id is not None
    return _run_retry_article(service, article_id)


if __name__ == "__main__":
    raise SystemExit(main())

"""Contract, constraint, and rollback tests for `SQLiteArticleRepository`.

Every test runs against a migration-created temporary SQLite database (see
`conftest.py`); none touch the real development database, RSS, or a live
article page.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.application.repositories import (
    ArticleRepository,
    DuplicateArticleError,
    RepositoryError,
)
from app.domain.article import Article
from app.domain.enums import ProcessingStatus
from app.infrastructure.database import create_engine_from_url
from app.infrastructure.sqlite_repositories import SQLiteArticleRepository
from tests.infrastructure.factories import make_article


def test_add_and_get_by_id(article_repository: ArticleRepository) -> None:
    article = make_article()
    article_repository.add(article)

    fetched = article_repository.get_by_id(article.id)

    assert fetched == article


def test_get_by_id_missing_returns_none(article_repository: ArticleRepository) -> None:
    assert article_repository.get_by_id(uuid4()) is None


def test_get_by_url(article_repository: ArticleRepository) -> None:
    article = make_article(url="https://indianexpress.com/unique-url")
    article_repository.add(article)

    fetched = article_repository.get_by_url("https://indianexpress.com/unique-url")

    assert fetched == article


def test_get_by_url_missing_returns_none(article_repository: ArticleRepository) -> None:
    assert article_repository.get_by_url("https://indianexpress.com/nope") is None


def test_get_by_source_external_id(article_repository: ArticleRepository) -> None:
    article = make_article(source="indian_express", external_id="ext-99")
    article_repository.add(article)

    fetched = article_repository.get_by_source_external_id("indian_express", "ext-99")

    assert fetched == article


def test_get_by_source_external_id_missing_returns_none(
    article_repository: ArticleRepository,
) -> None:
    assert article_repository.get_by_source_external_id("indian_express", "nope") is None


def test_multiple_articles_with_missing_external_id_allowed_when_urls_differ(
    article_repository: ArticleRepository,
) -> None:
    first = make_article(external_id=None, url="https://indianexpress.com/a")
    second = make_article(external_id=None, url="https://indianexpress.com/b")

    article_repository.add(first)
    article_repository.add(second)

    assert article_repository.get_by_id(first.id) == first
    assert article_repository.get_by_id(second.id) == second


def test_duplicate_url_rejected(article_repository: ArticleRepository) -> None:
    first = make_article(url="https://indianexpress.com/same", external_id="ext-1")
    second = make_article(url="https://indianexpress.com/same", external_id="ext-2")
    article_repository.add(first)

    with pytest.raises(DuplicateArticleError):
        article_repository.add(second)


def test_duplicate_source_external_id_rejected(article_repository: ArticleRepository) -> None:
    first = make_article(source="indian_express", external_id="ext-1", url="https://x.com/a")
    second = make_article(source="indian_express", external_id="ext-1", url="https://x.com/b")
    article_repository.add(first)

    with pytest.raises(DuplicateArticleError):
        article_repository.add(second)


def test_same_url_with_changed_external_id_rejected(article_repository: ArticleRepository) -> None:
    first = make_article(url="https://indianexpress.com/same", external_id="ext-1")
    second = make_article(url="https://indianexpress.com/same", external_id="ext-2")
    article_repository.add(first)

    with pytest.raises(DuplicateArticleError):
        article_repository.add(second)


def test_same_external_id_with_changed_url_rejected(article_repository: ArticleRepository) -> None:
    first = make_article(source="indian_express", external_id="ext-1", url="https://x.com/a")
    second = make_article(source="indian_express", external_id="ext-1", url="https://x.com/changed")
    article_repository.add(first)

    with pytest.raises(DuplicateArticleError):
        article_repository.add(second)


def test_duplicate_failure_rolls_back_and_repository_remains_usable(
    article_repository: ArticleRepository,
) -> None:
    first = make_article(url="https://indianexpress.com/same")
    article_repository.add(first)

    duplicate = make_article(url="https://indianexpress.com/same", external_id="different")
    with pytest.raises(DuplicateArticleError):
        article_repository.add(duplicate)

    # the repository must remain fully usable after a failed add()
    another = make_article(url="https://indianexpress.com/another", external_id="ext-another")
    article_repository.add(another)
    assert article_repository.get_by_id(another.id) == another
    # and the failed duplicate must not have been partially persisted
    assert article_repository.get_by_id(duplicate.id) is None


def test_update_persists_changes(article_repository: ArticleRepository) -> None:
    article = make_article(title="Old Title")
    article_repository.add(article)

    changed_kwargs = article.model_dump()
    changed_kwargs["title"] = "New Title"
    changed_kwargs["processing_status"] = ProcessingStatus.FAILED
    changed_kwargs["failure_reason"] = "Extraction failed."
    changed = Article(**changed_kwargs)
    article_repository.update(changed)

    fetched = article_repository.get_by_id(article.id)
    assert fetched is not None
    assert fetched.title == "New Title"
    assert fetched.processing_status == ProcessingStatus.FAILED
    assert fetched.failure_reason == "Extraction failed."


def test_failure_reason_round_trips_through_persistence(
    article_repository: ArticleRepository,
) -> None:
    article = make_article(
        processing_status=ProcessingStatus.FAILED, failure_reason="Network timeout."
    )
    article_repository.add(article)

    fetched = article_repository.get_by_id(article.id)

    assert fetched is not None
    assert fetched.failure_reason == "Network timeout."
    assert fetched.processing_status == ProcessingStatus.FAILED


def test_update_nonexistent_article_raises(article_repository: ArticleRepository) -> None:
    ghost = make_article()

    with pytest.raises(RepositoryError):
        article_repository.update(ghost)


def test_update_does_not_insert_a_new_row(article_repository: ArticleRepository) -> None:
    article = make_article()
    article_repository.add(article)

    changed_kwargs = article.model_dump()
    changed_kwargs["title"] = "Updated"
    article_repository.update(Article(**changed_kwargs))

    recent = article_repository.list_recent(limit=10)
    assert len(recent) == 1
    assert recent[0].title == "Updated"


def test_list_recent_orders_by_created_at_desc_with_id_tiebreak(
    article_repository: ArticleRepository,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    older = make_article(url="https://x.com/older", external_id="ext-older")
    older = Article(**{**older.model_dump(), "created_at": base, "updated_at": base})
    newer = make_article(url="https://x.com/newer", external_id="ext-newer")
    newer = Article(
        **{
            **newer.model_dump(),
            "created_at": base + timedelta(hours=1),
            "updated_at": base + timedelta(hours=1),
        }
    )

    article_repository.add(older)
    article_repository.add(newer)

    recent = article_repository.list_recent(limit=10)

    assert [a.id for a in recent] == [newer.id, older.id]


def test_list_recent_respects_limit(article_repository: ArticleRepository) -> None:
    for i in range(5):
        article_repository.add(make_article(url=f"https://x.com/{i}", external_id=f"ext-{i}"))

    recent = article_repository.list_recent(limit=2)

    assert len(recent) == 2


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_list_recent_rejects_non_positive_limit(
    article_repository: ArticleRepository, limit: int
) -> None:
    with pytest.raises(ValueError):
        article_repository.list_recent(limit=limit)


def test_list_recent_rejects_boolean_limit(article_repository: ArticleRepository) -> None:
    with pytest.raises(ValueError):
        article_repository.list_recent(limit=True)


def test_list_recent_rejects_non_integer_limit(article_repository: ArticleRepository) -> None:
    with pytest.raises(ValueError):
        article_repository.list_recent(limit="20")  # type: ignore[arg-type]


def test_get_with_learning_note_returns_none_without_note(
    article_repository: ArticleRepository,
) -> None:
    article = make_article()
    article_repository.add(article)

    result = article_repository.get_with_learning_note(article.id)

    assert result is not None
    assert result.article == article
    assert result.learning_note is None


def test_get_with_learning_note_missing_article_returns_none(
    article_repository: ArticleRepository,
) -> None:
    assert article_repository.get_with_learning_note(uuid4()) is None


def test_persistence_across_engine_disposal_and_reopen(migrated_db_url: str) -> None:
    article = make_article()

    write_engine = create_engine_from_url(migrated_db_url)
    write_session_factory = sessionmaker(bind=write_engine)
    SQLiteArticleRepository(write_session_factory).add(article)
    write_engine.dispose()

    read_engine = create_engine_from_url(migrated_db_url)
    read_session_factory: sessionmaker[Session] = sessionmaker(bind=read_engine)
    fetched = SQLiteArticleRepository(read_session_factory).get_by_id(article.id)
    read_engine.dispose()

    assert fetched == article

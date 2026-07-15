"""Error-translation edge cases: unrecognized integrity failures, a locked
database, and confirmation that article/note content never leaks into
exception messages.

SQLite error-message inspection (`_translate_article_integrity_error` /
`_translate_learning_note_integrity_error` in
`app.infrastructure.sqlite_repositories`) is adapter-specific: it depends on
SQLite's own `IntegrityError` message wording and is exercised end-to-end by
the duplicate/foreign-key tests in `test_sqlite_article_repository.py` and
`test_sqlite_learning_note_repository.py`. This file covers the two paths
those integration tests cannot reach through the public repository API with
valid domain objects:

* an *unrecognized* integrity failure, which cannot be triggered through
  `add()`/`update()` with a valid `Article` (`article_to_row` always produces
  a value SQLAlchemy's own `Enum` type accepts, so the only constraints ever
  actually violated through the public API are the ones already recognized);
  covered instead as a focused unit test of the translation function itself.
* a locked/unavailable database, triggered deterministically with a second
  raw `sqlite3` connection holding an exclusive lock (`timeout=0` so the
  attempt fails immediately rather than blocking).
"""

import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.repositories import ArticleRepository, RepositoryError
from app.infrastructure.database import create_engine_from_url, create_session_factory
from app.infrastructure.sqlite_repositories import (
    SQLiteArticleRepository,
    _translate_article_integrity_error,
    _translate_learning_note_integrity_error,
)
from tests.infrastructure.factories import make_article, make_learning_note


def _fake_integrity_error(message: str) -> IntegrityError:
    return IntegrityError(statement="INSERT ...", params=(), orig=Exception(message))


def test_unrecognized_article_integrity_error_becomes_generic_repository_error() -> None:
    article = make_article()
    exc = _fake_integrity_error("CHECK constraint failed: ck_articles_processing_status")

    translated = _translate_article_integrity_error(article, exc)

    # exactly RepositoryError, not one of its more specific duplicate subclasses
    assert type(translated) is RepositoryError


def test_unrecognized_learning_note_integrity_error_becomes_generic_repository_error() -> None:
    note = make_learning_note()
    exc = _fake_integrity_error("some unrelated constraint failure")

    translated = _translate_learning_note_integrity_error(note, exc)

    assert type(translated) is RepositoryError


def test_locked_database_raises_repository_error(migrated_db_url: str) -> None:
    db_path = migrated_db_url.removeprefix("sqlite:///")
    locker = sqlite3.connect(db_path)
    locker.execute("BEGIN EXCLUSIVE")
    try:
        engine = create_engine_from_url(f"{migrated_db_url}?timeout=0")
        repository = SQLiteArticleRepository(create_session_factory(engine))

        with pytest.raises(RepositoryError):
            repository.add(make_article())
    finally:
        locker.close()


def test_generic_locked_database_error_redacts_article_parameters(
    migrated_db_url: str,
) -> None:
    """A locked-database `OperationalError` goes through the generic
    `SQLAlchemyError` fallback branch, not the duplicate translator (which
    builds its own message and never interpolates the SQLAlchemy exception at
    all). This test proves specifically that `hide_parameters=True` on the
    engine - not the translator's own message construction - is what keeps
    bound `Article` content out of the resulting `RepositoryError`, by
    asserting the sensitive text is absent even from the chained SQLAlchemy
    cause's own string representation.
    """
    sensitive_text = "UNMISTAKABLE-SENSITIVE-ARTICLE-BODY-" + "X" * 200
    article = make_article(raw_text=sensitive_text)

    db_path = migrated_db_url.removeprefix("sqlite:///")
    locker = sqlite3.connect(db_path)
    locker.execute("BEGIN EXCLUSIVE")
    engine = create_engine_from_url(f"{migrated_db_url}?timeout=0")
    try:
        repository = SQLiteArticleRepository(create_session_factory(engine))
        with pytest.raises(RepositoryError) as excinfo:
            repository.add(article)
    finally:
        locker.close()
        engine.dispose()

    error = excinfo.value
    assert type(error) is RepositoryError
    assert sensitive_text not in str(error)
    assert sensitive_text not in repr(error)
    # a chained SQLAlchemy cause exists (exception chaining preserved: `raise
    # ... from exc`), and the sensitive text is absent even from *its* own
    # string representation - proving `hide_parameters=True` is doing the
    # redaction, not just the outer RepositoryError's message wording.
    assert error.__cause__ is not None
    assert isinstance(error.__cause__, SQLAlchemyError)
    assert sensitive_text not in str(error.__cause__)


def test_duplicate_error_message_does_not_include_article_body(
    article_repository: ArticleRepository,
) -> None:
    sensitive_text = "SENSITIVE ARTICLE BODY " * 50
    first = make_article(url="https://indianexpress.com/same", raw_text=sensitive_text)
    article_repository.add(first)

    duplicate = make_article(
        url="https://indianexpress.com/same",
        external_id="different",
        raw_text=sensitive_text,
    )
    with pytest.raises(RepositoryError) as excinfo:
        article_repository.add(duplicate)

    assert sensitive_text not in str(excinfo.value)
    assert sensitive_text not in repr(excinfo.value)

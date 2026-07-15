"""Shared fixtures for infrastructure persistence tests.

Every test gets its own temporary, migration-created SQLite database under
pytest's `tmp_path` - never the real development database at
`database/currentmind.db`.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.repositories import ArticleRepository, LearningNoteRepository
from app.infrastructure.database import create_engine_from_url, create_session_factory
from app.infrastructure.sqlite_repositories import (
    SQLiteArticleRepository,
    SQLiteLearningNoteRepository,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


def alembic_config_for(database_url: str) -> Config:
    """Build an Alembic Config targeting `database_url`.

    Always used with a `tmp_path`-derived URL in tests, so the real
    development database is never opened, migrated, or modified by the test
    suite.
    """
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """A SQLite URL for an isolated, not-yet-migrated temporary database file."""
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def migrated_db_url(db_url: str) -> str:
    """Apply the Alembic migration to an isolated temporary database and return its URL."""
    command.upgrade(alembic_config_for(db_url), "head")
    return db_url


@pytest.fixture
def engine(migrated_db_url: str) -> Iterator[Engine]:
    db_engine = create_engine_from_url(migrated_db_url)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def article_repository(session_factory: sessionmaker[Session]) -> ArticleRepository:
    return SQLiteArticleRepository(session_factory)


@pytest.fixture
def learning_note_repository(session_factory: sessionmaker[Session]) -> LearningNoteRepository:
    return SQLiteLearningNoteRepository(session_factory)

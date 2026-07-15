"""Database engine and session lifecycle for SQLite persistence.

This module only builds engines and session factories from an explicitly
supplied database URL - it never reads `Settings` itself, so every caller
(tests today, application startup later) controls exactly which database is
used. No table creation or migration runs on import; schema is owned by
Alembic (see `migrations/`), not by this module.
"""

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(database_url: str) -> Engine:
    """Build a SQLAlchemy engine for `database_url`.

    Registers a `PRAGMA foreign_keys=ON` connect listener so SQLite enforces
    foreign key constraints - including `ON DELETE CASCADE` - on every
    connection, since SQLite disables enforcement by default. Uses
    `hide_parameters=True` so a raised `IntegrityError`/`OperationalError`
    never includes bound parameter values (article or Learning Note content)
    in its string representation - only the SQL statement shape is kept for
    diagnostics.
    """
    engine = create_engine(database_url, hide_parameters=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to `engine`."""
    return sessionmaker(bind=engine)

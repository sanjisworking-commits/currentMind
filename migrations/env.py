from logging.config import fileConfig

from alembic import context

from app.infrastructure.config import get_settings
from app.infrastructure.database import create_engine_from_url
from app.infrastructure.orm_models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# `disable_existing_loggers=False` is required: the default (True) silently
# disables every logger already configured before this module runs -
# including the application's own module loggers and pytest's `caplog`
# handler, since Alembic commands (and this env.py) are invoked from within
# the same test process as the rest of the suite.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Sprint 4 schema: articles and learning_notes.
target_metadata = Base.metadata


def _resolve_url() -> str:
    """Resolve the database URL to migrate.

    Prefers an explicit `sqlalchemy.url` set on the Alembic Config (tests set
    this to an isolated temporary database before invoking a command);
    otherwise falls back to `Settings.database_url`, so `alembic upgrade head`
    run from the command line targets the same database as the application.
    """
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    Uses `create_engine_from_url` (the same helper the application and tests
    use) so foreign-key enforcement is registered as a connect-time event
    rather than executed on the connection here directly - executing a raw
    statement on the connection before handing it to `context.configure`
    starts an implicit transaction that interferes with Alembic's own
    version-table commit on SQLite.
    """
    connectable = create_engine_from_url(_resolve_url())

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

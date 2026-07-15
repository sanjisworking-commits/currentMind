"""Migration tests: the Alembic-created Sprint 4 schema on isolated temp databases.

Every test builds its Alembic Config against a `tmp_path`-derived SQLite URL
(via the `alembic_config_for`/`db_url` helpers in `conftest.py`) and never
touches the real development database.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from tests.infrastructure.conftest import alembic_config_for


def test_upgrade_head_creates_expected_tables(db_url: str) -> None:
    command.upgrade(alembic_config_for(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {"alembic_version", "articles", "learning_notes"}


def test_upgrade_head_creates_articles_constraints(db_url: str) -> None:
    command.upgrade(alembic_config_for(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)

    pk = inspector.get_pk_constraint("articles")
    assert pk["name"] == "pk_articles"
    assert pk["constrained_columns"] == ["id"]

    unique_names = {uq["name"] for uq in inspector.get_unique_constraints("articles")}
    assert unique_names == {"uq_articles_url", "uq_articles_source_external_id"}

    index_names = {ix["name"] for ix in inspector.get_indexes("articles")}
    assert "ix_articles_created_at" in index_names

    check_names = {ck["name"] for ck in inspector.get_check_constraints("articles")}
    assert "ck_articles_processing_status" in check_names


def test_upgrade_head_creates_learning_notes_constraints(db_url: str) -> None:
    command.upgrade(alembic_config_for(db_url), "head")
    engine = create_engine(db_url)
    inspector = inspect(engine)

    pk = inspector.get_pk_constraint("learning_notes")
    assert pk["name"] == "pk_learning_notes"
    assert pk["constrained_columns"] == ["id"]

    unique_names = {uq["name"] for uq in inspector.get_unique_constraints("learning_notes")}
    assert "uq_learning_notes_article_id" in unique_names

    foreign_keys = inspector.get_foreign_keys("learning_notes")
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk["name"] == "fk_learning_notes_article_id_articles"
    assert fk["referred_table"] == "articles"
    assert fk["constrained_columns"] == ["article_id"]
    assert fk["referred_columns"] == ["id"]
    assert fk["options"].get("ondelete") == "CASCADE"


def test_downgrade_base_removes_sprint4_tables(db_url: str) -> None:
    config = alembic_config_for(db_url)
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    assert "articles" not in inspector.get_table_names()
    assert "learning_notes" not in inspector.get_table_names()


def test_reupgrade_after_downgrade_succeeds(db_url: str) -> None:
    config = alembic_config_for(db_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    command.upgrade(config, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)
    assert {"articles", "learning_notes"}.issubset(inspector.get_table_names())


def test_alembic_config_never_targets_real_development_database(db_url: str) -> None:
    config: Config = alembic_config_for(db_url)
    assert config.get_main_option("sqlalchemy.url") == db_url
    assert "database/currentmind.db" not in db_url

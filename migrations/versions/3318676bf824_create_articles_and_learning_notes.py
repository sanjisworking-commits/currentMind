"""create articles and learning notes

Revision ID: 3318676bf824
Revises:
Create Date: 2026-07-15 07:32:19.805506

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3318676bf824"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the `articles` and `learning_notes` tables."""
    op.create_table(
        "articles",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column(
            "processing_status",
            sa.Enum(
                "discovered",
                "extracted",
                "analysis_pending",
                "analyzed",
                "failed",
                name="ck_articles_processing_status",
                native_enum=False,
                create_constraint=True,
                validate_strings=True,
            ),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_articles"),
        sa.UniqueConstraint("url", name="uq_articles_url"),
        sa.UniqueConstraint("source", "external_id", name="uq_articles_source_external_id"),
    )
    op.create_index("ix_articles_created_at", "articles", ["created_at"])

    op.create_table(
        "learning_notes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("article_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("gs_papers", sa.JSON(), nullable=False),
        sa.Column("subjects", sa.JSON(), nullable=False),
        sa.Column("syllabus_topics", sa.JSON(), nullable=False),
        sa.Column("static_concepts", sa.JSON(), nullable=False),
        sa.Column("constitutional_linkages", sa.JSON(), nullable=False),
        sa.Column("government_schemes", sa.JSON(), nullable=False),
        sa.Column("reports_and_committees", sa.JSON(), nullable=False),
        sa.Column("international_dimensions", sa.JSON(), nullable=False),
        sa.Column("important_facts", sa.JSON(), nullable=False),
        sa.Column("prelims_questions", sa.JSON(), nullable=False),
        sa.Column("mains_questions", sa.JSON(), nullable=False),
        sa.Column("revision_note", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_learning_notes"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_learning_notes_article_id_articles",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("article_id", name="uq_learning_notes_article_id"),
    )


def downgrade() -> None:
    """Drop the `learning_notes` and `articles` tables.

    `learning_notes` is dropped first since it holds the foreign key to
    `articles`.
    """
    op.drop_table("learning_notes")
    op.drop_index("ix_articles_created_at", table_name="articles")
    op.drop_table("articles")

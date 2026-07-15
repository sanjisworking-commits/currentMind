"""SQLAlchemy ORM models for the `articles` and `learning_notes` tables.

These classes are infrastructure-only: they describe database structure, not
business rules, and must never be imported outside `app/infrastructure/`. See
`app/infrastructure/mappers.py` for the explicit functions that translate
between these rows and the domain models in `app/domain/`.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.enums import ProcessingStatus


class Base(DeclarativeBase):
    """Declarative base shared by all infrastructure ORM models."""


class ArticleRow(Base):
    """ORM row for a persisted Article."""

    __tablename__ = "articles"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_articles"),
        UniqueConstraint("url", name="uq_articles_url"),
        UniqueConstraint("source", "external_id", name="uq_articles_source_external_id"),
        Index("ix_articles_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(SAUuid(as_uuid=True))
    source: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    categories: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(
            ProcessingStatus,
            name="ck_articles_processing_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LearningNoteRow(Base):
    """ORM row for a persisted Learning Note.

    Every structured list field (including the nested Prelims/Mains question
    lists) is stored in its own JSON column rather than as one opaque blob, so
    each field remains independently readable and self-describing in the schema.
    """

    __tablename__ = "learning_notes"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_learning_notes"),
        ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_learning_notes_article_id_articles",
            ondelete="CASCADE",
        ),
        UniqueConstraint("article_id", name="uq_learning_notes_article_id"),
    )

    id: Mapped[UUID] = mapped_column(SAUuid(as_uuid=True))
    article_id: Mapped[UUID] = mapped_column(SAUuid(as_uuid=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    gs_papers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    subjects: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    syllabus_topics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    static_concepts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    constitutional_linkages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    government_schemes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reports_and_committees: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    international_dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    important_facts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prelims_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    mains_questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    revision_note: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

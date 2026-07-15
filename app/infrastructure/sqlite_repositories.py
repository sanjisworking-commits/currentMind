"""Concrete SQLite/SQLAlchemy implementations of the application repository ports.

`SQLiteArticleRepository` and `SQLiteLearningNoteRepository` implement
`app.application.repositories.ArticleRepository` and `LearningNoteRepository`
structurally (no inheritance), matching the pattern already used for
`IndianExpressRSSSource` and `TrafilaturaArticleExtractor`. Each public method
opens its own session and owns its own transaction - there is no shared
long-lived session and no Unit of Work.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.application.repositories import (
    ArticleWithLearningNote,
    DuplicateArticleError,
    DuplicateLearningNoteError,
    RelatedArticleNotFoundError,
    RepositoryError,
    validate_positive_limit,
)
from app.domain.article import Article
from app.domain.learning_note import LearningNote
from app.infrastructure.mappers import (
    article_to_row,
    learning_note_to_row,
    row_to_article,
    row_to_learning_note,
    update_row_from_article,
)
from app.infrastructure.orm_models import ArticleRow, LearningNoteRow


def _translate_article_integrity_error(article: Article, exc: IntegrityError) -> RepositoryError:
    message = str(exc.orig)
    if "articles.url" in message:
        return DuplicateArticleError(f"an article with url {article.url!r} already exists")
    if "articles.source" in message and "articles.external_id" in message:
        return DuplicateArticleError(
            f"an article with source {article.source!r} and external_id "
            f"{article.external_id!r} already exists"
        )
    return RepositoryError(f"unexpected integrity error while persisting an article: {message}")


def _translate_learning_note_integrity_error(
    note: LearningNote, exc: IntegrityError
) -> RepositoryError:
    message = str(exc.orig)
    if "learning_notes.article_id" in message:
        return DuplicateLearningNoteError(
            f"a learning note for article {note.article_id} already exists"
        )
    if "FOREIGN KEY constraint failed" in message:
        return RelatedArticleNotFoundError(f"no article with id {note.article_id} exists")
    return RepositoryError(
        f"unexpected integrity error while persisting a learning note: {message}"
    )


class SQLiteArticleRepository:
    """SQLite/SQLAlchemy implementation of `ArticleRepository`."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, article: Article) -> None:
        row = article_to_row(article)
        try:
            with self._session_factory.begin() as session:
                session.add(row)
        except IntegrityError as exc:
            raise _translate_article_integrity_error(article, exc) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while adding an article: {exc}") from exc

    def get_by_id(self, article_id: UUID) -> Article | None:
        try:
            with self._session_factory() as session:
                row = session.get(ArticleRow, article_id)
                return row_to_article(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while reading an article: {exc}") from exc

    def get_by_url(self, url: str) -> Article | None:
        try:
            with self._session_factory() as session:
                row = session.execute(
                    select(ArticleRow).where(ArticleRow.url == url)
                ).scalar_one_or_none()
                return row_to_article(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while reading an article: {exc}") from exc

    def get_by_source_external_id(self, source: str, external_id: str) -> Article | None:
        try:
            with self._session_factory() as session:
                row = session.execute(
                    select(ArticleRow).where(
                        ArticleRow.source == source, ArticleRow.external_id == external_id
                    )
                ).scalar_one_or_none()
                return row_to_article(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while reading an article: {exc}") from exc

    def list_recent(self, limit: int = 20) -> list[Article]:
        validate_positive_limit(limit)
        try:
            with self._session_factory() as session:
                rows = (
                    session.execute(
                        select(ArticleRow)
                        .order_by(ArticleRow.created_at.desc(), ArticleRow.id.desc())
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )
                return [row_to_article(row) for row in rows]
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while listing recent articles: {exc}") from exc

    def update(self, article: Article) -> None:
        try:
            with self._session_factory.begin() as session:
                row = session.get(ArticleRow, article.id)
                if row is None:
                    raise RepositoryError(f"cannot update: no article with id {article.id} exists")
                update_row_from_article(row, article)
        except IntegrityError as exc:
            raise _translate_article_integrity_error(article, exc) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while updating an article: {exc}") from exc

    def get_with_learning_note(self, article_id: UUID) -> ArticleWithLearningNote | None:
        try:
            with self._session_factory() as session:
                article_row = session.get(ArticleRow, article_id)
                if article_row is None:
                    return None
                note_row = session.execute(
                    select(LearningNoteRow).where(LearningNoteRow.article_id == article_id)
                ).scalar_one_or_none()
                return ArticleWithLearningNote(
                    article=row_to_article(article_row),
                    learning_note=(
                        row_to_learning_note(note_row) if note_row is not None else None
                    ),
                )
        except SQLAlchemyError as exc:
            raise RepositoryError(
                f"database error while reading an article with its learning note: {exc}"
            ) from exc


class SQLiteLearningNoteRepository:
    """SQLite/SQLAlchemy implementation of `LearningNoteRepository`."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, note: LearningNote) -> None:
        row = learning_note_to_row(note)
        try:
            with self._session_factory.begin() as session:
                session.add(row)
        except IntegrityError as exc:
            raise _translate_learning_note_integrity_error(note, exc) from exc
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while adding a learning note: {exc}") from exc

    def get_by_article_id(self, article_id: UUID) -> LearningNote | None:
        try:
            with self._session_factory() as session:
                row = session.execute(
                    select(LearningNoteRow).where(LearningNoteRow.article_id == article_id)
                ).scalar_one_or_none()
                return row_to_learning_note(row) if row is not None else None
        except SQLAlchemyError as exc:
            raise RepositoryError(f"database error while reading a learning note: {exc}") from exc

"""Application-facing contracts for persisting and retrieving Articles and Learning Notes.

Concrete infrastructure adapters (for example a SQLite/SQLAlchemy implementation)
implement `ArticleRepository` and `LearningNoteRepository`. Application-layer
workflows depend on these ports and on the error types defined here, never on a
specific infrastructure implementation, so the persistence technology can be
replaced later without touching orchestration code.

Repositories persist and retrieve valid domain state; they do not decide
business workflow transitions (for example, which `ProcessingStatus` an
`Article` should move to after an extraction attempt). That decision belongs to
a future orchestration service.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.domain.article import Article
from app.domain.learning_note import LearningNote


@dataclass(frozen=True, slots=True)
class ArticleWithLearningNote:
    """An Article paired with its Learning Note, if one has been generated."""

    article: Article
    learning_note: LearningNote | None


class RepositoryError(Exception):
    """Base error for persistence failures that must not be handled silently."""


class DuplicateArticleError(RepositoryError):
    """Raised when an Article violates a unique-identity constraint on insert."""


class DuplicateLearningNoteError(RepositoryError):
    """Raised when a second Learning Note is saved for the same Article."""


class RelatedArticleNotFoundError(RepositoryError):
    """Raised when a Learning Note references an Article that does not exist."""


def validate_positive_limit(limit: int) -> None:
    """Reject a `list_recent` limit that is not a strict positive integer.

    Booleans are rejected even though `bool` is a subclass of `int` in Python,
    since a boolean limit is never a meaningful value here.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if limit <= 0:
        raise ValueError("limit must be a strict positive integer")


class ArticleRepository(Protocol):
    """Persists and retrieves Articles."""

    def add(self, article: Article) -> None:
        """Insert a new Article.

        Raises:
            DuplicateArticleError: if `article.url`, or the combination of
                `article.source` and `article.external_id`, already exists.
        """
        ...

    def get_by_id(self, article_id: UUID) -> Article | None:
        """Return the Article with the given id, or None if it does not exist."""
        ...

    def get_by_url(self, url: str) -> Article | None:
        """Return the Article with the given canonical URL, or None."""
        ...

    def get_by_source_external_id(self, source: str, external_id: str) -> Article | None:
        """Return the Article with the given source and external id, or None."""
        ...

    def list_recent(self, limit: int = 20) -> list[Article]:
        """Return up to `limit` Articles ordered by `created_at` descending,
        with `id` descending as a stable tie-breaker.

        Raises:
            ValueError: if `limit` is not a strict positive integer.
        """
        ...

    def update(self, article: Article) -> None:
        """Persist the current state of an existing Article.

        Raises:
            RepositoryError: if no Article with `article.id` exists.
        """
        ...

    def get_with_learning_note(self, article_id: UUID) -> ArticleWithLearningNote | None:
        """Return the Article and its Learning Note (if any), or None if the
        Article does not exist.
        """
        ...


class LearningNoteRepository(Protocol):
    """Persists and retrieves Learning Notes."""

    def add(self, note: LearningNote) -> None:
        """Insert a new Learning Note.

        Raises:
            DuplicateLearningNoteError: if a Learning Note already exists for
                `note.article_id`.
            RelatedArticleNotFoundError: if no Article with `note.article_id`
                exists.
        """
        ...

    def get_by_article_id(self, article_id: UUID) -> LearningNote | None:
        """Return the Learning Note for the given Article id, or None."""
        ...

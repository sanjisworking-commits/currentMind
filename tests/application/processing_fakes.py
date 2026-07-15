"""Handwritten fakes for `ProcessNewsFeedService` tests.

Each fake implements the corresponding application Protocol structurally,
records the calls it receives, and returns or raises scripted values. None of
them duplicate any pipeline logic: the in-memory repositories emulate only
the persistence contract (storage, identity uniqueness, and error
translation), never workflow decisions.
"""

from collections.abc import Callable
from uuid import UUID

from app.application.repositories import (
    ArticleWithLearningNote,
    DuplicateArticleError,
    DuplicateLearningNoteError,
    RelatedArticleNotFoundError,
    RepositoryError,
    validate_positive_limit,
)
from app.domain.article import Article, ArticleCandidate
from app.domain.extraction import ExtractedArticle
from app.domain.learning_note import LearningNote


class FakeArticleSource:
    """Returns a scripted candidate list, or raises a scripted error."""

    def __init__(
        self,
        candidates: list[ArticleCandidate] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._candidates = candidates if candidates is not None else []
        self._error = error
        self.calls = 0

    def discover_articles(self) -> list[ArticleCandidate]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._candidates)


class FakeArticleExtractor:
    """Returns scripted `ExtractedArticle` results keyed by requested URL."""

    def __init__(self, results: dict[str, ExtractedArticle] | None = None) -> None:
        self.results = results if results is not None else {}
        self.calls: list[str] = []

    def extract(self, url: str) -> ExtractedArticle:
        self.calls.append(url)
        try:
            return self.results[url]
        except KeyError:
            raise AssertionError(f"no scripted extraction result for {url!r}") from None


class HostileExtractor:
    """Raises an unexpected exception, for defensive-boundary tests only."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls: list[str] = []

    def extract(self, url: str) -> ExtractedArticle:
        self.calls.append(url)
        raise self._error


class FakeLearningNoteGenerator:
    """Consumes scripted outcomes: a `LearningNote` to return, or an error to raise."""

    def __init__(self, outcomes: list[LearningNote | Exception] | None = None) -> None:
        self._outcomes = list(outcomes) if outcomes is not None else []
        self.calls: list[Article] = []

    def generate(self, article: Article) -> LearningNote:
        self.calls.append(article)
        if not self._outcomes:
            raise AssertionError("FakeLearningNoteGenerator has no more scripted outcomes")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class InMemoryArticleRepository:
    """In-memory `ArticleRepository` with scripted failure hooks.

    `fail_update_when` / `fail_add_when` return an exception to raise for a
    given Article, or None to proceed normally. `before_add` runs just before
    the uniqueness check, letting a test simulate an insert race by slipping a
    competing Article into the store.
    """

    def __init__(self) -> None:
        self._store: dict[UUID, Article] = {}
        self.add_calls: list[Article] = []
        self.update_calls: list[Article] = []
        self.fail_add_when: Callable[[Article], Exception | None] = lambda article: None
        self.fail_update_when: Callable[[Article], Exception | None] = lambda article: None
        self.before_add: Callable[[Article], None] = lambda article: None
        self.linked_notes: InMemoryLearningNoteRepository | None = None

    def seed(self, article: Article) -> None:
        """Insert directly, bypassing hooks - for arranging test state."""
        self._store[article.id] = article.model_copy(deep=True)

    def stored(self, article_id: UUID) -> Article:
        """Read directly for assertions; raises KeyError if absent."""
        return self._store[article_id].model_copy(deep=True)

    def add(self, article: Article) -> None:
        self.add_calls.append(article)
        error = self.fail_add_when(article)
        if error is not None:
            raise error
        self.before_add(article)
        for existing in self._store.values():
            if existing.url == article.url:
                raise DuplicateArticleError(
                    f"an article with url {article.url!r} already exists"
                )
            if (
                article.external_id is not None
                and existing.source == article.source
                and existing.external_id == article.external_id
            ):
                raise DuplicateArticleError(
                    f"an article with source {article.source!r} and external_id "
                    f"{article.external_id!r} already exists"
                )
        self._store[article.id] = article.model_copy(deep=True)

    def get_by_id(self, article_id: UUID) -> Article | None:
        found = self._store.get(article_id)
        return found.model_copy(deep=True) if found is not None else None

    def get_by_url(self, url: str) -> Article | None:
        for article in self._store.values():
            if article.url == url:
                return article.model_copy(deep=True)
        return None

    def get_by_source_external_id(self, source: str, external_id: str) -> Article | None:
        for article in self._store.values():
            if article.source == source and article.external_id == external_id:
                return article.model_copy(deep=True)
        return None

    def list_recent(self, limit: int = 20) -> list[Article]:
        validate_positive_limit(limit)
        ordered = sorted(
            self._store.values(), key=lambda a: (a.created_at, a.id.int), reverse=True
        )
        return [article.model_copy(deep=True) for article in ordered[:limit]]

    def update(self, article: Article) -> None:
        self.update_calls.append(article)
        error = self.fail_update_when(article)
        if error is not None:
            raise error
        if article.id not in self._store:
            raise RepositoryError(f"cannot update: no article with id {article.id} exists")
        for existing in self._store.values():
            if existing.id != article.id and existing.url == article.url:
                raise DuplicateArticleError(
                    f"an article with url {article.url!r} already exists"
                )
        self._store[article.id] = article.model_copy(deep=True)

    def get_with_learning_note(self, article_id: UUID) -> ArticleWithLearningNote | None:
        article = self._store.get(article_id)
        if article is None:
            return None
        note = self.linked_notes.get_by_article_id(article_id) if self.linked_notes else None
        return ArticleWithLearningNote(article=article.model_copy(deep=True), learning_note=note)


class InMemoryLearningNoteRepository:
    """In-memory `LearningNoteRepository` with a scripted failure hook."""

    def __init__(self, article_repository: InMemoryArticleRepository | None = None) -> None:
        self._store: dict[UUID, LearningNote] = {}
        self._articles = article_repository
        self.add_calls: list[LearningNote] = []
        self.fail_add_when: Callable[[LearningNote], Exception | None] = lambda note: None
        if article_repository is not None:
            article_repository.linked_notes = self

    def seed(self, note: LearningNote) -> None:
        """Insert directly, bypassing hooks - for arranging test state."""
        self._store[note.article_id] = note.model_copy(deep=True)

    def add(self, note: LearningNote) -> None:
        self.add_calls.append(note)
        error = self.fail_add_when(note)
        if error is not None:
            raise error
        if note.article_id in self._store:
            raise DuplicateLearningNoteError(
                f"a learning note for article {note.article_id} already exists"
            )
        if self._articles is not None and self._articles.get_by_id(note.article_id) is None:
            raise RelatedArticleNotFoundError(f"no article with id {note.article_id} exists")
        self._store[note.article_id] = note.model_copy(deep=True)

    def get_by_article_id(self, article_id: UUID) -> LearningNote | None:
        found = self._store.get(article_id)
        return found.model_copy(deep=True) if found is not None else None

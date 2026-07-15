"""Application-facing contract for discovering article candidates.

Concrete infrastructure adapters (for example an RSS feed reader) implement
`ArticleSource`. Application-layer workflows depend on this port and on
`ArticleSourceError`, never on a specific infrastructure implementation, so
that additional sources can be added later without touching orchestration
code.
"""

from typing import Protocol

from app.domain.article import ArticleCandidate


class ArticleSource(Protocol):
    """A source that can discover article candidates."""

    def discover_articles(self) -> list[ArticleCandidate]:
        """Return the article candidates currently available from this source."""
        ...


class ArticleSourceError(Exception):
    """Raised when article discovery cannot produce a trustworthy result."""

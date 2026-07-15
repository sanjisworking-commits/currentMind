"""Application-facing contract for extracting clean article content.

Concrete infrastructure adapters (for example a Trafilatura-based extractor)
implement `ArticleExtractor`. Application-layer workflows depend on this
port, never on a specific infrastructure implementation, so the extraction
library can be replaced later without touching orchestration code.

Expected operational failures (network errors, unsupported pages, content
below the minimum length, unexpected extraction failures) are represented
as `ExtractedArticle` status values, not raised exceptions - see
`ExtractedArticle` in `app.domain.extraction`. An invalid `url` argument is
a caller contract violation and is raised as `ValueError` instead, since an
invalid URL cannot be represented by `ExtractedArticle` (its `url` field
only accepts valid absolute HTTP/HTTPS URLs).
"""

from typing import Protocol

from app.domain.extraction import ExtractedArticle


class ArticleExtractor(Protocol):
    """A component that can extract clean article content from a URL."""

    def extract(self, url: str) -> ExtractedArticle:
        """Download and extract clean article content from `url`.

        Raises:
            ValueError: if `url` is not a non-blank, absolute http(s) URL
                with a network location. No HTTP request is made in this case.
        """
        ...

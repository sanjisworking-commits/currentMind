# CurrentMind

CurrentMind is a personal learning system that converts UPSC current affairs
articles into structured, exam-oriented Learning Notes.

Phase 1 builds a single end-to-end pipeline for one source (Indian Express
UPSC Current Affairs): RSS discovery → article extraction → LLM analysis →
local storage → web dashboard. See `docs/PRD.md`, `docs/ENGINEERING_SPEC.md`,
and `docs/ROADMAP.md` for the full product and engineering plan.

## Current Status

**Sprint 3 — Article Content Extraction.** Sprint 0 provides the application
skeleton, configuration, logging, and health-check endpoint. Sprint 1 adds
the core domain layer (`app/domain/`): `ArticleCandidate`, `Article`,
`ExtractedArticle`, `LearningNote`, `PrelimsQuestion`, `MainsQuestion`, and
the `ProcessingStatus`, `ExtractionStatus`, and `GSPaper` enums — all
validated Pydantic models with no dependency on FastAPI, SQLAlchemy,
feedparser, Trafilatura, or the OpenAI SDK.

Sprint 2 adds RSS discovery:

* `app/application/sources.py` — the source-neutral `ArticleSource` port and
  the `ArticleSourceError` application error, which application code depends
  on instead of any concrete adapter.
* `app/infrastructure/rss_source.py` — `IndianExpressRSSSource`, which fetches
  the Indian Express UPSC Current Affairs RSS feed with `httpx`, parses it
  with `feedparser`, and maps entries into `ArticleCandidate` objects.

Key behaviour:

* A short-lived `httpx.Client` is created and closed inside every
  `discover_articles()` call (via a context manager); the constructor accepts
  only an optional `httpx.BaseTransport` as a test seam, never a shared
  client.
* Requests use an explicit timeout (`timeout_seconds`, validated `> 0`), an
  explicit `User-Agent` header, and `follow_redirects=True`.
* External IDs prefer `entry.id`, then `entry.guid`, else `None` — never a
  synthesized hash.
* Publication dates prefer `published_parsed`, then `updated_parsed`, else
  `None`; a malformed date never invalidates the rest of an entry.
* Title, author, and category text is cleaned with `html.unescape` plus a
  small `html.parser.HTMLParser`-based tag stripper (standard library only —
  no BeautifulSoup, no regex-based tag removal).
* Deduplication tracks external IDs and URLs in separate sets; an entry is
  dropped if its external ID **or** its URL has already been seen. The first
  occurrence always wins and feed order is otherwise preserved.
* A well-formed feed with zero entries returns `[]`. A feed that parses one
  or more entries but yields zero usable candidates (all invalid) raises
  `ArticleSourceError`, so a broken feed can never look identical to a
  legitimate empty one.

Sprint 3 adds article content extraction:

* `app/application/extraction.py` — the `ArticleExtractor` port
  (`extract(url: str) -> ExtractedArticle`), which application code depends
  on instead of any concrete extraction library.
* `app/infrastructure/trafilatura_extractor.py` — `TrafilaturaArticleExtractor`,
  which downloads a page with `httpx` and extracts clean article text with
  Trafilatura 2.x.

Key behaviour:

* An invalid `url` (blank, relative, non-http(s), or missing a network
  location) raises `ValueError` before any HTTP request is made — invalid
  input is a caller contract violation, not an operational outcome, because
  `ExtractedArticle.url` only accepts valid absolute HTTP/HTTPS URLs.
* Once a valid URL is accepted, every outcome — success, insufficient
  content, network failure, unsupported page, or an unexpected failure — is
  returned as an `ExtractedArticle`; no expected operational failure raises
  an exception.
* A short-lived `httpx.Client` is created and closed inside every
  `extract()` call, the same pattern as `IndianExpressRSSSource`; the
  constructor accepts only an optional `httpx.BaseTransport` test seam.
* The response body is streamed via `response.iter_bytes()` and capped at
  `max_response_bytes` (default 10 MB): a `Content-Length` header over the
  limit is rejected early as a hint, but the streamed byte count is what
  actually enforces the cap, so a missing or understated header cannot
  bypass it.
* HTTP `408`, `429`, and `5xx`, plus timeouts and connection failures, map to
  `NETWORK_ERROR` (transient). Other `4xx` codes, unsupported content types,
  and oversized responses map to `UNSUPPORTED_PAGE` (permanent). The status
  code is always included in `error_reason`.
* Only `text/html` and `application/xhtml+xml` are accepted. A missing
  `Content-Type` is tentatively processed unless the body starts with a
  known binary signature (PDF, PNG, JPEG, GIF); any other explicit content
  type is rejected before Trafilatura ever runs.
* Trafilatura is called with `output_format="txt"`,
  `include_comments=False`, `include_links=False`, `include_images=False`,
  and default `include_tables`/`favor_precision`/`favor_recall` — the
  balanced default extraction mode. The raw downloaded bytes are passed
  directly to Trafilatura (no separate decode step); only whitespace
  normalization is applied locally afterward.
* Extracted text below `min_content_length` (default 200 characters) is
  `INSUFFICIENT_CONTENT`, retaining whatever partial text Trafilatura
  returned; `SUCCESS` requires `len(cleaned_text) >= min_content_length`.

There is no application service wiring RSS discovery to extraction yet, no
persistence, no LLM analysis, and no dashboard.

## Requirements

* Python 3.12
* [uv](https://docs.astral.sh/uv/) for dependency and environment management

## Installation

```bash
uv sync
```

This creates a `.venv` and installs runtime and development dependencies from
`pyproject.toml` / `uv.lock`.

If you prefer not to use `uv`, you can instead create a virtual environment
and install the project in editable mode with `pip`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Environment Setup

Copy the example environment file and adjust values as needed:

```bash
cp .env.example .env
```

| Variable          | Purpose                                              |
| ----------------- | ----------------------------------------------------- |
| `OPENAI_API_KEY`  | API key for LLM analysis (not used until Sprint 5)    |
| `DATABASE_URL`    | SQLite database location                               |
| `RSS_URL`         | Indian Express UPSC Current Affairs feed URL           |
| `LOG_LEVEL`       | Logging verbosity (e.g. `INFO`, `DEBUG`)               |
| `LLM_MODEL`       | LLM model identifier (not used until Sprint 5)         |

Never commit a real `.env` file.

## Database Setup

Not yet applicable. No database models or migrations exist as of Sprint 0.

## Running the Application

```bash
uv run uvicorn main:app --reload
```

Then check the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

## Processing the Feed

Not yet implemented (planned for a later sprint).

## Starting the Dashboard

Not yet implemented (planned for a later sprint).

## Running Tests

```bash
uv run pytest
```

## Running Lint and Type Checks

```bash
uv run ruff check .
uv run mypy .
```

## Known Limitations

* `IndianExpressRSSSource` can discover article candidates and
  `TrafilaturaArticleExtractor` can extract clean text from a URL, but
  nothing yet connects them: there is no application service, CLI command,
  or scheduler wiring discovery into extraction into a pipeline. Persistence,
  LLM analysis, and the dashboard do not exist yet.
* RSS request timeout and the User-Agent string are fixed module constants in
  `app/infrastructure/rss_source.py`, not environment-configurable, since
  Sprint 2 has no concrete need for that yet. `TrafilaturaArticleExtractor`
  follows the same pattern for its own timeout, User-Agent,
  `min_content_length`, and `max_response_bytes`.
* Deduplication is within a single fetched response only; there is no
  persistence-backed or cross-run duplicate detection yet (planned for
  Sprint 4).
* `TrafilaturaArticleExtractor` performs no DNS resolution or IP-range
  filtering (no localhost/private-address/redirect-target protection). This
  is intentional for Sprint 3: `extract(url)` is only ever called by internal
  application workflows on URLs already validated as absolute HTTP/HTTPS, and
  Phase 1 has no public URL-submission endpoint or other untrusted input path
  to this method. This must be revisited before adding any manual
  article-submission API, public endpoint, or other untrusted URL input.
* Full PDF, image, and OCR extraction are out of scope; such content types
  are rejected as `UNSUPPORTED_PAGE` before Trafilatura runs.
* No database exists yet; `database/` and `logs/` are present as placeholders
  for later sprints.

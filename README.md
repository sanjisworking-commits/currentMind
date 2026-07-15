# CurrentMind

CurrentMind is a personal learning system that converts UPSC current affairs
articles into structured, exam-oriented Learning Notes.

Phase 1 builds a single end-to-end pipeline for one source (Indian Express
UPSC Current Affairs): RSS discovery → article extraction → LLM analysis →
local storage → web dashboard. See `docs/PRD.md`, `docs/ENGINEERING_SPEC.md`,
and `docs/ROADMAP.md` for the full product and engineering plan.

## Current Status

**Sprint 4 — Persistence Layer.** Sprint 0 provides the application
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

Sprint 4 adds SQLite persistence for Articles and Learning Notes:

* `app/application/repositories.py` — the `ArticleRepository` and
  `LearningNoteRepository` ports, the `ArticleWithLearningNote` combined-read
  value, and the `RepositoryError`/`DuplicateArticleError`/
  `DuplicateLearningNoteError`/`RelatedArticleNotFoundError` application
  errors, which application code depends on instead of any concrete
  persistence implementation.
* `app/infrastructure/orm_models.py` — the `ArticleRow`/`LearningNoteRow`
  SQLAlchemy 2.x declarative models. Infrastructure-only: never imported
  outside `app/infrastructure/`.
* `app/infrastructure/mappers.py` — pure functions translating between domain
  models and ORM rows (`article_to_row`/`row_to_article`,
  `learning_note_to_row`/`row_to_learning_note`, `update_row_from_article`).
* `app/infrastructure/database.py` — `create_engine_from_url()` and
  `create_session_factory()`, both taking an explicit database URL.
* `app/infrastructure/sqlite_repositories.py` — `SQLiteArticleRepository` and
  `SQLiteLearningNoteRepository`, the concrete SQLAlchemy/SQLite
  implementations of the two repository ports.
* `migrations/` — an Alembic environment with a single baseline revision
  (`3318676bf824`) that creates the complete Sprint 4 schema.

Key behaviour:

* Cross-run deduplication is enforced by named database unique constraints —
  `uq_articles_url` and `uq_articles_source_external_id` — not by an
  application-level existence check before insert. SQLite permits repeated
  `NULL external_id` values under the composite constraint, so RSS entries
  with no GUID never falsely collide.
* `Article` gained a `failure_reason: str | None` field: a `FAILED` article
  must carry a non-empty reason, and every other status must carry `None`,
  enforced transactionally (including under attribute assignment) so an
  invalid transition is rejected outright rather than partially applied.
* `learning_notes.article_id` has a named foreign key to `articles.id` with
  `ON DELETE CASCADE`, and a named unique constraint limiting Phase 1 to one
  Learning Note per Article.
* Every `LearningNote` list field — including the nested `prelims_questions`
  and `mains_questions` — is stored in its own JSON column; there is no
  single opaque blob column.
* SQLite has no native timezone storage. Every datetime read back from a row
  is reconstructed as UTC-aware in the mapper layer before it reaches a
  domain model, whose own validators reject naive datetimes outright.
* `SQLiteArticleRepository`/`SQLiteLearningNoteRepository` open their own
  session per method call (`session_factory.begin()` for writes,
  `session_factory()` for reads); there is no shared long-lived session and
  no Unit of Work.
* `ExtractedArticle` is not persisted as a separate entity. Sprint 4 persists
  only `Article`'s own fields (`raw_text`, `processing_status`,
  `failure_reason`, `updated_at`) via `update()`; a future orchestration
  sprint decides how an `ExtractedArticle` result changes an `Article`.
* A recognized `IntegrityError` (matched against SQLite's own error-message
  wording) becomes a specific `DuplicateArticleError`/`DuplicateLearningNoteError`/
  `RelatedArticleNotFoundError`; any other `SQLAlchemyError` — including a
  locked or unavailable database — becomes a generic `RepositoryError`, never
  a misleading duplicate error. The engine is created with
  `hide_parameters=True`, so no exception message or log line can ever
  include bound parameter values (article or Learning Note content).

There is no application service wiring RSS discovery to extraction to
persistence yet, no LLM analysis, and no dashboard.

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

The database schema is managed by Alembic. Apply the migration to create the
local SQLite database (using `DATABASE_URL` from `.env`, defaulting to
`sqlite:///./database/currentmind.db`):

```bash
uv run alembic upgrade head
```

This creates the `articles` and `learning_notes` tables. Re-running the
command is safe (Alembic tracks the applied revision in an `alembic_version`
table and is a no-op once already at `head`).

To inspect or roll back the schema:

```bash
uv run alembic current   # show the currently applied revision
uv run alembic history   # show all revisions
uv run alembic downgrade base   # drop the Sprint 4 tables
```

Automated tests never touch this database — each test applies the same
migration to an isolated temporary SQLite file under pytest's `tmp_path`.

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

* `IndianExpressRSSSource` can discover article candidates,
  `TrafilaturaArticleExtractor` can extract clean text from a URL, and
  `SQLiteArticleRepository`/`SQLiteLearningNoteRepository` can persist and
  retrieve them, but nothing yet connects these into a pipeline: there is no
  application service, CLI command, or scheduler wiring discovery into
  extraction into persistence. No LLM analysis and no dashboard exist yet.
* RSS request timeout and the User-Agent string are fixed module constants in
  `app/infrastructure/rss_source.py`, not environment-configurable, since
  Sprint 2 has no concrete need for that yet. `TrafilaturaArticleExtractor`
  follows the same pattern for its own timeout, User-Agent,
  `min_content_length`, and `max_response_bytes`.
* Cross-run deduplication is now enforced by database unique constraints
  (`uq_articles_url`, `uq_articles_source_external_id`), but nothing yet
  calls `ArticleRepository` from RSS discovery — that wiring is planned for
  Sprint 6.
* `TrafilaturaArticleExtractor` performs no DNS resolution or IP-range
  filtering (no localhost/private-address/redirect-target protection). This
  is intentional for Sprint 3: `extract(url)` is only ever called by internal
  application workflows on URLs already validated as absolute HTTP/HTTPS, and
  Phase 1 has no public URL-submission endpoint or other untrusted input path
  to this method. This must be revisited before adding any manual
  article-submission API, public endpoint, or other untrusted URL input.
* Full PDF, image, and OCR extraction are out of scope; such content types
  are rejected as `UNSUPPORTED_PAGE` before Trafilatura runs.
* `ExtractedArticle` (the Sprint 3 extraction result) is not persisted as a
  separate entity — there are no `extraction_status`/`extracted_at`/
  `extraction_error_reason` columns and no history of extraction attempts.
  Only the `Article` fields that already exist (`raw_text`,
  `processing_status`, `failure_reason`, `updated_at`) are persisted, via
  `ArticleRepository.update()`. A future orchestration sprint decides how an
  `ExtractedArticle` result changes an `Article`.
* There is no cross-repository transaction atomicity between
  `ArticleRepository` and `LearningNoteRepository` calls (no Unit of Work);
  each repository method commits its own transaction independently.
* The Alembic baseline revision (`migrations/versions/3318676bf824_*.py`) is
  hand-written to mirror `app/infrastructure/orm_models.py`, not
  autogenerated against a live database. Future schema changes should use
  `alembic revision --autogenerate` against a disposable database and then be
  reviewed by hand.

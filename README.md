# CurrentMind

CurrentMind is a personal learning system that converts UPSC current affairs
articles into structured, exam-oriented Learning Notes.

Phase 1 builds a single end-to-end pipeline for one source (Indian Express
UPSC Current Affairs): RSS discovery → article extraction → LLM analysis →
local storage → web dashboard. See `docs/PRD.md`, `docs/ENGINEERING_SPEC.md`,
and `docs/ROADMAP.md` for the full product and engineering plan.

## Current Status

**Sprint 2 — Source Adapter and RSS Discovery.** Sprint 0 provides the
application skeleton, configuration, logging, and health-check endpoint.
Sprint 1 adds the core domain layer (`app/domain/`): `ArticleCandidate`,
`Article`, `ExtractedArticle`, `LearningNote`, `PrelimsQuestion`,
`MainsQuestion`, and the `ProcessingStatus`, `ExtractionStatus`, and `GSPaper`
enums — all validated Pydantic models with no dependency on FastAPI,
SQLAlchemy, feedparser, Trafilatura, or the OpenAI SDK.

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

There is no application service wiring the adapter into a pipeline yet, no
persistence, no article extraction, and no dashboard.

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

* `IndianExpressRSSSource` can discover article candidates from the feed, but
  nothing yet calls it: there is no application service, CLI command, or
  scheduler wiring RSS discovery into a pipeline. Article extraction,
  persistence, LLM analysis, and the dashboard do not exist yet.
* RSS request timeout and the User-Agent string are fixed module constants in
  `app/infrastructure/rss_source.py`, not environment-configurable, since
  Sprint 2 has no concrete need for that yet.
* Deduplication is within a single fetched response only; there is no
  persistence-backed or cross-run duplicate detection yet (planned for
  Sprint 4).
* No database exists yet; `database/` and `logs/` are present as placeholders
  for later sprints.

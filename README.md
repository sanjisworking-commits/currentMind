# CurrentMind

CurrentMind is a **local, personal** learning system that converts UPSC
current-affairs articles into structured, exam-oriented Learning Notes. It
discovers current-affairs articles, extracts their text, generates a
structured Learning Note with an LLM, persists everything locally in SQLite,
and displays it through a read-only web dashboard.

**Who it is for:** an individual UPSC (or similar competitive-exam) aspirant
running the tool on their own machine. The goal is to spend less time making
current-affairs notes by hand and more time studying structured, revisable
knowledge — not to build a news reader.

## Phase 1 features

* Indian Express UPSC Current Affairs **RSS discovery**.
* **Article extraction** (Trafilatura).
* **Structured Learning Notes** generated via a pluggable LLM provider — the
  OpenAI Responses API or the Anthropic Messages API, selected by `LLM_PROVIDER`.
* **SQLite persistence** (schema managed by Alembic).
* **Duplicate protection** enforced by database unique constraints.
* **Idempotent processing** — re-running never re-analyzes completed articles.
* **Targeted retry** for failed articles (in-feed and off-feed).
* A **read-only, server-rendered dashboard**.

Phase 1 is a single end-to-end pipeline for one source: RSS discovery →
article extraction → LLM analysis → local storage → web dashboard.

## Documentation

* `docs/PRD.md`, `docs/ENGINEERING_SPEC.md`, `docs/ROADMAP.md` — product and
  engineering plan.
* `docs/ARCHITECTURE.md` — system-level architecture overview.
* `docs/PROMPTS.md` — prompt versioning and the structured-output contract.
* `docs/DECISIONS.md` — architectural decision records (ADR-001 … ADR-026).
* `docs/RELEASE_CHECKLIST.md` — Phase 1 release verification checklist.

## Current Status

**Sprint 7 — Web Dashboard.** Sprint 0 provides the application
skeleton, configuration, logging, and health-check endpoint. Sprint 1 adds
the core domain layer (`app/domain/`): `ArticleCandidate`, `Article`,
`ExtractedArticle`, `LearningNote`, `PrelimsQuestion`, `MainsQuestion`, and
the `ProcessingStatus`, `ExtractionStatus`, and `GSPaper` enums — all
validated Pydantic models with no dependency on FastAPI, SQLAlchemy,
feedparser, Trafilatura, or any LLM provider SDK.

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

Sprint 5 adds structured LLM analysis:

* `app/application/learning_notes.py` — the `LearningNoteGenerator` port
  (`generate(article: Article) -> LearningNote`), the
  `LearningNoteGenerationError`/`LearningNoteProviderError`/
  `LearningNoteValidationError` application errors, and the pure
  `assemble_learning_note()` function.
* `app/domain/learning_note.py` — adds `LearningNoteContent`, the
  AI-authored subset of `LearningNote`'s fields (every category an LLM may
  produce, none of the trusted metadata). `LearningNote` itself is
  unchanged.
* `app/infrastructure/prompt_loader.py` — `load_prompt_template()`, which
  loads and validates a `string.Template` prompt file's exact placeholder
  set.
* `app/infrastructure/openai_generator.py` — `OpenAILearningNoteGenerator`,
  the OpenAI Responses API implementation of `LearningNoteGenerator`.
* `app/infrastructure/anthropic_generator.py` — `AnthropicLearningNoteGenerator`,
  the Anthropic Messages API implementation of the same `LearningNoteGenerator`
  port (added later; see ADR-026). Both adapters share the source-neutral v1
  prompts and the same three-attempt validation policy; the CLI composition
  root selects between them by `LLM_PROVIDER`. The description below is written
  around the OpenAI adapter; the Anthropic adapter mirrors it, substituting
  `messages.parse(..., output_format=LearningNoteContent)` and the Anthropic
  SDK's stop-reason/error model.
* `prompts/learning_note_v1_system.txt` and `prompts/learning_note_v1_user.txt`
  — the versioned system and user prompt templates (shared by both providers).

Key behaviour:

* `LearningNoteContent` contains only the 15 AI-authored fields (`summary`
  through `keywords`) with **no defaults** — OpenAI Structured Outputs
  requires every field present in every response, so an irrelevant category
  must come back as an explicit empty list from the model itself, never
  omitted and backfilled locally. It has no `id`, `article_id`,
  `model_name`, `prompt_version`, or `created_at` fields at all, so the
  model has no way to influence trusted metadata - not by convention, but
  because those fields don't exist on the type sent to the LLM.
* `assemble_learning_note()` builds the final `LearningNote` using explicit,
  individually named keyword arguments for every field - never a `**dict`
  spread - so there is no path through which content could override a
  trusted field. `id` and `created_at` use `LearningNote`'s own domain
  defaults unless a `created_at` is explicitly injected (for deterministic
  tests).
* Uses the OpenAI Responses API's native structured-output parsing
  (`client.responses.parse(..., text_format=LearningNoteContent)`)
  exclusively - no manual JSON parsing, Markdown-fence stripping, or regex
  extraction anywhere. Pydantic (via the SDK's own use of
  `model_validate_json`) is the sole validator of model output.
* Exactly **three total validation attempts** (one original plus up to two
  repair retries), triggered only by a `pydantic.ValidationError` raised
  during parsing or a completed, non-refusal response with no parsed
  content. A model refusal, an incomplete response
  (`max_output_tokens`/`content_filter`), and any SDK-level operational
  failure (transport, authentication, rate limit, server error) are never
  retried by application code - each becomes an immediate
  `LearningNoteProviderError`. The OpenAI SDK's own transport-level retries
  (`max_retries`, default 2) operate underneath this, entirely separately.
* The only test seam is `_ResponsesClient`, a narrow, infrastructure-private
  `Protocol` covering just the `responses.parse(model=..., input=...,
  text_format=...)` surface this adapter actually calls - not a fake
  `LearningNoteGenerator`. Tests inject a handwritten fake implementing this
  Protocol via the constructor's `responses=` parameter; production code
  always constructs a real `openai.OpenAI` client from an explicit
  `api_key=` parameter. The constructor requires exactly one of `api_key` or
  `responses`, never both, never neither.
* Prompts are plain UTF-8 text rendered with stdlib `string.Template`
  (`$identifier` placeholders, `.substitute()` - never `.safe_substitute()`,
  so a missing or unknown placeholder fails loudly). `PROMPT_VERSION = "v1"`
  is a single source of truth: both prompt filenames are derived from it, so
  bumping the version without adding the corresponding files fails
  immediately with a clear `FileNotFoundError` rather than silently
  reusing stale prompts.
* Repair instructions sent back to the model on retry contain only
  sanitized Pydantic error `type`/`loc`/`msg` fields
  (`include_input=False`) - never the rejected value, never a raw
  `str(exc)` rendering, which by Pydantic v2 default embeds the offending
  input.

Sprint 6 connects everything into one processing pipeline:

* `app/application/processing.py` — `ProcessNewsFeedService`, the synchronous
  application service wiring discovery → identity resolution → persistence →
  extraction → analysis → Learning Note persistence, plus the
  `ProcessingSummary`/`FailureDetail`/`ArticleProcessingResult` result types,
  the `reconstruct_article()` state-transition helper, and
  `new_article_from_candidate()`.
* `app/cli.py` — the stdlib-`argparse` command-line entry point and
  composition root (see "Processing the Feed" below).

Key behaviour:

* **Idempotent reruns.** Resumption is decided from ground truth - whether a
  Learning Note exists and whether accepted non-blank `raw_text` exists -
  never by trusting a possibly stale `processing_status` or parsing
  `failure_reason` text. Completed Articles are skipped; incomplete ones
  resume at exactly the stage they need; an existing note reconciles a stale
  status to `analyzed` without calling the generator.
* **Note-first finalization.** The Learning Note is always persisted before
  the Article is marked `analyzed`, so `analyzed` can never durably exist
  without its note. If finalization fails after the note is saved, the
  Article deliberately rests at its last durable checkpoint and the next run
  reconciles it - the intended no-Unit-of-Work recovery path (ADR-023).
* **Two retry scopes.** `process-feed --retry-failed` retries failed
  Articles rediscovered in the current feed window;
  `retry-article <UUID>` retries any persisted Article directly, including
  one that has dropped out of the feed, and never calls RSS discovery.
* **Per-Article failure isolation.** One Article's failure - expected or a
  genuine defect - never stops the batch. Failures surface as structured,
  privacy-safe `FailureDetail`s (stage, fixed category, safe message,
  query-stripped URL; never article text, prompts, or provider output).
* **Summary counters are independent metrics** and intentionally overlap: a
  fully successful new Article increments `new_articles`,
  `successfully_extracted`, and `successfully_analyzed`. They are not a
  partition of `total_discovered`; the one arithmetic invariant is
  `failed == len(failure_details)`.

Sprint 7 adds the read-only web dashboard:

* `app/application/dashboard.py` — `DashboardQueryService` (implementing the
  `DashboardQuery` port), which reads persisted Articles and Learning Notes
  through the repository ports and assembles the immutable `ArticleCard` and
  `ArticleDetail` read models. It imports no FastAPI/Jinja2/SQLAlchemy and
  performs no writes.
* `app/presentation/api.py` — the `create_app()` factory now serves `GET /`
  (recent articles) and `GET /articles/{article_id}` (detail) with
  server-rendered Jinja2 templates, alongside the unchanged `/health`.
* `app/presentation/templates/` and `app/presentation/static/dashboard.css` —
  the templates and one local stylesheet (no JavaScript, no build step, no
  external assets).
* `app/presentation/view_helpers.py` — display-only helpers (status labels,
  source humanization, date formatting).

Key behaviour:

* **Strictly read-only.** No dashboard request writes to the database or calls
  the processing pipeline, generator, extractor, or source — visiting the
  dashboard never triggers processing.
* **Bounded home page.** The home page shows the 30 most recent articles
  (`1` list query + one Learning Note lookup per article); the full table is
  never loaded.
* **Safe display.** Every persisted field is rendered through Jinja2
  autoescaping (no `|safe` anywhere); `Article.raw_text` is never placed in a
  read model or template. A malformed article id returns 422, a well-formed
  but unknown id returns an HTML 404, and a repository read failure renders a
  fixed 503 page with no database detail.
* Prelims answers/explanations use a native `<details>` disclosure, so the
  dashboard works without JavaScript.

## Requirements

* **Python 3.12 or later** (the repository pins `3.12` via `.python-version`).
* [uv](https://docs.astral.sh/uv/) for dependency and environment management.
* Local filesystem access (SQLite database + logs).
* An **API key for the selected LLM provider — for processing only**. With
  `LLM_PROVIDER=openai` (the default) that is `OPENAI_API_KEY`; with
  `LLM_PROVIDER=anthropic` it is `ANTHROPIC_API_KEY`. Only the selected
  provider's key is required. The dashboard needs neither provider key; it only
  reads the local database.

## Installation

```bash
git clone <repository-url>
cd currentMind
uv sync --frozen
cp .env.example .env
```

`uv sync --frozen` installs the exact locked runtime and development
dependencies from `pyproject.toml` / `uv.lock` into a `.venv` without
modifying the lockfile. (`uv sync` without `--frozen` is also fine for local
development.) Do **not** put a real API key in a committed file — edit your
local `.env` only.

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

| Variable            | Required for | Default | Notes |
| ------------------- | ------------ | ------- | ----- |
| `LLM_PROVIDER`      | processing   | `openai` | Learning Note generator: `openai` or `anthropic`. Selects which API key is required. **Not** needed by the dashboard. |
| `OPENAI_API_KEY`    | processing (openai) | none | Needed by `process-feed` / `retry-article` when `LLM_PROVIDER=openai`. **Not** needed by the dashboard. |
| `ANTHROPIC_API_KEY` | processing (anthropic) | none | Needed by `process-feed` / `retry-article` when `LLM_PROVIDER=anthropic`. **Not** needed by the dashboard. |
| `LLM_MODEL`         | processing   | none    | Model identifier for the selected provider (e.g. `gpt-4o-mini`, `claude-haiku-4-5`). **Not** needed by the dashboard. |
| `DATABASE_URL`      | processing + dashboard | `sqlite:///./database/currentmind.db` | The only variable the dashboard needs. |
| `RSS_URL`           | processing   | Indian Express UPSC Current Affairs feed | Feed to discover. |
| `LOG_LEVEL`         | optional     | `INFO`  | Logging verbosity (e.g. `INFO`, `DEBUG`). |

`.env.example` is **secret-free**: it lists every supported variable with safe
defaults or empty placeholders, and contains no real credentials. Copy it to
`.env` and fill in your own values. **Never commit a real `.env` file** (it is
git-ignored).

## Database Setup

Alembic is the **sole schema authority** — there is no `create_all()` path in
the application, so the tables exist only after you run the migration. Apply
the migration to create the local SQLite database (using `DATABASE_URL` from
`.env`, defaulting to `sqlite:///./database/currentmind.db`):

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

The database schema must exist first (`uv run alembic upgrade head` — the CLI
never runs migrations automatically and fails with a clear message if the
schema is missing). `LLM_MODEL` and the selected provider's API key must be set
(`OPENAI_API_KEY` for `LLM_PROVIDER=openai`, `ANTHROPIC_API_KEY` for
`LLM_PROVIDER=anthropic`).

Process the current RSS feed window:

```bash
uv run python -m app.cli process-feed
```

Also retry failed articles that are rediscovered in the current feed:

```bash
uv run python -m app.cli process-feed --retry-failed
```

Retry one persisted article by UUID — including an article that no longer
appears in the RSS feed (this command never calls feed discovery):

```bash
uv run python -m app.cli retry-article <ARTICLE_UUID>
```

The two retry paths differ deliberately: `--retry-failed` only reaches failed
articles still present in the feed window, while `retry-article` operates
purely on persisted state.

Exit codes: `0` for a completed command with no article-level failures; `1`
for a configuration failure (a missing provider-specific API key —
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for the selected provider — a missing
`LLM_MODEL`, or an unknown `LLM_PROVIDER`), a feed-discovery failure, an unknown
or malformed article id, a database unavailable/unmigrated failure, or one or
more per-article failures. The
command prints summary counts and safe failure details (stage, category,
message, identifiers) — never article text or provider output.

### Timeouts and retries

The current defaults are fixed:

| Stage | Request timeout | Retries |
| ----- | --------------- | ------- |
| RSS fetch | 10 s | none |
| Article extraction | 10 s | none |
| LLM provider request | 60 s | selected SDK transport retries (2) |
| Structured-output validation | — | up to 3 application attempts |

Both provider adapters (OpenAI and Anthropic) use the same values: a
60-second request timeout and two SDK transport retries. These are distinct
mechanisms and should not be conflated:

* **SDK transport retry** — the selected provider SDK may retry an individual
  request on transient transport errors; this is the SDK's own concern (two
  retries by default, the same for both providers).
* **Application validation attempt** — up to three structured-output attempts
  (one original plus up to two repairs), triggered only by a schema
  `ValidationError` or a completed response with no parsed content. Refusals
  and provider-status (provider-outcome) failures are **not**
  application-retried, for either provider.
* Total processing duration for one article has **no guaranteed fixed upper
  bound** — it is bounded per request by the timeouts above, but the number of
  requests (validation attempts × SDK transport retries) compounds.
* **Insert-race recovery** — a one-time re-read after a duplicate-insert race.
* **Reconciliation** — an interrupted run is healed on the next run from
  persisted ground truth (no regeneration).
* **Manual retry** — the operator-triggered `--retry-failed` /
  `retry-article` commands above.

Because the SDK applies its own retry backoff, the total wall-clock time of a
single article's analysis may exceed a simple multiplication of the 60-second
timeout; there is no guaranteed fixed upper bound. Validation repair is
nonetheless bounded to three attempts.

## Starting the Dashboard

Apply the database migration first (`uv run alembic upgrade head`), then start
the application:

```bash
uv run uvicorn main:app --reload
```

Open the dashboard at:

* `http://127.0.0.1:8000/` — the most recent processed articles;
* `http://127.0.0.1:8000/articles/<article-uuid>` — one article's full
  Learning Note.

The dashboard is **read-only**: visiting it never processes the feed, and its
routes never call RSS or OpenAI or write to the database. Processing remains a
separate, manually run CLI operation (`uv run python -m app.cli process-feed`);
there is no scheduler and no automatic processing. The dashboard requires only
`DATABASE_URL` (not `OPENAI_API_KEY`/`LLM_MODEL`). If the database is missing
or unmigrated, pages return a safe "temporarily unavailable" response rather
than an error trace.

**This dashboard is for local, single-user use only.** It has **no
authentication** and is **not hardened for public internet exposure** — do not
expose it to untrusted networks. `--reload` is a development convenience;
omit it for ordinary local use. By default `uvicorn` binds `127.0.0.1`
(localhost).

Optional filters (by GS paper, processing status, or keyword) are deferred:
the required pages are complete without them, and none needs a new repository
contract.

## Running Tests

```bash
uv run pytest
```

## Running Lint and Type Checks

```bash
uv run ruff check .
uv run mypy .
```

## Troubleshooting

| Symptom | Likely cause and fix |
| ------- | -------------------- |
| `uv: command not found` | `uv` is not installed. Install it (see the [uv docs](https://docs.astral.sh/uv/)) and re-run. |
| Python version error on `uv sync` | Python 3.12+ is required (`.python-version` pins `3.12`). Install it or point `uv` at a 3.12 interpreter. |
| Settings load fails / values missing | No `.env` present. `cp .env.example .env` and fill in values. |
| `OPENAI_API_KEY is required` | Using `LLM_PROVIDER=openai` (the default): set `OPENAI_API_KEY` in your environment or `.env` (needed only for `process-feed` / `retry-article`). |
| `ANTHROPIC_API_KEY is required` | Using `LLM_PROVIDER=anthropic`: set `ANTHROPIC_API_KEY` in your environment or `.env`. |
| `Unknown LLM_PROVIDER ...` | Set `LLM_PROVIDER` to `openai` or `anthropic`. |
| `LLM_MODEL is required` | Set `LLM_MODEL` (the model identifier for the selected provider). |
| Database-directory error | The `database/` directory must exist (it is committed with a `.gitkeep`). Recreate it if deleted. |
| "Database unavailable or schema not initialized" | The database is missing or unmigrated. Run `uv run alembic upgrade head`. |
| Feed discovery failed | The RSS feed is unavailable or `RSS_URL` is wrong/unreachable. Verify `RSS_URL` and network/feed availability, then retry. |
| Malformed RSS response | The feed returned unparseable content. `process-feed` fails safely with a fixed message; retry later. |
| An article shows `Failed` with `extraction: insufficient content` | The page had too little extractable text. Not all pages extract cleanly; the article is preserved and can be retried. |
| An article shows `Failed` with `analysis: provider failure` | A provider/transport error occurred. Retry with `retry-article <UUID>` (or `process-feed --retry-failed` if still in the feed). |
| An article shows `Failed` with `analysis: validation exhausted` | Structured output failed validation three times. Retry as above; persistent failures may indicate an unsuitable article. |
| Retrying a failed article | Use `process-feed --retry-failed` for articles still in the feed window, or `retry-article <ARTICLE_UUID>` for one that has dropped out. |
| Dashboard shows "temporarily unavailable" (HTTP 503) | The database read failed (missing/unmigrated/unavailable). Run `uv run alembic upgrade head` and confirm `DATABASE_URL`. |
| Dashboard returns 422 for an article URL | The URL path is not a valid UUID. Use a real article UUID from the home page. |
| Stale remote branches after a `git push --delete` returns HTTP 403 | Branch deletion may be disallowed for your account. This is not an error in the merge; leave the branch or ask a repository admin to remove it. Do not force anything. |
| Resetting a local database | **First confirm `DATABASE_URL`**, then delete only that known disposable/local file (e.g. the default `./database/currentmind.db`), and re-run `uv run alembic upgrade head`. **Never blindly delete a database at an unknown path.** |

## Known Limitations

* There is only **one source** (Indian Express UPSC Current Affairs) and no
  multi-source abstraction in Phase 1.
* Generated Learning Notes are **not independently fact-verified** — there is
  no web verification or retrieval step, so a note may contain model error and
  should be reviewed before you rely on it (see `docs/PROMPTS.md`).
* CurrentMind is intended for **local, single-user use** and is **not hardened
  for public internet exposure** (no authentication, no TLS, no
  authorization).
* There is no automatic scheduling or background processing — `process-feed`
  is run manually, and the dashboard never triggers it.
* The dashboard is read-only and has no filters or pagination: the home page
  shows the 30 most recent articles (one list query plus one Learning Note
  lookup per article), and there is no archive navigation. Optional
  status/GS-paper/keyword filters were deferred (see ADR-024).
* The dashboard has no authentication and is intended for local single-user
  use only.
* RSS request timeout and the User-Agent string are fixed module constants in
  `app/infrastructure/rss_source.py`, not environment-configurable, since
  Sprint 2 has no concrete need for that yet. `TrafilaturaArticleExtractor`
  follows the same pattern for its own timeout, User-Agent,
  `min_content_length`, and `max_response_bytes`.
* `process-feed --retry-failed` reaches only failed articles that are still
  present (rediscovered) in the current RSS feed window. A failed article
  that has dropped out of the feed is retried with
  `retry-article <ARTICLE_UUID>` instead — off-feed retry is supported, but
  only through that explicit, targeted command.
* Processing summary counters are independent, deliberately overlapping
  operational metrics, not a partition of `total_discovered` (see the
  Sprint 6 notes above and ADR-023).
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
  `ArticleRepository.update()`. Sprint 6's `ProcessNewsFeedService` decides
  how an `ExtractedArticle` result changes an `Article`: only fully accepted
  extraction text is ever written into `raw_text`; unusable partial text
  from a failed extraction is discarded.
* There is no cross-repository transaction atomicity between
  `ArticleRepository` and `LearningNoteRepository` calls (no Unit of Work);
  each repository method commits its own transaction independently. Sprint 6
  compensates with deliberate write ordering (Learning Note before Article
  finalization) plus note-existence reconciliation on the next run
  (ADR-023), so interrupted sequences converge without regeneration.
* The Alembic baseline revision (`migrations/versions/3318676bf824_*.py`) is
  hand-written to mirror `app/infrastructure/orm_models.py`, not
  autogenerated against a live database. Future schema changes should use
  `alembic revision --autogenerate` against a disposable database and then be
  reviewed by hand.
* `LearningNoteGenerator.generate()` itself remains workflow-unaware: it
  only reads `article.raw_text` and returns a `LearningNote`. All status
  transitions and persistence around it are owned by
  `ProcessNewsFeedService`. No automated test makes a live OpenAI or Anthropic
  request — the generator, pipeline, CLI, and composition tests all use
  handwritten fakes and temporary databases.
* Neither provider adapter (`OpenAILearningNoteGenerator`,
  `AnthropicLearningNoteGenerator`) truncates long extracted article text.
  Real UPSC current-affairs articles are short-to-medium news pieces well
  within typical model context windows, and truncation risks silently
  discarding article content. The documented risk: an abnormally long or
  mis-extracted article could be rejected by the selected provider for
  exceeding the configured model's context length - this surfaces as a safe
  `LearningNoteProviderError`, not a crash, but is not retried.
* Two Learning Note providers are supported, selected by `LLM_PROVIDER`:
  OpenAI (Responses API, default) and Anthropic (Messages API). Both go
  through the same `LearningNoteGenerator` port, the same source-neutral
  prompt files, and the same bounded validation-retry policy. There is no
  OpenAI Chat Completions fallback, and only one provider is active per run.
* Application-level retries are validation-only (a `pydantic.ValidationError`
  or a completed response with no parsed content), bounded at three total
  attempts, for both providers. Transport-level retry is entirely the selected
  provider SDK's own concern (`max_retries`, configured explicitly at client
  construction, default 2) and is never duplicated by application code.

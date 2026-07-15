# DECISIONS.md

# CurrentMind Architectural Decision Log

**Project:** CurrentMind
**Purpose:** Record significant product and engineering decisions that affect architecture, data design, technology choices, security boundaries, extensibility, and future integration.

---

# 1. How to Use This Document

This file records decisions that should remain understandable months later.

Each decision should explain:

* What was decided
* Why the decision was necessary
* Which alternatives were considered
* What consequences follow from the decision
* Whether the decision is active, superseded, or under review

Do not record minor coding details, temporary debugging steps, or routine implementation choices.

---

# 2. Decision Statuses

Use one of the following statuses:

* **Proposed** — Suggested but not yet accepted
* **Accepted** — Approved and currently applicable
* **Superseded** — Replaced by a later decision
* **Deprecated** — Still present but should not be used for new work
* **Rejected** — Considered and intentionally not selected

---

# 3. Decision Template

Copy this template when adding a new decision.

```markdown
## ADR-XXX: Decision Title

**Status:** Proposed  
**Date:** YYYY-MM-DD  
**Decision Owner:** Musa / Claude Code / Project Team

### Context

Describe the problem, constraint, or architectural question that required a decision.

### Decision

State the chosen approach clearly.

### Alternatives Considered

1. Alternative One
2. Alternative Two
3. Alternative Three

### Rationale

Explain why the selected option is preferable.

### Consequences

#### Positive

- Benefit
- Benefit

#### Negative

- Trade-off
- Limitation

### Revisit When

Describe the conditions under which this decision should be reconsidered.
```

---

# 4. Accepted Decisions

## ADR-001: Build CurrentMind as a Standalone Project

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

CurrentMind may eventually become part of the Knowledge Operating System, or KOS.

Building it directly inside KOS would introduce additional architectural constraints before the product workflow has been validated.

The immediate priority is to determine whether an AI-assisted current affairs learning pipeline is useful in regular UPSC preparation.

### Decision

CurrentMind will be built and operated as a standalone application during its initial phases.

It will not depend on KOS packages, infrastructure, terminology, or internal services.

Future compatibility with KOS will be supported through clean interfaces and structured domain models.

### Alternatives Considered

1. Build CurrentMind directly inside KOS.
2. Build CurrentMind as a tightly coupled KOS module.
3. Build CurrentMind independently and integrate it later.

### Rationale

An independent project allows:

* Faster experimentation
* Simpler debugging
* Clearer product validation
* Fewer inherited abstractions
* Easier changes to the workflow
* Independent deployment and use

Once the product becomes stable, integration boundaries can be designed using actual requirements rather than assumptions.

### Consequences

#### Positive

* CurrentMind can evolve quickly.
* KOS complexity does not slow Phase 1.
* Product usefulness can be tested independently.
* Future integration can be based on a stable data model.

#### Negative

* Some integration work may be required later.
* Certain infrastructure may temporarily exist in both projects.
* Data migration or adapter development may eventually be necessary.

### Revisit When

Reconsider this decision after CurrentMind has:

* A stable article-processing pipeline
* A stable Learning Note schema
* Regular real-world usage
* Clear KOS integration requirements

---

## ADR-002: Treat CurrentMind as a Learning System, Not a News Reader

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

A conventional news application optimizes for content discovery, frequent consumption, engagement, and reading volume.

CurrentMind is intended to help an aspirant understand, organize, revise, and retain current affairs.

A summary-focused news reader would not fully satisfy that objective.

### Decision

CurrentMind will be designed as a learning pipeline.

The primary output will be a structured Learning Note rather than a generic article summary.

The system will optimize for:

* Conceptual clarity
* UPSC syllabus mapping
* Static-current integration
* Prelims preparation
* Mains preparation
* Revision
* Retention

### Alternatives Considered

1. Build a standard RSS reader with AI summaries.
2. Build a current affairs aggregation dashboard.
3. Build a learning-oriented article transformation pipeline.

### Rationale

The learning-oriented model provides greater value than merely shortening articles.

It also creates structured outputs that can later support search, revision, flashcards, concept linking, and KOS integration.

### Consequences

#### Positive

* Product decisions remain aligned with examination preparation.
* Generated outputs are more reusable.
* The system avoids becoming an ordinary news feed.
* Future educational features have a stronger foundation.

#### Negative

* Prompt design becomes more complex.
* Output quality requires stricter validation.
* Some articles may not produce meaningful content in every learning category.

### Revisit When

Reconsider only if user testing shows that the structured Learning Note creates unnecessary complexity or reduces study efficiency.

---

## ADR-003: Use a Modular Monolith for Phase 1

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

CurrentMind requires several responsibilities:

* RSS discovery
* Article extraction
* LLM analysis
* Database persistence
* Web presentation

These responsibilities should remain separated without introducing operational complexity inappropriate for a personal-use application.

### Decision

CurrentMind will be implemented as a modular monolith using clear domain, application, infrastructure, and presentation boundaries.

It will run as one application and use one local database.

### Alternatives Considered

1. Microservices
2. Serverless functions
3. A single unstructured script
4. Modular monolith

### Rationale

A modular monolith provides:

* Clear separation of responsibilities
* Simple local execution
* Easy testing
* Low deployment complexity
* Sufficient extensibility for later phases

Microservices would add unnecessary networking, deployment, monitoring, and data-consistency concerns.

A single script would be quick initially but difficult to maintain.

### Consequences

#### Positive

* Easy local development
* Simple debugging
* Low operational overhead
* Clear internal module boundaries
* Straightforward testing

#### Negative

* All components share one deployment unit.
* Poorly enforced boundaries could lead to coupling.
* Scaling individual components independently is not supported.

### Revisit When

Reconsider only if real usage creates clear operational requirements such as:

* Independent scaling
* Long-running background workloads
* Multiple teams owning separate services
* Significant deployment isolation needs

---

## ADR-004: Use Python 3.12 and FastAPI

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The project requires RSS parsing, article extraction, LLM integration, validation, persistence, testing, and a lightweight local web interface.

Python provides strong libraries for all these requirements.

### Decision

CurrentMind will use Python 3.12 as the implementation language and FastAPI for HTTP endpoints and the local web application.

### Alternatives Considered

1. Python with FastAPI
2. Python with Flask
3. Python with Django
4. TypeScript with Next.js
5. Streamlit-only application

### Rationale

Python is well suited for:

* AI and LLM integration
* Content extraction
* Data validation
* Rapid backend development
* Future knowledge-processing workflows

FastAPI provides:

* Strong typing support
* Pydantic integration
* Simple routing
* Automatic API documentation
* Low framework overhead

Django would add features not required in Phase 1.

Streamlit would enable quick prototyping but provide weaker long-term separation between application logic and presentation.

### Consequences

#### Positive

* Strong ecosystem support
* Fast development
* Easy testing
* Good compatibility with future AI features
* Clean API boundaries

#### Negative

* A separate template layer may be needed for the dashboard.
* Python packaging and environment setup must be managed carefully.
* FastAPI does not provide all batteries included by larger frameworks.

### Revisit When

Reconsider if the application later requires a highly interactive frontend that cannot be maintained effectively with server-rendered pages.

---

## ADR-005: Use SQLite for Phase 1

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

CurrentMind is initially a single-user local application.

Expected data volume and write concurrency are low.

A cloud or server database would add configuration and maintenance costs without immediate benefit.

### Decision

CurrentMind will use SQLite during Phase 1.

SQLAlchemy will provide persistence abstractions, and database migrations will be used to manage schema changes.

### Alternatives Considered

1. SQLite
2. PostgreSQL
3. MongoDB
4. Airtable
5. File-based JSON or Markdown storage only

### Rationale

SQLite provides:

* No server setup
* Reliable local persistence
* Transaction support
* Simple backups
* Adequate performance for personal use
* A reasonable migration path to PostgreSQL through SQLAlchemy

JSON-only storage would become difficult for relationships, deduplication, filtering, and status tracking.

### Consequences

#### Positive

* Minimal setup
* Easy local development
* Low operational burden
* Sufficient for Phase 1 usage
* Portable database file

#### Negative

* Limited concurrent write capacity
* Not ideal for multi-user deployment
* Certain database features differ from PostgreSQL

### Revisit When

Consider migration to PostgreSQL when:

* Multiple users are introduced
* Concurrent background processing becomes significant
* The application is hosted for remote access
* Database size or query complexity materially increases

---

## ADR-006: Store Articles and Learning Notes Separately

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

An article represents source material and provenance.

A Learning Note represents an AI-generated educational transformation of that source.

Combining them into a single database record would blur source data and generated interpretation.

### Decision

Articles and Learning Notes will be modeled as separate domain objects and separate database tables.

An Article may have a related Learning Note.

The Learning Note will store metadata such as model name and prompt version.

### Alternatives Considered

1. Store all data in one article record.
2. Store the Learning Note as a single JSON field.
3. Store Articles and Learning Notes separately.
4. Store only the generated note and discard article data.

### Rationale

Separate models preserve:

* Source provenance
* Processing history
* Regeneration capability
* Prompt and model version tracking
* Clear conceptual boundaries
* Future export to KOS

### Consequences

#### Positive

* Original and generated content remain distinct.
* Notes can be regenerated later.
* Article metadata remains reusable.
* The Learning Note can evolve independently.
* Future version comparison becomes possible.

#### Negative

* Persistence logic is slightly more complex.
* Database joins are required for complete article views.
* Schema migrations may be needed when the Learning Note evolves.

### Revisit When

Reconsider the relationship if the application later supports multiple Learning Notes per article, multiple analysis modes, or versioned note generation.

---

## ADR-007: Use Source-Neutral Article Interfaces

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The first content source is the Indian Express UPSC Current Affairs RSS feed.

However, the future roadmap may include PIB, PRS, RBI, Down To Earth, and other sources.

Embedding Indian Express-specific structures throughout the application would make expansion difficult.

### Decision

The application will define source-neutral article candidate and source adapter interfaces.

Indian Express will be implemented as the first infrastructure adapter.

The application, analyzer, storage, and presentation layers will operate on source-neutral models.

### Alternatives Considered

1. Hardcode Indian Express throughout the application.
2. Build a full plugin framework for sources.
3. Use a small source interface with one initial adapter.

### Rationale

A small interface provides sufficient extensibility without introducing a premature plugin system.

### Consequences

#### Positive

* Additional sources can be added with limited changes.
* Source-specific parsing remains isolated.
* Core business logic remains reusable.
* Testing becomes easier using fake sources.

#### Negative

* Some interface design is required before multiple sources exist.
* Different sources may later require richer metadata than initially anticipated.

### Revisit When

Revisit the interface after adding the second real source.

Do not expand the abstraction based only on hypothetical future requirements.

---

## ADR-008: Use Trafilatura for Initial Article Extraction

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

RSS entries generally provide article metadata and links but may not include the complete article body.

The application requires clean text suitable for LLM analysis.

### Decision

Trafilatura will be used as the default article extraction library during Phase 1.

It will be wrapped behind an `ArticleExtractor` interface.

### Alternatives Considered

1. Trafilatura
2. Newspaper3k
3. Beautiful Soup with custom selectors
4. Browser automation
5. Use RSS descriptions only

### Rationale

Trafilatura is designed for extracting main text from web pages and usually requires less site-specific parsing than custom selectors.

Wrapping it behind an interface allows replacement if it performs poorly.

Browser automation would add significant complexity and is not required for publicly accessible pages.

### Consequences

#### Positive

* Rapid implementation
* Reduced custom parsing code
* Replaceable extraction implementation
* Suitable for multiple future sources

#### Negative

* Extraction quality may vary.
* Site layout changes may reduce reliability.
* Some pages may return incomplete or unusable text.

### Revisit When

Reconsider if extraction failures become frequent or article-specific parsing proves necessary.

---

## ADR-009: Do Not Implement Authentication or Paywall Circumvention

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The Indian Express RSS feed is publicly accessible.

Some linked articles may be fully accessible, partially accessible, or unavailable without a subscription.

Storing personal credentials or attempting to circumvent access controls would create security, maintenance, and compliance concerns.

### Decision

Phase 1 will process only content accessible through normal public HTTP requests.

The system will not:

* Request Indian Express login credentials
* Store passwords
* Automate login
* Reuse browser cookies
* Circumvent paywalls
* Attempt to defeat technical access controls

Unavailable articles will be recorded as extraction failures and skipped without stopping the batch.

### Alternatives Considered

1. Store personal login credentials.
2. Use exported browser cookies.
3. Use browser automation.
4. Process only publicly accessible content.

### Rationale

Public-content-only access keeps the MVP simple, safer, and easier to maintain.

It also prevents the project from depending on fragile authentication flows.

### Consequences

#### Positive

* No credential-security risk
* Simpler architecture
* Lower maintenance
* Clear lawful access boundary

#### Negative

* Some articles may not be processed.
* Extraction coverage may be incomplete.
* Alternative sources may eventually be required for inaccessible topics.

### Revisit When

Reconsider only if there is an officially supported API or documented access method that permits authenticated personal use without bypassing access restrictions.

---

## ADR-010: Require Structured and Validated LLM Output

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The dashboard and database require predictable Learning Note fields.

Free-form LLM responses are difficult to validate, store, test, and render reliably.

### Decision

The LLM must return structured output conforming to a defined schema.

Pydantic will validate the output.

Malformed or incomplete output will be rejected.

Recoverable format failures may trigger a bounded retry.

### Alternatives Considered

1. Accept free-form Markdown.
2. Parse headings from prose.
3. Require structured output and schema validation.
4. Store raw model responses without validation.

### Rationale

Structured validation provides:

* Reliable persistence
* Predictable UI rendering
* Testable contracts
* Safer downstream automation
* Easier future KOS integration

### Consequences

#### Positive

* Consistent Learning Notes
* Clear provider contract
* Easier error handling
* Stronger automated tests
* Reduced downstream parsing

#### Negative

* LLM calls may fail validation.
* Prompt design becomes more demanding.
* Retries may increase API usage.
* Schema evolution requires migration planning.

### Revisit When

Reconsider the schema when real usage shows that important educational content is missing or current fields are routinely empty.

---

## ADR-011: Keep Prompt Templates Outside Python Source Files

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

Prompt wording will likely evolve frequently as output quality is tested.

Hardcoding prompts inside application code would mix behavioural configuration with implementation logic.

### Decision

LLM prompt templates will be stored in the `prompts/` directory.

Each material prompt revision should have a version identifier.

The generated Learning Note should store the prompt version used.

### Alternatives Considered

1. Hardcode prompts inside Python classes.
2. Store prompts in environment variables.
3. Store versioned prompt files in the repository.
4. Store prompts in a database.

### Rationale

Repository-based prompt files are:

* Easy to review
* Easy to version
* Easy to test
* Easy to modify
* Appropriate for a single-user local application

### Consequences

#### Positive

* Prompt evolution is traceable.
* Code remains cleaner.
* Model behaviour can be associated with a prompt version.
* Prompt files can be reviewed independently.

#### Negative

* Prompt loading must be implemented.
* File paths and packaging require care.
* Changing a prompt may alter output without changing Python code.

### Revisit When

Consider database-managed prompts only when the application needs runtime prompt editing, experiments, or multiple user-selectable analysis modes.

---

## ADR-012: Automated Tests Must Not Depend on Live Services

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

Live RSS feeds, websites, and LLM APIs are unreliable test dependencies.

They can cause failures due to network outages, content changes, rate limits, cost, or provider behaviour.

### Decision

Automated tests will use:

* Saved RSS fixtures
* Saved HTML fixtures
* Fake article sources
* Fake article extractors
* Fake LLM providers
* Temporary SQLite databases

A small number of manually invoked smoke tests may use live services.

### Alternatives Considered

1. Test everything against live services.
2. Mock all internal implementation details.
3. Test behaviour using fixtures and fakes.
4. Avoid integration tests.

### Rationale

Fixtures and fakes provide deterministic, fast, low-cost tests while still allowing realistic workflow testing.

### Consequences

#### Positive

* Reliable test suite
* No API cost during tests
* Offline development
* Easier simulation of failures
* Faster feedback

#### Negative

* Fixtures may become outdated.
* Live behaviour can differ from test data.
* Manual smoke testing remains necessary.

### Revisit When

Add controlled contract tests if source or provider changes frequently and fixture drift becomes a recurring issue.

---

## ADR-013: Use Server-Rendered Pages for the Phase 1 Dashboard

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The Phase 1 dashboard requires simple browsing and reading of stored Learning Notes.

It does not require complex client-side state, real-time collaboration, or advanced interactivity.

### Decision

The dashboard will use FastAPI with server-rendered templates.

A separate React, Next.js, or other frontend application will not be introduced in Phase 1.

### Alternatives Considered

1. FastAPI with server-rendered templates
2. React frontend
3. Next.js application
4. Streamlit
5. Desktop application

### Rationale

Server-rendered pages minimize:

* Tooling complexity
* Build configuration
* API duplication
* Frontend state management
* Deployment overhead

They are sufficient for a personal study dashboard.

### Consequences

#### Positive

* One application
* Simple local execution
* Faster implementation
* Easier testing
* Minimal frontend tooling

#### Negative

* Limited client-side interactivity
* UI may need partial replacement for advanced future features
* Rich visualization may be harder later

### Revisit When

Consider a richer frontend when the product requires:

* Interactive knowledge graphs
* Complex note editing
* Real-time search experiences
* Advanced study workflows
* Mobile-responsive application behaviour beyond simple layouts

---

# 5. Proposed Decisions for Sprint 0 Review

The following decisions should be confirmed or amended by Claude Code after inspecting the initial repository and proposing Sprint 0.

## ADR-014: Use `pyproject.toml` for Dependency and Tool Configuration

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

Python dependency management and development tools require configuration.

Keeping configuration distributed across multiple files may increase maintenance overhead.

Sprint 0 also required selecting the precise package manager, left open by the original proposal.

### Decision

Use `pyproject.toml` as the central configuration file for:

* Project metadata
* Dependencies
* Ruff
* MyPy
* Pytest
* Build configuration

The package manager is `uv`, with `uv.lock` committed for reproducible installs. The build backend is `hatchling`.

### Alternatives Considered

1. `pyproject.toml` with `uv` (selected)
2. `requirements.txt` plus separate tool files
3. Poetry-specific project configuration
4. Pipenv
5. Plain `pip` + `venv` with no lock file

### Rationale

`pyproject.toml` is the modern standard and centralizes configuration. `uv` provides a single fast tool for environment creation, dependency resolution, and lock-file management, natively driven by `pyproject.toml`. `hatchling` is a minimal, standard build backend requiring no additional configuration for a pure-Python package.

### Consequences

#### Positive

* Fewer configuration files
* Modern Python tooling compatibility
* Easier onboarding
* Reproducible installs via `uv.lock`

#### Negative

* Contributors without `uv` installed must use the documented `pip install -e ".[dev]"` fallback.
* Some deployment workflows may still generate lock or requirements files.

### Revisit When

Reconsider if `uv` adoption creates friction for contributors or deployment environments.

---

## ADR-015: Use Alembic for Database Migrations

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The database schema will evolve as Article and Learning Note models develop.

Automatic table creation alone does not provide a reliable upgrade path.

This decision was left `Proposed` pending Sprint 4, where `docs/ROADMAP.md` §7
explicitly requires "migrations rather than relying only on automatic table
creation." Sprint 4 planning initially proposed deferring Alembic in favor of
`Base.metadata.create_all()` on simplicity grounds (CLAUDE.md §7/§25), but the
roadmap's explicit requirement was confirmed as authoritative and this ADR is
finalized as accepted, not superseded.

### Decision

Use Alembic for SQLite schema migrations, starting with a single baseline
revision (`3318676bf824`) that creates the complete Sprint 4 schema
(`articles` and `learning_notes`). `Base.metadata.create_all()` is not used as
the schema-initialization path for the real database; it remains available
only as a convenience for constructing ORM row objects in mapper unit tests
that need no database at all.

### Alternatives Considered

1. Alembic (selected)
2. SQLAlchemy automatic `create_all`
3. Custom SQL migration scripts
4. Recreate the local database after every schema change

### Rationale

Alembic integrates with SQLAlchemy and provides a documented, repeatable path
for schema evolution. `docs/ROADMAP.md` §7 requires migrations explicitly for
Sprint 4; that requirement is more specific than CLAUDE.md's general
simplicity preference and is not overridden by it.

### Consequences

#### Positive

* Repeatable schema upgrades
* Better production discipline
* Easier future PostgreSQL migration
* A single baseline revision gives the project a real upgrade/downgrade path
  from the very first schema, rather than retrofitting one later

#### Negative

* Additional setup: `alembic.ini`, `migrations/env.py`,
  `migrations/script.py.mako`, and a versions directory
* Migration files must be kept in sync with `app/infrastructure/orm_models.py`
  by hand (the baseline revision was hand-written to match the ORM models
  exactly, not autogenerated against a live database, to avoid connecting to
  any database - including the real development database - during authoring)
* SQLite migration limitations require care (for example, SQLite's limited
  `ALTER TABLE` support will constrain how future revisions can be written)
* `logging.config.fileConfig()` in `migrations/env.py` must be called with
  `disable_existing_loggers=False`; the default silently disables every
  logger already configured in the process, including the application's own
  module loggers and pytest's `caplog` handler, since Alembic commands run
  inside the same test process as the rest of the suite

### Revisit When

Revisit if SQLite's `ALTER TABLE` limitations make a future migration
impractical to express through Alembic's SQLite batch mode, or if the project
migrates to PostgreSQL (see ADR-005).

---

## ADR-016: Nest Application Layers Under `app/`

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

`docs/ENGINEERING_SPEC.md` §4 depicts `domain/`, `application/`, `infrastructure/`, and `presentation/` as top-level directories alongside `app/`. `docs/ROADMAP.md` §3's Sprint 0 "Suggested Project Structure" nests those same four layers inside `app/`. The two documents describe the same layering but disagree on directory nesting, and Sprint 0 required a single, unambiguous structure before any code could be written.

### Decision

The four architectural layers are implemented as subpackages of `app/`:

```text
app/
├── domain/
├── application/
├── infrastructure/
└── presentation/
```

`ENGINEERING_SPEC.md`'s layering rules (dependency direction, what each layer may and may not import) apply unchanged; only the physical nesting differs from its diagram.

### Alternatives Considered

1. Flat top-level layer directories, as literally diagrammed in `ENGINEERING_SPEC.md` §4.
2. Nested layers under `app/`, as diagrammed in `ROADMAP.md` §3 (selected).

### Rationale

`ROADMAP.md`'s structure is the more specific, sprint-scoped instruction, and nesting under `app/` keeps all application code under one importable package root, which is the more common convention and requires no `PYTHONPATH`/packaging workaround. The choice is cosmetic with respect to the mandatory layering and dependency rules — both documents require the same isolation between layers.

### Consequences

#### Positive

* Removes ambiguity that would otherwise recur every time a new module is added.
* Single importable root package (`app`) simplifies imports and packaging.

#### Negative

* Diverges from the literal diagram in `docs/ENGINEERING_SPEC.md` §4, which is not itself updated by this decision.

### Revisit When

Revisit only if a future sprint finds a concrete reason the nested layout impedes packaging or deployment.

---

## ADR-017: Domain Models Use Pydantic v2 with UUID Identities and Timezone-Aware UTC Timestamps

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

Sprint 1 requires strongly typed, validated domain models (`ArticleCandidate`, `Article`, `ExtractedArticle`, `LearningNote`, `PrelimsQuestion`, `MainsQuestion`) with no dependency on SQLAlchemy or FastAPI. Three cross-cutting representation questions apply to all of them: what validates the models, how object identity is represented, and how timestamps are represented.

### Decision

* All domain models are ordinary (non-frozen) Pydantic v2 `BaseModel` classes. Freezing was considered and rejected: frozen models still contain mutable `list` fields, so freezing provides only partial, misleading immutability while adding friction for future application-layer code that updates entity state (e.g. `Article.processing_status`).
* Identity fields use Python's native `UUID` type generated via `Field(default_factory=uuid4)` (`Article.id`, `LearningNote.id`, `LearningNote.article_id`), letting Pydantic handle parsing, validation, and JSON serialization natively. No custom ID-generation or ID-validation helper is introduced.
* All timestamp fields are timezone-aware `datetime` values. A shared `ensure_utc` validator rejects naive datetimes and normalizes any aware datetime to UTC; a shared `utc_now()` factory is the canonical source of "now" for `created_at`/`updated_at`/`extracted_at` defaults.
* All domain models inherit a shared `DomainModel` base (`app/domain/base.py`) configuring `extra="forbid"` (unknown fields rejected) and `validate_assignment=True` (attribute reassignment is revalidated, not just initial construction).
* Cross-field invariants that must hold after attribute assignment (`Article.created_at`/`updated_at` ordering; `ExtractedArticle.status`/`text`/`error_reason` consistency) are implemented as field-level (`field_validator` with `ValidationInfo.data`) or `model_validator(mode="before")` checks rather than `model_validator(mode="after")`. An `after` model validator runs once the candidate value has already been written into the model's `__dict__`; if it then raises, the instance can be left mutated despite the `ValidationError`. Validating from the proposed field state *before* it is committed keeps a rejected assignment fully transactional — the previous valid values are retained.

### Alternatives Considered

1. Frozen Pydantic models for value-object semantics (rejected — false immutability with mutable list fields).
2. UUID-formatted `str` fields with custom generation/validation helpers (rejected — duplicates what Pydantic already validates natively for `UUID`).
3. Naive or locally-timed datetimes with conversion at the infrastructure boundary (rejected — pushes UTC discipline out of the domain layer where CLAUDE.md requires it).

### Rationale

Pydantic v2 is already the project's required validation library (CLAUDE.md §10–11) and needs no additional justification. Native `UUID` fields are simpler and less error-prone than hand-rolled string validation, and are trivially serializable. UTC-only, timezone-aware timestamps prevent an entire class of bugs (ambiguous local time, silent naive/aware mixing) at model-construction time rather than downstream.

### Consequences

#### Positive

* No custom ID or timestamp validation code to maintain beyond one small shared `app/domain/validation.py` module.
* Naive-datetime bugs are caught immediately at construction, not at persistence or display time.
* `UUID` fields serialize predictably through Pydantic/FastAPI without extra adapters.

#### Negative

* Mutable domain models mean application-layer code (future sprints) must be disciplined about not mutating shared instances unexpectedly; no compiler/runtime enforcement of immutability exists in Sprint 1.
* Every aware-but-non-UTC datetime is silently converted to UTC rather than rejected, which is intentional but should be understood by future contributors.
* `validate_assignment=True` validates *attribute reassignment* (`article.processing_status = ...`), not in-place mutation of a field's contents. `article.categories.append("x")` mutates the list object directly and triggers no validation at all; only assigning a whole new list (`article.categories = [...]`) is checked. Future sprints that mutate list-valued fields in place must not assume validation runs.

### Revisit When

Reconsider mutability if a future sprint introduces concurrent or shared mutable references to the same domain instance and bugs result. Reconsider UUID-as-string only if a KOS integration boundary requires a different identity format.

---

## ADR-018: Closed `GSPaper` Enum and Fixed Four-Option `PrelimsQuestion` Contract

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

`LearningNote.gs_papers` and `PrelimsQuestion.options` are both fields where ROADMAP/PRD describe the concept but do not specify an exact representation. Left unconstrained, `gs_papers` could be free-form strings (inconsistent values like `"GS 1"` vs `"gs1"` vs `"General Studies I"`), and `PrelimsQuestion.options` could vary in length in ways that don't match the real UPSC Prelims MCQ format.

### Decision

* `GSPaper` is a closed `StrEnum` with exactly four members: `GS1`, `GS2`, `GS3`, `GS4`. `LearningNote.gs_papers: list[GSPaper]` rejects any other value.
* `PrelimsQuestion.options` must contain exactly 4 non-empty, non-duplicate strings, and `correct_option` must be a valid index into that list (`0 <= correct_option < 4`).

### Alternatives Considered

1. Free-form `list[str]` for `gs_papers` (rejected — permits inconsistent values that break dashboard filtering, planned in Sprint 7).
2. Variable-length `options` (e.g. 2–6) to accommodate hypothetical non-standard question formats (rejected — the real UPSC Prelims format is always 4 options; variability would only mask malformed LLM output later).

### Rationale

A closed enum for GS papers gives every future consumer (dashboard filters, LLM output validation in Sprint 5) a single guaranteed vocabulary instead of ad hoc string matching. Fixing `PrelimsQuestion` at exactly 4 options matches the real exam format and turns a malformed LLM response into an immediate, loud validation failure instead of a silently-accepted malformed question — directly satisfying ROADMAP §4's acceptance criterion that "invalid question structures are rejected."

### Consequences

#### Positive

* Dashboard GS-paper filtering (Sprint 7) can rely on a fixed, known set of values with no normalization step.
* Malformed Prelims MCQs from the future LLM generator (Sprint 5) fail validation immediately rather than reaching storage or the UI.

#### Negative

* If UPSC current affairs content ever maps to a paper outside GS1–GS4 (e.g. Essay paper), the enum must be extended before that content can be represented.
* If a future prompt design produces a legitimately different option count, this contract must be revisited before that content can be stored.

### Revisit When

Reconsider `GSPaper` if a genuine need arises to classify content under Essay or another non-GS paper. Reconsider the four-option rule only if real LLM-generated question sets show a valid need for a different option count.

---

## ADR-019: Use a Synchronous Application-Layer `ArticleSource` Port for Phase 1

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

Sprint 2 introduces the first source adapter (`IndianExpressRSSSource`) and needs a stable contract that application-layer workflows can depend on instead of the concrete Indian Express implementation. Two questions needed settling before writing code: which layer owns the interface and its error type, and whether discovery should be synchronous or asynchronous.

### Decision

* `ArticleSource` (a `Protocol` with `discover_articles(self) -> list[ArticleCandidate]`) and `ArticleSourceError` both live in `app/application/sources.py`. This mirrors `CLAUDE.md`'s treatment of `LearningNoteGenerator` as an "application-facing interface": the port expresses a workflow-level contract, not a domain concept, so it belongs in the application layer rather than `app/domain/`.
* `app/infrastructure/rss_source.py` implements the port structurally — `IndianExpressRSSSource` does not inherit from `ArticleSource` — and raises `ArticleSourceError` on failure. The exception is defined in the application layer specifically so that future application orchestration code can catch source failures without importing an Indian Express-specific infrastructure module.
* `discover_articles()` is synchronous. Phase 1 has exactly one source and one blocking feed fetch per call; both `httpx` (used synchronously) and `feedparser` are synchronous APIs, and nothing in the current pipeline performs concurrent discovery across multiple sources.

### Alternatives Considered

1. Define `ArticleSource`/`ArticleSourceError` in `app/domain/` (rejected — the domain layer should stay a pure data-shape layer with no notion of "source" or "adapter" as a concept; `ArticleCandidate` itself is domain, the port around it is not).
2. Define `ArticleSourceError` inside `app/infrastructure/rss_source.py` (rejected — this would force any future application-layer error handling to import an Indian Express-specific infrastructure module just to catch a generic discovery failure).
3. An `async def discover_articles()` port (rejected for Phase 1 — no current concurrency requirement; would add an async surface with no present consumer).

### Rationale

Keeping the port and its error type together in the application layer, decoupled from any concrete adapter, lets a future `ProcessNewsFeedService` (Sprint 6) depend only on `app.application.sources` — never on `app.infrastructure.rss_source` — matching ADR-007's source-neutral interface goal. Staying synchronous avoids introducing async machinery (event loops, awaitable interfaces) before any real concurrency need exists, consistent with CLAUDE.md's simplicity rules.

### Consequences

#### Positive

* Application code and tests can depend on `app.application.sources` alone.
* No async infrastructure is introduced prematurely.
* The same pattern (port + error in `app/application/`) can be reused for `ArticleExtractor` (Sprint 3) and `LearningNoteGenerator` (Sprint 5) without re-litigating layer placement.

#### Negative

* If a later phase needs concurrent discovery across multiple sources, `discover_articles()` and its callers will need to be revisited together.

### Revisit When

Reconsider synchronous execution only when a real concurrency requirement appears (for example, multiple sources fetched concurrently). Deduplication policy, HTTP client ownership, and feed-entry field mapping are documented in code and tests (`app/infrastructure/rss_source.py`, `tests/infrastructure/test_rss_source.py`) and in the README rather than as separate ADRs, since they are implementation-level choices rather than decisions expected to be revisited independently.

---

## ADR-020: Synchronous ArticleExtractor Port with Status-Based Outcomes

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

Sprint 3 introduces the first article-extraction adapter
(`TrafilaturaArticleExtractor`) and needs a stable contract that a future
application workflow can depend on instead of the concrete Trafilatura
implementation. This mirrors the situation ADR-019 already settled for
`ArticleSource`, but with one important difference: `ExtractedArticle`
(defined in Sprint 1) is a validated domain model whose `url` field only
accepts a valid absolute HTTP/HTTPS URL, so an invalid `url` argument cannot
be represented as an `ExtractedArticle` value at all. This forced an
explicit decision about which failures belong in the domain result and
which belong in the caller contract, in addition to the layer-placement and
sync-vs-async questions ADR-019 already answered the same way.

### Decision

* `ArticleExtractor` (a `Protocol` with `extract(self, url: str) ->
  ExtractedArticle`) lives in `app/application/extraction.py`, following the
  same application-layer placement as `ArticleSource` (ADR-019) and for the
  same reason: it expresses a workflow-level contract, not a domain concept.
  No application exception type is defined alongside it.
* `extract()` is synchronous, for the same reasons ADR-019 gives for
  `discover_articles()`: one blocking `httpx` call per article, Trafilatura's
  API is synchronous, and there is no current concurrency requirement.
* `app/infrastructure/trafilatura_extractor.py` implements the port
  structurally (`TrafilaturaArticleExtractor` does not inherit from
  `ArticleExtractor`), using Trafilatura 2.x as the extraction library behind
  it — Trafilatura itself was already selected in ADR-008; this decision
  does not revisit that choice, only how the library is wrapped.
* **Invalid URLs raise `ValueError` and make no HTTP request**, unlike
  `ArticleSourceError` for RSS discovery failures. An invalid `url` argument
  is treated as a caller contract violation (the type signature already says
  `url: str`, and Sprint 3 requires it to additionally be a non-blank,
  absolute http(s) URL with a network location) rather than an operational
  outcome, because `ExtractedArticle.url` cannot hold an invalid value — the
  domain model was deliberately not modified to accommodate one.
* **Every outcome after a valid URL is accepted is returned as an
  `ExtractedArticle`**, never raised. This includes an unexpected failure
  inside Trafilatura or the post-processing step, mapped to
  `ExtractionStatus.UNEXPECTED_ERROR` with the traceback logged
  (`exc_info=True`) but a concise, non-sensitive `error_reason` returned to
  the caller. This is the opposite choice from ADR-019, which raises
  `ArticleSourceError` for RSS failures — the two adapters differ because
  `ArticleSource.discover_articles()` returns a `list[ArticleCandidate]`
  with no per-item failure channel, while `ExtractedArticle.status` already
  exists specifically to carry a per-article outcome. Routing extraction
  failures through it (rather than a parallel exception type) means a future
  batch orchestrator (Sprint 6) can handle every extraction outcome,
  expected or not, the same way: inspect `status`, log, and continue to the
  next article, with no per-article `try/except` required.
* Phase 1 has no public or untrusted URL-submission entry point.
  `extract(url)` is only ever called by internal application workflows on
  URLs that already passed `ArticleCandidate`/`Article` validation upstream.
  Accordingly, Sprint 3 does not add DNS resolution, IP-range filtering, or
  redirect-target validation — see the Consequences section.

### Alternatives Considered

1. Represent an invalid URL as `ExtractedArticle(status=UNSUPPORTED_PAGE,
   ...)` (rejected — `ExtractedArticle.url` is validated by
   `validate_http_url` and cannot hold a blank, relative, or non-http(s)
   value; constructing the result would itself fail domain validation).
2. Loosen `ExtractedArticle.url` to accept arbitrary strings so invalid URLs
   could be represented as a status (rejected — this dilutes a Sprint 1
   domain invariant for a Sprint 3 convenience, and CLAUDE.md directs that
   domain models are not modified merely to accommodate a new adapter).
3. Define an `ArticleExtractionError` application exception, paralleling
   `ArticleSourceError`, for all extraction failures including expected
   operational ones (rejected — `ExtractedArticle.status` already exists to
   carry exactly this information; a parallel exception type would give
   callers two failure channels to handle for the same class of outcome).
4. Add SSRF hardening (DNS/IP-range/redirect-target checks) now, ahead of
   any untrusted URL input path (rejected as premature for Phase 1 — see
   Consequences; to be revisited when a concrete untrusted-input trigger
   appears).

### Rationale

Keeping the port in the application layer and decoupled from Trafilatura
lets a future `ProcessNewsFeedService` (Sprint 6) depend only on
`app.application.extraction`, matching the pattern ADR-019 already
established for `ArticleSource`. Raising `ValueError` for invalid URLs
(rather than stretching the domain model or inventing a new exception type)
keeps the boundary honest: a malformed argument is a programming error at
the call site, not something that happened while extracting a page, and
CLAUDE.md's domain-modeling rules do not permit relaxing an existing
validated field to accommodate it. Routing every outcome after a valid URL
through `ExtractedArticle.status` — including genuinely unexpected failures
— satisfies CLAUDE.md §13's requirement that "one failed article must not
stop the entire batch": a future batch caller never needs a
`try/except ArticleExtractionError` around each `extract()` call.

### Consequences

#### Positive

* Application code and tests can depend on `app.application.extraction`
  alone, never on `app.infrastructure.trafilatura_extractor`.
* A single, uniform per-article handling pattern (`status` inspection) will
  work for Sprint 6's batch orchestration regardless of failure cause.
* The domain model's existing invariants (Sprint 1) remain untouched and
  fully enforced; Sprint 3 adapts to them rather than the reverse.

#### Negative

* A caller that passes an unvalidated URL straight through to `extract()`
  must be prepared to catch `ValueError`, unlike the fully status-based
  RSS-discovery path — this asymmetry between the two ports must be
  understood by whoever writes Sprint 6's orchestration code.
* No loopback/private-address/redirect-target protection exists yet. This is
  safe only because Phase 1 has no public URL-submission endpoint and no
  other untrusted-input path to `extract()`; it must be revisited before any
  future manual article-submission API, public endpoint, or other feature
  that accepts a URL from an untrusted source.

### Revisit When

Reconsider the exception-vs-status split if a future sprint finds a
genuinely operational failure mode that doesn't fit `ExtractionStatus`.
Reconsider the absence of SSRF hardening the moment any untrusted or
public-facing URL input path is introduced (per CLAUDE.md §23, no such path
exists in Phase 1: no authentication, no multi-user input, no manual
article submission).

---

## ADR-021: SQLite Persistence through Application Repository Ports and Explicit Domain/ORM Mapping

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

Sprint 4 introduces the first persistence layer: `Article` and `LearningNote`
must be stored in and retrieved from SQLite, with cross-run deduplication and
a Learning Note relationship, following the same "port in the application
layer, concrete adapter in infrastructure" pattern ADR-019 and ADR-020 already
established for `ArticleSource` and `ArticleExtractor`. This is the first ADR
to address database technology choices beyond ADR-005 (SQLite for Phase 1)
and ADR-006 (Articles and Learning Notes stored separately), which this
decision extends rather than revisits.

Three additional questions were specific to persistence and needed settling:
how repository contracts should be shaped and where they live, how domain
models remain ignorant of SQLAlchemy, and how a domain gap discovered during
planning (`Article` had no field to record a failure reason) should be
resolved.

### Decision

* **Synchronous SQLAlchemy 2.x.** `app/infrastructure/database.py` exposes
  `create_engine_from_url(url)` and `create_session_factory(engine)`, both
  taking an explicit URL rather than reading `Settings` themselves. No table
  creation or migration runs on import.
* **Application-layer repository Protocols.** `ArticleRepository` and
  `LearningNoteRepository` (both `Protocol`s), plus `ArticleWithLearningNote`
  and the repository error types, live in `app/application/repositories.py` -
  the same placement pattern as `ArticleSource` (ADR-019) and `ArticleExtractor`
  (ADR-020). `SQLiteArticleRepository`/`SQLiteLearningNoteRepository` in
  `app/infrastructure/sqlite_repositories.py` implement them structurally, no
  inheritance.
* **Infrastructure-only ORM models.** `ArticleRow`/`LearningNoteRow` in
  `app/infrastructure/orm_models.py` are plain SQLAlchemy 2.x typed
  declarative models (`Mapped[...]`/`mapped_column(...)`), with every
  constraint explicitly named (primary keys, unique constraints, the
  `learning_notes.article_id` foreign key with `ON DELETE CASCADE`, and the
  `processing_status` check constraint). They import nothing from
  `app/domain/`, and nothing outside `app/infrastructure/` imports them.
* **Explicit mapping functions, not `session.merge()`.**
  `app/infrastructure/mappers.py` provides pure functions -
  `article_to_row`/`row_to_article`, `learning_note_to_row`/
  `row_to_learning_note`, and `update_row_from_article` (which updates an
  existing row's domain-backed columns individually rather than replacing the
  row wholesale). List/dict values are always copied on both directions, so
  mutating a returned domain object can never reach back into ORM/session
  state. SQLite has no native timezone storage, so every datetime read from a
  row is reconstructed as UTC-aware before it reaches a domain model, whose
  own validators reject naive datetimes outright.
* **JSON-per-structured-field, not one blob.** Every `LearningNote` list field
  - including the nested `prelims_questions` and `mains_questions` - has its
  own JSON column, extending ADR-006's "no opaque blob" principle down to the
  note's internal structure, not just the Article/LearningNote split.
* **Database constraints are the final deduplication boundary.** `articles`
  has named unique constraints on `url` and on `(source, external_id)`
  (SQLite permits repeated `NULL external_id` values under a composite unique
  index, which is the desired behavior for feed entries with no GUID).
  `add()` does not pre-check existence; a violation is caught and translated
  by inspecting the underlying SQLite integrity-error message, never assumed
  from context. This message inspection is adapter-specific to SQLite and is
  exercised by integration tests, not mocked. Every repository method also
  catches the broader `SQLAlchemyError` (covering `OperationalError` from a
  locked or unavailable database, not just `IntegrityError`) and wraps it in
  a generic `RepositoryError` - an unrecognized failure is never mislabeled
  as a duplicate. The engine is created with `hide_parameters=True`, so
  article or Learning Note content bound as SQL parameters can never appear
  in an exception's string representation or a log line derived from it.
* **Alembic, per ADR-015 (now Accepted).** A single baseline revision
  (`3318676bf824`) creates the complete Sprint 4 schema; see ADR-015 for the
  migration-strategy decision itself.
* **No Unit of Work.** Each repository method opens its own session
  (`session_factory.begin()` for writes, `session_factory()` for reads) and
  owns its own transaction. Nothing in Sprint 4 needs a multi-aggregate atomic
  transaction spanning both repositories.
* **`Article.failure_reason` domain correction.** `Article` gained
  `failure_reason: str | None = None`, enforced transactionally: `FAILED`
  requires a non-empty, stripped reason; every other status requires `None`.
  This is a domain correction, not an ORM convenience: Sprint 1's `Article`
  had no way to represent why an article failed, which blocked Sprint 4's own
  "record failure messages" requirement and CLAUDE.md §14's "never fail
  silently." The invariant is enforced the same way `ExtractedArticle`
  enforces its status/text/error_reason consistency (ADR-017's pattern): a
  `model_validator(mode="before")`, so an invalid proposed state - including
  under `validate_assignment=True` - is rejected outright rather than applied
  and then flagged, preserving the model's previous valid state.
* **`ExtractedArticle` is not persisted as a separate entity.** No
  `extraction_status`/`extracted_at`/`extraction_error_reason` columns and no
  `record_extraction_result()` method exist. Sprint 4 persists only the
  `Article` domain state that already exists (`raw_text`, `processing_status`,
  `failure_reason`, `updated_at`) via `update()`. A future orchestration
  sprint decides how an `ExtractedArticle` result changes an `Article`; the
  repository persists that resulting `Article` without making the workflow
  decision itself.

### Alternatives Considered

1. `add()` returning the inserted `Article` (rejected - `Article.id` is
   client-generated via `uuid4()`, so there is nothing new for the repository
   to hand back).
2. An `exists()` repository method (rejected - invites the exact
   check-then-insert race the unique-constraint boundary is meant to avoid).
3. A single `save()` method covering both insert and update (rejected for
   `ArticleRepository` - `add()`/`update()` express materially different
   failure modes, duplicate vs. not-found; kept as `add()`-only for
   `LearningNoteRepository` since Phase 1 allows only one note per article and
   there is no update use case yet).
4. Storing `extraction_status`/`extracted_at`/`extraction_error_reason` as
   infrastructure-only columns on `articles` (rejected - this would duplicate
   `failure_reason`'s purpose, split a single logical update across two
   repository calls and two transactions, and risk a later successful
   extraction's metadata being silently overwritten by an unrelated call;
   removed in favor of persisting only `Article`'s own accepted domain state).
5. A separate one-to-one `article_extractions` table (rejected for the same
   reason, and because Sprint 4 needs only latest state, not history).
6. Translating every `IntegrityError` into `DuplicateArticleError` (rejected -
   an unrecognized integrity failure must surface as a generic
   `RepositoryError`, not a misleading duplicate error).

### Rationale

Keeping repository Protocols in `app/application/` and concrete adapters in
`app/infrastructure/` extends a pattern already proven twice (ADR-019,
ADR-020), so a future orchestration service (Sprint 6) can depend on
`app.application.repositories` alone. Explicit mapping functions - rather than
`session.merge()` or direct ORM/domain coupling - keep the translation
boundary auditable and testable without a database, and make the UTC
datetime reconstruction and list-copying rules impossible to skip by
accident. Database constraints as the deduplication boundary (rather than
application-level pre-checks) directly satisfies CLAUDE.md §12's instruction
to prefer them as "the final correctness boundary." The `failure_reason`
addition and the decision not to persist `ExtractedArticle` separately were
both approved amendments to the original Sprint 4 plan, made explicitly to
keep persisted state a faithful mirror of validated domain state rather than
inventing parallel infrastructure-only state the domain layer cannot
represent or reconstruct.

### Consequences

#### Positive

* A future orchestration service depends only on
  `app.application.repositories`, never on SQLAlchemy or SQLite directly.
* Mapper unit tests run with no database at all, keeping the fast majority of
  persistence-layer test coverage database-free.
* `Article.failure_reason`'s transactional invariant means a `FAILED` article
  can never be persisted, or reconstructed, without a reason.
* Removing extraction-specific columns keeps `articles` a direct reflection of
  `Article`'s own fields, with no infrastructure-only state a reader of the
  domain model would not expect.

#### Negative

* `update()` and any future `record`-style write remain caller-decided: the
  repository will faithfully persist a business-transition decision it does
  not itself make, so a future orchestration bug could still write an
  inconsistent `Article` state - the repository only guarantees the
  invariants `Article` itself enforces at construction time.
* No cross-repository transaction atomicity exists yet between
  `ArticleRepository.update()` and `LearningNoteRepository.add()`; a future
  sprint needing both to commit together will need a small Unit-of-Work
  addition at that point, not before.
* Alembic's baseline revision is hand-written to mirror
  `app/infrastructure/orm_models.py` rather than autogenerated, so the two
  must be kept in sync manually until a second revision establishes a
  generate-and-review workflow.

### Revisit When

Revisit the no-Unit-of-Work decision when a future sprint needs an atomic
write spanning both `ArticleRepository` and `LearningNoteRepository` in one
transaction. Revisit the "no extraction-specific persistence" decision only if
a future sprint has a concrete requirement for extraction-attempt history,
which Sprint 4 explicitly does not have.

---

## ADR-022: Structured Learning Note Generation through OpenAI Responses

**Status:** Accepted
**Date:** 2026-07-15
**Decision Owner:** Musa / Claude Code

### Context

Sprint 5 introduces the first LLM-backed component: transforming an
`Article`'s extracted text into a validated `LearningNote`, following the
same "port in the application layer, concrete adapter in infrastructure"
pattern ADR-019/020/021 already established for `ArticleSource`,
`ArticleExtractor`, and the persistence repositories. Two questions were
specific to this sprint and needed settling before writing code: how to stop
LLM output from ever controlling trusted identity/provenance metadata, and
how to use the OpenAI Python SDK correctly given it had moved to a new major
version (2.x) since before this project's dependencies were last reviewed.

### Decision

* **`LearningNoteGenerator`** (a `Protocol` with `generate(self, article:
  Article) -> LearningNote`) lives in `app/application/learning_notes.py`,
  the same placement pattern as every prior port. `article.raw_text is
  None`, blank, or whitespace-only raises `ValueError` before any prompt
  rendering or provider request - a caller contract violation, not an
  operational outcome, mirroring ADR-020's treatment of an invalid `url`.
  The generator does not validate `article.processing_status`; deciding
  when an `Article` is ready for analysis is a future orchestration
  concern.
* **`LearningNoteContent`**, added beside `LearningNote` in
  `app/domain/learning_note.py`, contains exactly the 15 AI-authored fields
  with **no defaults** - OpenAI Structured Outputs requires every field
  present in every response, so an irrelevant category must be returned as
  an explicit empty list by the model, never omitted and backfilled
  locally. It has no `id`, `article_id`, `model_name`, `prompt_version`, or
  `created_at` fields, so the model cannot influence trusted metadata by
  construction, not convention. It is a sibling of `LearningNote`, not a
  superclass or subclass - touching the already-shipped, Sprint-4-migrated
  `LearningNote` for a DRY-only refactor was rejected as unjustified scope
  creep. A parity test (`tests/domain/test_learning_note.py`) asserts
  `LearningNoteContent`'s field set exactly equals `LearningNote`'s fields
  minus trusted metadata, so the two cannot silently drift.
* **`assemble_learning_note()`**, a pure function in
  `app/application/learning_notes.py`, builds the final `LearningNote` using
  explicit, individually named keyword arguments for every field - never a
  `**dict` spread of validated content - so there is no path through which
  a future content field could accidentally collide with or override a
  trusted one. `id` and `created_at` use `LearningNote`'s own domain
  defaults unless `created_at` is explicitly injected for deterministic
  tests.
* **OpenAI is the sole Phase 1 provider** (extending ADR-008's precedent of
  naming one Phase 1 library rather than building a multi-provider
  abstraction), accessed exclusively through the **Responses API**'s native
  structured-output parsing: `client.responses.parse(model=..., input=...,
  text_format=LearningNoteContent)`, reading `response.output_parsed`.
  There is no Chat Completions fallback, no manual JSON parsing, no
  Markdown-fence stripping, no regex extraction. Pydantic (via the SDK's
  own use of `model_validate_json` inside `.parse()`) remains the sole
  validator.
* **Before writing any response-handling code, the installed `openai==2.45.0`
  package's own source was read directly** (`OpenAI.__init__`,
  `Responses.parse`, `ParsedResponse`, `Response.status`,
  `IncompleteDetails`, `ResponseOutputRefusal`, the `_exceptions.py`
  hierarchy) rather than relying on training-data memory or partially
  blocked documentation fetches. This confirmed, among other things, that
  `LengthFinishReasonError`/`ContentFilterFinishReasonError` belong only to
  the older Chat Completions parsing path - the Responses API represents
  incompleteness as data (`response.status == "incomplete"` +
  `response.incomplete_details.reason`), not a raised exception - and that
  a `pydantic.ValidationError` genuinely can propagate directly out of
  `client.responses.parse()` itself (from `parse_text()`'s
  `model_validate_json` call), which is the primary retry trigger.
* **Exactly three total validation attempts** (one original, up to two
  repair retries). Retried only for a `pydantic.ValidationError` raised
  during parsing, or a completed, non-refusal response with no parsed
  content. Never retried: invalid input (never reaches the loop), a typed
  refusal, `status == "incomplete"` (`max_output_tokens` or
  `content_filter`), or any `openai.OpenAIError` (transport, auth,
  permission, rate limit, server error) - each becomes an immediate
  `LearningNoteProviderError`. The OpenAI SDK's own transport-level retry
  (`max_retries`, explicitly set to 2 at client construction, matching the
  SDK default) operates entirely beneath and separately from this loop.
  Repair instructions sent back to the model contain only sanitized
  Pydantic error `type`/`loc`/`msg` fields (`errors(include_input=False)`)
  - never the rejected value.
* **Reusable client, narrow typed test seam.** The adapter owns a long-lived
  `openai.OpenAI` client (a deliberate difference from the short-lived
  `httpx.Client`-per-call pattern in `IndianExpressRSSSource`/
  `TrafilaturaArticleExtractor`, justified because the OpenAI SDK's client
  is explicitly designed as a reusable, connection-pooling object). The
  only test seam is `_ResponsesClient`, an infrastructure-private
  structural `Protocol` covering just the `.parse(model=..., input=...,
  text_format=...)` surface this adapter calls - not a second
  application-facing provider abstraction, and not a fake
  `LearningNoteGenerator`. The constructor requires **exactly one** of
  `api_key` or `responses`, raising `ValueError` for both or neither,
  rather than defining an implicit precedence rule between them.
* **External, version-derived prompt files.** `prompts/learning_note_v1_system.txt`
  and `prompts/learning_note_v1_user.txt`, loaded and rendered with stdlib
  `string.Template` (`$identifier` placeholders, `.substitute()` -
  never `.safe_substitute()`). `PROMPT_VERSION = "v1"` is a single source of
  truth: both filenames are derived from it, so bumping the version without
  adding the corresponding files fails immediately with a clear
  `FileNotFoundError` rather than silently reusing a stale prompt.
  `load_prompt_template()` validates a template's exact placeholder set
  before any provider request - an unknown or missing placeholder, an empty
  file, or a missing file all fail loudly.
* **No persistence or pipeline wiring.** `generate()` returns a
  `LearningNote`; nothing calls `LearningNoteRepository`, nothing updates
  `Article.processing_status`, and no application service connects
  discovery, extraction, or persistence to analysis. That is explicitly a
  future orchestration sprint's responsibility.

### Alternatives Considered

1. Letting the LLM populate the complete persisted `LearningNote` schema
   directly, including `id`/`article_id`/`model_name`/`prompt_version`/
   `created_at` (rejected - lets untrusted model output determine identity
   and provenance metadata).
2. `LearningNote(LearningNoteContent)` inheritance to eliminate duplicated
   field-validator registrations (rejected - no concrete correctness defect
   justifies touching the already-shipped `LearningNote`; the sibling model
   plus explicit-keyword assembly already prevents both duplication of
   validation logic, since both models call the same shared
   `app.domain.validation` helpers, and conversion errors).
3. Chat Completions `.parse()` as the primary or fallback API (rejected per
   explicit instruction - Responses API only, to avoid maintaining two
   response-handling code paths for one provider).
4. A broad `client: OpenAI | None` constructor parameter with monkeypatched
   internals for testing (rejected - untyped, encourages patching SDK
   internals, and does not compose with strict MyPy as cleanly as a narrow
   Protocol).
5. Ambiguous constructor precedence between `api_key` and an injected client
   (rejected in favor of requiring exactly one, which is simpler to reason
   about and test than a precedence rule).

### Rationale

Keeping the port in `app/application/` and the adapter in
`app/infrastructure/` extends a pattern proven three times already. Splitting
AI-authored content from trusted metadata into two types - rather than
trusting the model with the full schema and stripping fields afterward -
makes the "the model cannot control identity/provenance" guarantee a
property of the type system, not application logic that could be forgotten
or bypassed. Reading the installed SDK's own source before writing adapter
code (rather than trusting training-data memory of an older `openai`
version) directly followed from the explicit instruction not to rely on
remembered or obsolete APIs, and surfaced real, non-obvious behavior (the
Chat-Completions-only scope of `LengthFinishReasonError`, and that Pydantic
validation failures can propagate directly out of `.parse()`) that a
memory-only implementation would have gotten wrong.

### Consequences

#### Positive

* A future orchestration service depends only on
  `app.application.learning_notes`, never on the `openai` package directly.
* `LearningNoteContent`'s all-required-no-defaults shape is enforced at both
  the Pydantic layer and, by the parity test, kept from silently drifting
  from `LearningNote`.
* The three-attempt validation retry is bounded, stateless, and cleanly
  separated from the SDK's own transport retry - no risk of the two
  compounding into an unbounded retry storm.
* Every adapter test runs against a handwritten fake with no network
  access, and exercises the real retry/assembly/error-translation logic
  rather than a mocked generator.

#### Negative

* The narrow `_ResponsesClient` Protocol required a targeted, documented
  `cast()` where the real `Responses.parse` method's enormous
  auto-generated signature (dozens of `Omit`-defaulted parameters, huge
  Literal-union types) doesn't structurally match a hand-written narrow
  Protocol under strict MyPy, even though the actual keyword arguments used
  are valid at runtime - confirmed by direct source inspection, not
  assumed.
* No truncation policy exists for very long extracted article text; an
  abnormally long or mis-extracted article could be rejected by the
  provider for exceeding context length. This is handled safely (a normal
  `LearningNoteProviderError`, not a crash) but is a documented, accepted
  risk rather than a solved problem.
* Long-lived client ownership is a deliberate deviation from the
  short-lived-per-call pattern in the Sprint 2/3 adapters; a future
  reader must understand this is intentional, not an inconsistency.

### Revisit When

Revisit the no-truncation decision if real usage shows articles routinely
exceeding the configured model's context window. Revisit the
Responses-API-only decision if a concrete requirement emerges for a second
provider or for Chat-Completions-specific behavior. Revisit
`_ResponsesClient`'s narrow surface if a future sprint needs additional
Responses API parameters (for example `previous_response_id` for
multi-turn use) that the current Protocol does not expose.

---

# 6. Decision Index

| ID      | Decision                                                 | Status   |
| ------- | -------------------------------------------------------- | -------- |
| ADR-001 | Build CurrentMind as a standalone project                | Accepted |
| ADR-002 | Treat CurrentMind as a learning system                   | Accepted |
| ADR-003 | Use a modular monolith                                   | Accepted |
| ADR-004 | Use Python 3.12 and FastAPI                              | Accepted |
| ADR-005 | Use SQLite for Phase 1                                   | Accepted |
| ADR-006 | Store Articles and Learning Notes separately             | Accepted |
| ADR-007 | Use source-neutral article interfaces                    | Accepted |
| ADR-008 | Use Trafilatura for extraction                           | Accepted |
| ADR-009 | Do not implement authentication or paywall circumvention | Accepted |
| ADR-010 | Require structured and validated LLM output              | Accepted |
| ADR-011 | Store prompt templates outside Python source files       | Accepted |
| ADR-012 | Keep automated tests independent of live services        | Accepted |
| ADR-013 | Use server-rendered pages for the Phase 1 dashboard      | Accepted |
| ADR-014 | Use `pyproject.toml` for project configuration           | Accepted |
| ADR-015 | Use Alembic for migrations                               | Accepted |
| ADR-016 | Nest application layers under `app/`                     | Accepted |
| ADR-017 | Pydantic domain models with UUID identities and UTC times | Accepted |
| ADR-018 | Closed `GSPaper` enum and four-option `PrelimsQuestion`   | Accepted |
| ADR-019 | Synchronous application-layer `ArticleSource` port        | Accepted |
| ADR-020 | Synchronous `ArticleExtractor` port with status-based outcomes | Accepted |
| ADR-021 | SQLite persistence via application repository ports and explicit domain/ORM mapping | Accepted |
| ADR-022 | Structured Learning Note generation through OpenAI Responses | Accepted |

---

# 7. Maintenance Rules

When adding or changing a decision:

1. Assign the next ADR number.
2. Add the decision to the index.
3. Never delete an accepted decision.
4. Mark replaced decisions as **Superseded**.
5. Link the superseding ADR where applicable.
6. Use exact dates.
7. Record meaningful consequences, including drawbacks.
8. Update related documentation when the decision changes project behaviour.

This document should explain not only what CurrentMind became, but why it became that way.

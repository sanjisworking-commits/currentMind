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

**Status:** Proposed
**Date:** 2026-07-15
**Decision Owner:** Musa

### Context

The database schema will evolve as Article and Learning Note models develop.

Automatic table creation alone does not provide a reliable upgrade path.

### Proposed Decision

Use Alembic for SQLite schema migrations.

### Alternatives Considered

1. Alembic
2. SQLAlchemy automatic `create_all`
3. Custom SQL migration scripts
4. Recreate the local database after every schema change

### Rationale

Alembic integrates with SQLAlchemy and provides a documented path for future schema evolution.

### Consequences

#### Positive

* Repeatable schema upgrades
* Better production discipline
* Easier future PostgreSQL migration

#### Negative

* Additional setup
* Migration files must be maintained
* SQLite migration limitations require care

### Revisit When

Finalize before Sprint 4 persistence work.

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
| ADR-015 | Use Alembic for migrations                               | Proposed |
| ADR-016 | Nest application layers under `app/`                     | Accepted |
| ADR-017 | Pydantic domain models with UUID identities and UTC times | Accepted |
| ADR-018 | Closed `GSPaper` enum and four-option `PrelimsQuestion`   | Accepted |

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

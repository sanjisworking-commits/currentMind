# CLAUDE.md

# CurrentMind — Claude Code Instructions

## 1. Role

You are the lead software engineer responsible for building and maintaining CurrentMind.

CurrentMind is a standalone personal learning system that converts current affairs articles into structured, UPSC-oriented Learning Notes.

You must approach the project as a senior engineer who values:

* Simplicity
* Reliability
* Readability
* Testability
* Incremental delivery
* Clear architectural boundaries

Do not optimize for novelty or architectural sophistication.

Optimize for a system that works reliably and remains understandable over time.

---

## 2. Required Reading

Before making architectural decisions or modifying code, read:

* `docs/PRD.md`
* `docs/ENGINEERING_SPEC.md`
* `docs/ROADMAP.md`
* `docs/DECISIONS.md`
* Existing source files
* Existing tests
* `README.md`

Treat these documents as the source of truth.

When documents conflict, identify the conflict before proceeding.

The priority order is:

1. Explicit instructions in the current user request
2. `CLAUDE.md`
3. `docs/DECISIONS.md`
4. `docs/ENGINEERING_SPEC.md`
5. `docs/ROADMAP.md`
6. `docs/PRD.md`
7. Existing implementation patterns

Do not silently resolve significant conflicts.

---

## 3. Product Principle

CurrentMind is a learning system, not a conventional news application.

The system should not merely summarize articles.

It should convert articles into structured knowledge that supports:

* Understanding
* Syllabus mapping
* Static-current integration
* Prelims preparation
* Mains preparation
* Revision
* Long-term retention

Every feature should support this learning pipeline:

```text
Article
   ↓
Relevant Information
   ↓
Structured Knowledge
   ↓
Conceptual Understanding
   ↓
Revision
   ↓
Retention
```

Avoid features designed primarily around engagement, endless feeds, notifications, or content consumption.

---

## 4. Project Independence

CurrentMind must remain a standalone project during Phase 1.

It may later integrate with the Knowledge Operating System, or KOS, but it must not depend on KOS now.

Therefore:

* Do not import KOS packages.
* Do not copy KOS abstractions without a present need.
* Do not introduce KOS-specific terminology into the core implementation.
* Do not create integration code unless explicitly requested.
* Do not compromise CurrentMind’s standalone usability for possible future integration.

Future integration should remain possible through clean interfaces and structured domain objects.

---

## 5. Development Method

Work sprint by sprint according to `docs/ROADMAP.md`.

For every sprint, follow this sequence.

### 5.1 Inspect

Before changing code:

* Inspect the current repository.
* Read relevant documentation.
* Review existing tests.
* Check the current Git diff where available.
* Identify incomplete or conflicting work.
* Understand existing conventions before introducing new ones.

Never assume that a task is unimplemented merely because it appears in the roadmap.

Verify the current source first.

### 5.2 Plan

Before implementation, provide a concise plan containing:

* Current repository assessment
* Scope of the sprint
* Files to create
* Files to modify
* Proposed design
* Testing strategy
* Important risks or trade-offs

Do not begin major implementation before establishing a clear plan.

### 5.3 Implement

Implement only the requested sprint or task.

Do not add future features merely because they appear useful.

Keep changes focused and reviewable.

### 5.4 Verify

After implementation, run all relevant checks:

```bash
pytest
ruff check .
mypy .
```

Also run relevant application commands or targeted tests.

Do not report completion while known test, lint, or type-checking failures remain, unless the failure is unrelated and clearly documented.

### 5.5 Report

At the end of the task, report:

* What was implemented
* Files created or modified
* Tests added
* Commands run
* Results of verification
* Known limitations
* Decisions that should be recorded in `docs/DECISIONS.md`
* Recommended next sprint

Do not claim something works unless it was verified.

---

## 6. Architectural Rules

CurrentMind should be implemented as a modular monolith.

Use the following conceptual layers:

```text
Presentation
    ↓
Application
    ↓
Domain
    ↓
Infrastructure
```

### Domain Layer

The domain layer contains core business concepts.

Examples:

* Article
* ArticleCandidate
* ExtractedArticle
* LearningNote
* PrelimsQuestion
* ProcessingStatus

The domain layer must not depend on:

* FastAPI
* SQLAlchemy
* OpenAI SDK
* feedparser
* Trafilatura
* HTTP clients
* Database sessions

### Application Layer

The application layer coordinates workflows.

Examples:

* Discover articles
* Process an article
* Process the feed
* Retry a failed article
* Retrieve recent Learning Notes

Application services should depend on interfaces, not concrete infrastructure implementations.

### Infrastructure Layer

The infrastructure layer implements external integrations.

Examples:

* Indian Express RSS adapter
* HTTP article extractor
* SQLite repositories
* OpenAI Learning Note generator
* Logging and configuration

### Presentation Layer

The presentation layer contains:

* FastAPI routes
* Dashboard views
* CLI commands
* Request and response handling

Presentation code must not contain core business logic.

---

## 7. Simplicity Rules

Prefer the simplest implementation that satisfies the current requirements.

Do not introduce the following during Phase 1 unless explicitly approved:

* Microservices
* Kafka
* Redis
* Celery
* Message queues
* CQRS
* Event sourcing
* Complex dependency-injection frameworks
* Plugin frameworks
* Service locators
* Distributed tracing
* Kubernetes
* Container orchestration
* Graph databases
* Vector databases
* RAG pipelines
* Background worker infrastructure
* Multiple frontend frameworks

Small interfaces are acceptable when they isolate external systems or materially improve testing.

Do not create interfaces for every class merely for architectural appearance.

---

## 8. Source Adapter Rules

The initial source is the Indian Express UPSC Current Affairs RSS feed.

Treat Indian Express as an infrastructure adapter, not as a core domain concept.

The analyzer, repositories, and UI should not depend on Indian Express-specific structures.

Use a source-neutral abstraction such as:

```python
class ArticleSource(Protocol):
    def discover_articles(self) -> list[ArticleCandidate]:
        ...
```

The Phase 1 implementation may be:

```python
class IndianExpressRSSSource:
    ...
```

Do not implement additional sources during Phase 1.

---

## 9. Content Access Rules

Phase 1 may process only content accessible through ordinary public HTTP requests.

Do not:

* Ask for Indian Express login credentials.
* Store usernames or passwords.
* Automate login flows.
* Export or reuse browser cookies.
* Circumvent paywalls.
* Attempt to defeat access controls.
* Use browser automation unless explicitly approved for a lawful, non-circumvention use.

When an article cannot be accessed or extracted:

* Record the failure.
* Preserve the article metadata.
* Log a meaningful reason.
* Continue processing other articles.

---

## 10. Domain Modeling Rules

Use explicit, strongly typed domain models.

Avoid unvalidated dictionaries for important structures.

For example, a Prelims question should use a model such as:

```python
class PrelimsQuestion(BaseModel):
    question: str
    options: list[str]
    correct_option: int
    explanation: str
```

Important domain structures should have validation rules.

Examples:

* A Prelims question should have a valid number of options.
* The correct option must refer to an existing option.
* Required Learning Note fields should not contain empty placeholder values.
* Processing statuses should use an enum.
* URLs should be validated.
* Timestamps should use UTC internally.

Do not couple domain models directly to SQLAlchemy tables.

---

## 11. LLM Integration Rules

LLM integration must be isolated behind an application-facing interface.

Example:

```python
class LearningNoteGenerator(Protocol):
    def generate(self, article: Article) -> LearningNote:
        ...
```

Only the infrastructure implementation should import the LLM provider SDK.

### Output Requirements

LLM output must:

* Follow a defined schema.
* Return structured data.
* Be validated with Pydantic.
* Use empty lists where a category is not applicable.
* Distinguish article facts from reasonable analytical interpretation.
* Avoid inventing constitutional provisions, cases, reports, schemes, statistics, or historical facts.
* Avoid reproducing large portions of the original article.
* Remain concise and revision-oriented.

### Failure Handling

* Retry only recoverable failures.
* Use a bounded retry count.
* Log why a retry occurred.
* Do not retry indefinitely.
* Do not silently accept invalid output.
* Do not expose API keys or complete prompts in logs.
* Store the model name and prompt version with generated notes.

### Prompt Management

Prompts must live outside Python source files.

Store prompt templates in:

```text
prompts/
```

Prompt changes should be versioned.

---

## 12. Database Rules

Use SQLite for Phase 1.

Use SQLAlchemy 2.x and database migrations.

The database should contain separate representations for:

* Articles
* Learning Notes

Do not store the entire Learning Note as one opaque JSON or text blob unless a specific field is intentionally structured that way.

Enforce duplicate prevention using suitable unique constraints.

Possible duplicate identifiers include:

* Source and external identifier
* Canonical article URL

Repositories should translate infrastructure exceptions into meaningful application-level errors.

Automated repository tests must use temporary databases.

---

## 13. Processing Pipeline Rules

The feed-processing workflow must be idempotent.

Re-running the pipeline should not:

* Create duplicate articles.
* Create duplicate Learning Notes.
* Re-analyze completed articles by default.

The pipeline should preserve partial progress.

A typical workflow is:

```text
Discover
   ↓
Deduplicate
   ↓
Persist Metadata
   ↓
Extract Content
   ↓
Persist Extracted Content
   ↓
Generate Learning Note
   ↓
Validate
   ↓
Persist Learning Note
   ↓
Mark Complete
```

One failed article must not stop the entire batch.

Every article should have a clear processing status.

Failed articles should remain eligible for a deliberate retry.

---

## 14. Error Handling Rules

Never fail silently.

Expected operational failures include:

* Network errors
* RSS errors
* Invalid feeds
* Missing article metadata
* Article extraction failures
* Insufficient article content
* LLM timeouts
* Invalid LLM responses
* Database failures
* Template rendering failures

Errors should be:

* Logged clearly
* Classified where useful
* Converted into meaningful application errors
* Recoverable when appropriate

Avoid broad exception handling that hides programming defects.

Do not use:

```python
except Exception:
    pass
```

When a broad boundary exception is necessary, log the complete context and preserve the original exception chain.

---

## 15. Logging Rules

Use the standard Python logging library unless a different choice is explicitly approved.

Log significant lifecycle events, including:

* Feed fetch started
* Feed fetch completed
* Number of entries discovered
* Duplicate skipped
* Article extraction started
* Article extraction completed
* Article extraction failed
* LLM analysis started
* LLM validation failed
* Retry initiated
* Learning Note saved
* Processing batch completed

Never log:

* API keys
* Passwords
* Authentication tokens
* Full environment files
* Sensitive headers

Avoid logging the full article text or complete LLM response during normal operation.

---

## 16. Configuration Rules

Use environment-based configuration.

Expected variables may include:

```env
OPENAI_API_KEY=
DATABASE_URL=sqlite:///./database/currentmind.db
RSS_URL=https://indianexpress.com/section/upsc-current-affairs/feed/
LOG_LEVEL=INFO
LLM_MODEL=
```

Provide safe defaults only where appropriate.

Maintain:

```text
.env.example
```

Never commit:

```text
.env
```

Validate configuration during application startup and provide meaningful errors for missing required values.

---

## 17. Testing Rules

Tests are part of implementation, not optional follow-up work.

Use:

* `pytest`
* Fakes for external services
* Fixtures for RSS and HTML content
* Temporary SQLite databases
* Deterministic test data

Automated tests must not require:

* Live Indian Express access
* Live OpenAI access
* Internet connectivity
* Personal credentials

Minimum test areas:

* Domain validation
* RSS parsing
* Duplicate detection
* Article extraction
* Repository persistence
* LLM output validation
* Retry limits
* Processing state transitions
* Pipeline idempotency
* Dashboard rendering

Prefer testing observable behaviour rather than internal implementation details.

Do not write tests that merely repeat the implementation.

---

## 18. Code Quality Rules

Use:

* Python 3.12
* Full type hints
* Pydantic v2
* SQLAlchemy 2.x
* Ruff
* MyPy
* Pytest

Maximum line length:

```text
100 characters
```

Naming conventions:

* Classes: `PascalCase`
* Functions: `snake_case`
* Variables: `snake_case`
* Constants: `UPPER_CASE`
* Private implementation details: leading underscore where appropriate

Use modern Python syntax compatible with Python 3.12.

Prefer:

```python
str | None
```

over:

```python
Optional[str]
```

unless project compatibility requirements later change.

Avoid:

* Wildcard imports
* Hidden global state
* Mutable global collections
* Deep inheritance
* Clever metaprogramming
* Unnecessary decorators
* Boolean parameters that obscure behaviour
* Functions with multiple unrelated responsibilities

Keep functions and classes focused.

---

## 19. Documentation Rules

Every public class and function should have a useful docstring where its purpose is not immediately obvious.

Docstrings should explain:

* Purpose
* Parameters
* Return value
* Important exceptions
* Relevant side effects

Do not add comments that merely restate the code.

Update documentation whenever behaviour changes.

The README must remain accurate for:

* Installation
* Environment setup
* Database setup
* Running the application
* Processing the feed
* Starting the dashboard
* Running tests
* Running lint and type checks
* Known limitations

---

## 20. Decision Recording

Record significant architectural decisions in:

```text
docs/DECISIONS.md
```

A decision should be recorded when it affects:

* Architecture
* Data modeling
* Technology selection
* External provider selection
* Public interfaces
* Migration strategy
* Testing strategy
* Future compatibility
* Security or content-access boundaries

Each decision should include:

* Decision
* Context
* Alternatives considered
* Rationale
* Consequences
* Status
* Date

Do not record trivial implementation details.

---

## 21. Git Rules

Make small, focused commits.

A commit should represent one coherent change.

Good examples:

```text
Initialize FastAPI project structure
Add Article domain model
Implement Indian Express RSS adapter
Add SQLite article repository
Validate structured Learning Note output
```

Avoid:

```text
Misc changes
Updates
Fix stuff
Final version
```

Do not mix unrelated refactoring and feature development without a clear reason.

Before committing:

* Run relevant tests.
* Run Ruff.
* Run MyPy.
* Review the diff.
* Ensure secrets are not included.

Do not rewrite Git history or force-push unless explicitly requested.

---

## 22. UI Rules

The UI should optimize for study and revision.

Prioritize:

* Clear hierarchy
* Scannable sections
* Readable typography
* Visible source attribution
* Minimal clutter
* Clear processing status
* Clear separation between questions and answers

Do not build:

* Infinite scrolling
* Social engagement features
* Recommendation feeds
* Gamification
* Complex animations
* A large frontend framework during Phase 1

Use the simplest presentation approach that meets the PRD.

---

## 23. Prohibited Phase 1 Features

Do not implement the following unless explicitly requested:

* Authentication
* Multiple users
* Multiple news sources
* Indian Express login integration
* Paywall circumvention
* Semantic search
* Embeddings
* Vector databases
* RAG
* Knowledge graphs
* AI chat
* Flashcards
* Spaced repetition
* Revision scheduling
* Mobile applications
* Browser extensions
* Email or WhatsApp delivery
* Automatic background scheduling
* KOS integration

A clean extension point is acceptable.

A premature implementation is not.

---

## 24. Completion Standard

Do not describe a sprint as complete solely because code was written.

A sprint is complete only when:

* The requested functionality is implemented.
* Tests are added.
* Tests pass.
* Ruff passes.
* MyPy passes at the configured level.
* Relevant application commands have been run.
* Documentation is updated.
* Known limitations are documented.
* Significant decisions are recorded.

Be precise about anything that was not verified.

---

## 25. Default Engineering Preference

When multiple approaches satisfy the requirements, prefer the approach that is:

1. Easier to understand
2. Easier to test
3. Easier to replace
4. Less coupled
5. Less operationally complex
6. Appropriate for a personal-use application

The goal is not to build the most sophisticated system.

The goal is to build the smallest reliable system that delivers meaningful learning value.

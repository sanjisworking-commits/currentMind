# ROADMAP.md

# CurrentMind Development Roadmap

**Project:** CurrentMind
**Phase:** Phase 1 — Minimum Viable Product
**Status:** Planned
**Primary Goal:** Build a reliable, end-to-end learning pipeline that converts Indian Express UPSC current affairs articles into structured UPSC Learning Notes.

---

# 1. Development Strategy

CurrentMind will be built incrementally.

Each sprint must:

* Produce a working and testable result.
* Add only the functionality required for that sprint.
* Include automated tests.
* Leave the codebase in a stable state.
* Avoid implementing future-phase features prematurely.

The project should be developed as a simple modular monolith.

The recommended implementation order is:

```text
Project Foundation
        ↓
Domain Models
        ↓
RSS Source Adapter
        ↓
Article Extraction
        ↓
Database Persistence
        ↓
LLM Analysis
        ↓
End-to-End Processing
        ↓
Web Dashboard
        ↓
Reliability and Documentation
```

---

# 2. Phase 1 Definition of Done

Phase 1 is complete when the user can:

1. Start the application locally.
2. Fetch articles from the Indian Express UPSC RSS feed.
3. Detect and skip duplicate articles.
4. Extract clean article text.
5. Generate a structured UPSC Learning Note using an LLM.
6. Store the article and Learning Note in SQLite.
7. View recent articles through a local web dashboard.
8. Open an article and read its complete Learning Note.
9. Re-run the application without reprocessing completed articles.
10. Review meaningful logs and errors when processing fails.

---

# 3. Sprint 0 — Project Foundation

## Objective

Create the initial repository structure, development environment, configuration system, and quality tooling.

## Deliverables

* Python 3.12 project initialized.
* Package and dependency management configured.
* Application directory structure created.
* `.env.example` added.
* Central configuration module created.
* Logging configured.
* Ruff configured.
* MyPy configured.
* Pytest configured.
* Basic FastAPI application created.
* Health-check endpoint implemented.
* Initial README created.

## Suggested Project Structure

```text
currentmind/
├── app/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   └── presentation/
├── prompts/
├── tests/
├── docs/
├── database/
├── logs/
├── main.py
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

## Acceptance Criteria

* The application starts successfully.
* `GET /health` returns a successful response.
* Tests run successfully.
* Ruff reports no errors.
* MyPy reports no blocking type errors.
* No API keys or secrets are committed.

## Out of Scope

* RSS fetching
* Database models
* Article parsing
* LLM integration
* Dashboard

---

# 4. Sprint 1 — Core Domain Models

## Objective

Define the central business objects without coupling them to databases, HTTP frameworks, or external services.

## Required Domain Models

### Article

Represents a source article before and after extraction.

Suggested fields:

* `id`
* `source`
* `external_id`
* `title`
* `url`
* `author`
* `published_at`
* `categories`
* `raw_text`
* `content_status`
* `created_at`
* `updated_at`

### LearningNote

Represents the structured UPSC learning output generated from an article.

Suggested fields:

* `id`
* `article_id`
* `summary`
* `why_it_matters`
* `gs_papers`
* `subjects`
* `syllabus_topics`
* `static_concepts`
* `constitutional_linkages`
* `government_schemes`
* `reports_and_committees`
* `international_dimensions`
* `important_facts`
* `prelims_questions`
* `mains_questions`
* `revision_note`
* `keywords`
* `model_name`
* `prompt_version`
* `created_at`

### PrelimsQuestion

Suggested fields:

* `question`
* `options`
* `correct_option`
* `explanation`

### ProcessingStatus

Suggested values:

* `discovered`
* `extracted`
* `analysis_pending`
* `analyzed`
* `failed`

## Design Requirements

* Models should use strong typing.
* Structured values should not be stored as arbitrary unvalidated dictionaries.
* Domain models must not import SQLAlchemy or FastAPI.
* Use enums where appropriate.
* Use UTC timestamps internally.
* Keep source-specific data out of the core domain when possible.

## Acceptance Criteria

* All domain models validate correctly.
* Invalid question structures are rejected.
* Invalid processing states are rejected.
* Domain tests pass.
* Models contain no persistence or HTTP logic.

## Out of Scope

* Database tables
* RSS parsing
* LLM calls
* UI

---

# 5. Sprint 2 — Source Adapter and RSS Discovery

## Objective

Implement the first source adapter for the Indian Express UPSC Current Affairs RSS feed.

## Source

```text
https://indianexpress.com/section/upsc-current-affairs/feed/
```

## Requirements

The source adapter must:

* Fetch the RSS feed.
* Parse available entries.
* Convert feed entries into source-neutral article candidates.
* Capture title, URL, publication date, author, category, and external identifier where available.
* Handle missing optional RSS fields safely.
* Detect duplicate entries within the same response.
* Use timeouts.
* Use a clear user-agent header.
* Return meaningful errors for unavailable or malformed feeds.

## Proposed Interface

```python
class ArticleSource:
    def discover_articles(self) -> list[ArticleCandidate]:
        ...
```

Phase 1 implementation:

```python
class IndianExpressRSSSource(ArticleSource):
    ...
```

The application should depend on the source interface rather than directly on Indian Express.

## Acceptance Criteria

* Valid RSS entries are returned as article candidates.
* Duplicate feed entries are removed.
* Missing optional metadata does not crash the application.
* Network failures are logged clearly.
* Parsing tests use saved fixture data rather than live network calls.
* The analyzer and storage layers contain no Indian Express-specific logic.

## Out of Scope

* Scheduled background polling
* Multiple news sources
* Authentication
* Paywall bypassing
* Full article extraction

---

# 6. Sprint 3 — Article Content Extraction

## Objective

Download article pages and extract clean, readable article text.

## Requirements

The extraction service must:

* Accept an article URL.
* Download the page with a timeout.
* Extract the main article body.
* Remove navigation, advertisements, related stories, and footer text where possible.
* Normalize whitespace.
* Reject empty or unusably short content.
* Preserve meaningful paragraph breaks.
* Return extraction metadata.
* Log failures without crashing the full batch.

## Preferred Tool

Use Trafilatura as the default extraction library.

The extractor should be wrapped behind an interface so it can be replaced later.

## Proposed Interface

```python
class ArticleExtractor:
    def extract(self, url: str) -> ExtractedArticle:
        ...
```

## Extraction Statuses

Suggested outcomes:

* `success`
* `insufficient_content`
* `network_error`
* `unsupported_page`
* `unexpected_error`

## Acceptance Criteria

* Clean content can be extracted from representative article fixtures.
* Advertisement and navigation text are substantially excluded.
* Empty extraction results are not marked as successful.
* Extraction failures are logged.
* A failure for one article does not stop processing other articles.
* Unit tests do not depend on the live Indian Express website.

## Out of Scope

* Browser automation
* Login sessions
* Cookie-based authentication
* Paywall circumvention
* Image extraction
* OCR

---

# 7. Sprint 4 — Persistence Layer

## Objective

Persist articles, processing state, and Learning Notes in SQLite.

## Requirements

Create SQLAlchemy models and repositories for:

* Articles
* Learning Notes

The system must:

* Save newly discovered articles.
* Detect duplicate articles by canonical URL and source identifier.
* Update extracted content.
* Save processing status.
* Save structured Learning Notes.
* Retrieve recent articles.
* Retrieve an article with its Learning Note.
* Record failure messages where useful.

## Repository Interfaces

Suggested interfaces:

```python
class ArticleRepository:
    def add(self, article: Article) -> Article:
        ...

    def get_by_url(self, url: str) -> Article | None:
        ...

    def list_recent(self, limit: int = 20) -> list[Article]:
        ...

    def update_status(self, article_id: str, status: ProcessingStatus) -> None:
        ...
```

```python
class LearningNoteRepository:
    def save(self, note: LearningNote) -> LearningNote:
        ...

    def get_by_article_id(self, article_id: str) -> LearningNote | None:
        ...
```

## Database Design Requirements

* Use migrations rather than relying only on automatic table creation.
* Enforce uniqueness for source identifiers and canonical URLs where appropriate.
* Use foreign keys.
* Delete Learning Notes appropriately if their parent article is deleted.
* Store structured list fields consistently.
* Do not store the complete Learning Note as one opaque text blob.

## Acceptance Criteria

* Duplicate article insertion is prevented.
* Articles persist across application restarts.
* Learning Notes maintain a valid relationship with Articles.
* Repository tests use a temporary SQLite database.
* Database exceptions are translated into meaningful application errors.

## Out of Scope

* PostgreSQL
* Cloud database
* Full-text search
* Vector storage
* User-specific data

---

# 8. Sprint 5 — LLM Analysis Contract and Prompt

## Objective

Define and implement the structured AI analysis pipeline.

## Requirements

The analyzer must transform extracted article content into a validated Learning Note.

The output should include:

* Summary
* Why the article matters
* Relevant GS papers
* Subjects
* UPSC syllabus topics
* Static concepts
* Constitutional linkages
* Government schemes
* Reports and committees
* International dimensions
* Important facts and data
* Prelims MCQs
* Mains questions
* Revision note
* Keywords

## Prompt Requirements

The prompt must:

* Identify the model as a UPSC-focused analyst and teacher.
* Distinguish facts from inference.
* Avoid inventing constitutional provisions, judgments, reports, or data.
* Use empty lists when a category is not relevant.
* Produce concise, revision-oriented content.
* Avoid copying large portions of the article.
* Return structured output only.
* Follow the Pydantic schema exactly.
* Mention the supplied article as the primary source context.

## Output Validation

* Use Pydantic validation.
* Reject malformed MCQs.
* Reject missing required fields.
* Retry only for recoverable format or validation failures.
* Limit retries.
* Log retry reasons.
* Store model name and prompt version.

## Provider Design

Use an interface such as:

```python
class LearningNoteGenerator:
    def generate(self, article: Article) -> LearningNote:
        ...
```

The application must not depend directly on the OpenAI SDK outside the infrastructure implementation.

## Acceptance Criteria

* Valid model output is converted into a Learning Note.
* Invalid output is rejected.
* Recoverable validation failures trigger a bounded retry.
* Tests use a fake LLM provider.
* Prompt files are stored outside Python source files.
* The application does not expose secrets in logs.

## Out of Scope

* RAG
* Web search for fact verification
* Multiple LLM providers
* Streaming output
* Chat interface
* Knowledge graph extraction

---

# 9. Sprint 6 — Processing Pipeline

## Objective

Connect discovery, extraction, analysis, and persistence into one complete workflow.

## Workflow

```text
Discover Feed Entries
        ↓
Check Existing Article
        ↓
Save New Article
        ↓
Extract Content
        ↓
Update Processing State
        ↓
Generate Learning Note
        ↓
Validate Output
        ↓
Persist Learning Note
        ↓
Mark Article as Analyzed
```

## Application Service

Suggested service:

```python
class ProcessNewsFeedService:
    def process(self) -> ProcessingSummary:
        ...
```

## Processing Summary

The service should return:

* Total discovered
* New articles
* Duplicates skipped
* Successfully extracted
* Successfully analyzed
* Failed
* Failure details

## Reliability Requirements

* Processing should be idempotent.
* Completed articles should not be analyzed again by default.
* Failed articles should be eligible for manual retry.
* One article failure should not stop the batch.
* Processing statuses must be updated consistently.
* Partial results should be preserved.

## Command-Line Entry Point

Provide a command such as:

```bash
python main.py process-feed
```

or an equivalent documented CLI command.

## Acceptance Criteria

* A new article can travel through the complete pipeline.
* Re-running the command skips completed articles.
* Duplicate records are not created.
* Failed items are clearly reported.
* End-to-end tests use local fixtures and a fake LLM provider.
* No live API call is required for automated tests.

## Out of Scope

* Automatic scheduling
* Background workers
* Email notifications
* Daily digest

---

# 10. Sprint 7 — Web Dashboard

## Objective

Provide a simple interface for browsing processed articles and Learning Notes.

## Required Pages

### Home Page

Display recent processed articles with:

* Title
* Publication date
* Source
* GS paper
* Topic tags
* Short summary
* Processing status
* Link to full article view

### Article Detail Page

Display:

* Article metadata
* Link to original article
* Executive summary
* Why it matters
* GS paper and syllabus mapping
* Static concepts
* Constitutional linkages
* Schemes
* Reports and committees
* International dimensions
* Important facts
* Prelims questions
* Answers and explanations
* Mains questions
* Revision note
* Keywords

## UI Principles

* Optimize for study and revision.
* Avoid visual clutter.
* Use clear headings.
* Make long notes scannable.
* Clearly distinguish questions from answers.
* Ensure the original source link is visible.
* Do not recreate a social-media-style news feed.

## Optional Phase 1 Filters

Only add these if implementation remains simple:

* GS paper
* Processing status
* Keyword search over stored metadata

## Acceptance Criteria

* The homepage displays stored articles.
* The detail page displays a complete Learning Note.
* Articles without completed analysis show a clear status.
* Missing optional sections do not break rendering.
* The interface works locally without frontend build complexity.

## Out of Scope

* React or Next.js frontend
* Authentication
* User preferences
* Rich text editor
* Knowledge graph visualization
* Semantic search

---

# 11. Sprint 8 — Reliability, Documentation, and MVP Release

## Objective

Prepare Phase 1 for regular personal use.

## Reliability Tasks

* Review timeout settings.
* Review retry behaviour.
* Improve error messages.
* Ensure database migrations work from a clean setup.
* Add graceful handling for unavailable RSS feeds.
* Add graceful handling for article extraction failures.
* Add graceful handling for invalid LLM responses.
* Verify duplicate protection.
* Add manual retry capability for failed articles.
* Ensure logs do not expose API keys or full sensitive configuration.

## Documentation Tasks

Update `README.md` with:

* Product overview
* Requirements
* Installation steps
* Environment setup
* Database setup
* How to run tests
* How to process the feed
* How to start the dashboard
* Known limitations
* Troubleshooting

Create or update:

* `.env.example`
* `DECISIONS.md`
* Architecture overview
* Prompt version documentation

## Final Test Scenarios

The MVP should be tested for:

1. A valid new article.
2. A duplicate article.
3. An unavailable RSS feed.
4. A malformed RSS response.
5. An article with insufficient extractable text.
6. An LLM timeout.
7. Invalid LLM output.
8. Database persistence across restart.
9. Multiple articles where one fails.
10. Dashboard rendering with incomplete optional data.

## Acceptance Criteria

* A clean installation works from the README.
* All automated tests pass.
* Ruff passes.
* MyPy passes at the agreed strictness level.
* The application processes at least one real accessible article successfully.
* Known content-access limitations are documented.
* The Phase 1 definition of done is satisfied.

---

# 12. Recommended Sprint Execution Protocol for Claude Code

For each sprint, Claude Code should follow this process:

## Step 1 — Inspect

Read:

* `docs/PRD.md`
* `docs/ENGINEERING_SPEC.md`
* `docs/ROADMAP.md`
* `CLAUDE.md`
* `docs/DECISIONS.md`
* Existing source code
* Existing tests

## Step 2 — Plan

Before coding, provide:

* Current repository assessment
* Proposed changes
* Files to create or modify
* Important design decisions
* Testing approach
* Risks or ambiguities

## Step 3 — Implement

Implement only the current sprint.

Do not add future features unless strictly required by the current sprint.

## Step 4 — Verify

Run:

* Tests
* Ruff
* MyPy
* Relevant application command

Fix failures before reporting completion.

## Step 5 — Report

Summarize:

* What was implemented
* Files changed
* Tests added
* Commands run
* Known limitations
* Any decisions that should be added to `DECISIONS.md`

---

# 13. Phase 1 Constraints

Throughout Phase 1:

* Do not implement authentication.
* Do not request or store Indian Express login credentials.
* Do not attempt to bypass paywalls.
* Do not introduce browser automation unless explicitly approved later.
* Do not introduce a vector database.
* Do not implement semantic search.
* Do not build a knowledge graph.
* Do not integrate with KOS.
* Do not add distributed infrastructure.
* Do not add multiple news sources.
* Do not build scheduled background jobs.

The system may process only publicly accessible content returned through ordinary HTTP requests.

---

# 14. Future Phases

## Phase 2 — Study Experience

Potential features:

* Better filtering and search
* Manual article submission
* Daily and weekly summaries
* Editable Learning Notes
* Improved UPSC classification
* Topic dashboards
* Export to Markdown or PDF

## Phase 3 — Connected Knowledge

Potential features:

* Cross-article concept linking
* Topic timelines
* Prerequisite mapping
* Related article recommendations
* Knowledge graph

## Phase 4 — Personalized Learning

Potential features:

* Flashcards
* Spaced repetition
* Weak-topic analytics
* Revision planning
* AI tutor
* Personalized question generation

## Phase 5 — KOS Integration

Potential integration points:

* Export Article and LearningNote objects.
* Expose application services through a stable interface.
* Convert Learning Notes into KOS Knowledge Units.
* Transfer provenance and source metadata.
* Reuse extracted concepts and questions.
* Preserve CurrentMind as an independently runnable application.

Future integration should happen only after CurrentMind proves useful as a standalone product.

---

# 15. Recommended Immediate Next Step

Begin with **Sprint 0 — Project Foundation**.

Claude Code should first inspect all project documentation and propose the exact repository structure, dependency choices, and setup plan before creating implementation files.

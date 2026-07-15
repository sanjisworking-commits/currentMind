# ENGINEERING_SPEC.md

# CurrentMind Engineering Specification

**Project:** CurrentMind

**Version:** Phase 1

**Status:** Active

---

# 1. Engineering Philosophy

CurrentMind is intended to be a long-lived software project.

The codebase should prioritize:

* Simplicity
* Readability
* Testability
* Extensibility
* Reliability

Avoid premature optimization and unnecessary abstractions.

Every architectural decision should make the system easier to understand six months from now.

---

# 2. Engineering Principles

## Build Incrementally

Every development phase must produce a working application.

Avoid building infrastructure for future features before they are needed.

---

## Keep It Modular

Each responsibility should belong to one module.

Examples:

* RSS fetching
* Article extraction
* AI analysis
* Storage
* Presentation

These should remain independent.

---

## Prefer Composition

Favor composition over inheritance.

Avoid deep inheritance hierarchies.

---

## Avoid Over-Engineering

Do not introduce:

* Event buses
* Microservices
* CQRS
* Kafka
* Message queues
* Distributed systems
* Plugin architectures

Unless explicitly requested in future phases.

---

## Strong Typing

Every public function should use explicit type hints.

Use Pydantic models wherever appropriate.

---

# 3. Architecture

CurrentMind will follow a simple layered architecture.


Presentation Layer
        │
Application Layer
        │
Domain Layer
        │
Infrastructure Layer

                CurrentMind

            Source Adapters
        ┌─────────────────────┐
        │ Indian Express RSS  │
        │ PIB                 │
        │ PRS                 │
        │ RBI                 │
        │ The Hindu           │
        │ Down To Earth       │
        └──────────┬──────────┘
                   │
                   ▼
            Article Fetcher
                   │
                   ▼
            Content Extractor
                   │
                   ▼
              AI Analyzer
                   │
                   ▼
           Learning Note
                   │
                   ▼
              SQLite / UI


---

## Presentation Layer

Responsible for:

* Dashboard
* API endpoints
* User interaction

Should never contain business logic.

---

## Application Layer

Coordinates workflows.

Examples:

* Process RSS feed
* Analyze article
* Save article
* Retrieve articles

Application services orchestrate the domain.

---

## Domain Layer

Contains business concepts.

Examples:

* Article
* LearningNote
* Topic
* AnalysisResult

No database code.

No API code.

No HTTP logic.

---

## Infrastructure Layer

Responsible for external systems.

Examples:

* SQLite
* RSS feed
* OpenAI API
* Logging
* Configuration

Infrastructure should implement interfaces defined by higher layers.

---

# 4. Project Structure

```text
currentmind/

├── app/
│
├── domain/
│
├── application/
│
├── infrastructure/
│
├── presentation/
│
├── prompts/
│
├── tests/
│
├── config/
│
├── database/
│
├── logs/
│
├── docs/
│
├── main.py
│
└── README.md
```

Each directory should have a single responsibility.

---

# 5. Technology Stack

Language

* Python 3.12

Backend

* FastAPI

ORM

* SQLAlchemy 2.x

Validation

* Pydantic v2

Database

* SQLite

RSS

* feedparser

Article Extraction

* Trafilatura

LLM

* OpenAI SDK

Configuration

* python-dotenv

Testing

* pytest

Formatting

* Ruff

Type Checking

* MyPy

Logging

* Standard Python logging

---

# 6. Data Storage

SQLite is sufficient for Phase 1.

The database should contain separate tables for:

* Articles
* Learning Notes

Do not store AI output as an unstructured blob.

Store structured fields.

---

# 7. AI Design Principles

Every AI response must be deterministic in structure.

Responses must:

* Return JSON only
* Match the expected schema
* Be validated
* Retry automatically if validation fails

Prompt templates should live in the `prompts/` directory.

No prompts should be hardcoded inside Python files.

---

# 8. Error Handling

The application should never fail silently.

Every failure should:

* Be logged
* Return meaningful errors
* Allow recovery where possible

Expected failure scenarios:

* RSS unavailable
* Network timeout
* Invalid article
* LLM timeout
* Invalid JSON
* Database errors

---

# 9. Configuration

Use a `.env` file.

Example:

```env
OPENAI_API_KEY=
DATABASE_URL=
LOG_LEVEL=INFO
RSS_URL=
```

Never hardcode secrets.

---

# 10. Logging

Log important lifecycle events.

Examples:

* RSS fetch started
* RSS fetch completed
* Article downloaded
* Analysis completed
* Database updated
* Retry triggered
* Error occurred

Use structured, readable log messages.

---

# 11. Testing Strategy

Every major module should have unit tests.

Minimum coverage:

* RSS Fetcher
* Article Parser
* JSON Validation
* Database Storage
* AI Response Parsing

Critical workflows should have integration tests.

---

# 12. Documentation Standards

Every public class should have a docstring.

Every public function should explain:

* Purpose
* Parameters
* Returns
* Exceptions

Avoid unnecessary comments.

Prefer self-explanatory code.

---

# 13. Coding Standards

Maximum line length:

100 characters

Naming:

* Classes → PascalCase
* Functions → snake_case
* Variables → snake_case
* Constants → UPPER_CASE

Imports:

* Standard Library
* Third-party
* Local modules

Avoid wildcard imports.

---

# 14. Git Workflow

Development should follow small, meaningful commits.

Example commit messages:

* Add RSS fetcher
* Implement article parser
* Add AI analysis service
* Create learning note model

Avoid large commits containing unrelated changes.

---

# 15. Performance Expectations

The application is intended for personal use.

Optimize for:

* Maintainability
* Reliability
* Simplicity

Not maximum throughput.

---

# 16. Future Compatibility

Although CurrentMind is an independent project, it should be designed so that future integration with larger systems (such as KOS) is straightforward.

To support this:

* Separate domain logic from infrastructure.
* Keep modules loosely coupled.
* Expose clean service interfaces.
* Avoid assumptions tied to a single data source.
* Treat generated Learning Notes as reusable knowledge objects rather than news summaries.

No KOS-specific abstractions should be introduced in Phase 1. The architecture should simply avoid decisions that would make future integration difficult.

---

# 17. Engineering Success Criteria

The engineering implementation will be considered successful if:

* The codebase is easy for a new contributor to understand.
* New news sources can be added with minimal changes.
* The AI analysis pipeline is isolated from the UI.
* All modules are independently testable.
* The application remains simple despite future growth.

When in doubt, prefer the simpler design that satisfies today's requirements while preserving clean extension points for tomorrow.

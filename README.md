# CurrentMind

CurrentMind is a personal learning system that converts UPSC current affairs
articles into structured, exam-oriented Learning Notes.

Phase 1 builds a single end-to-end pipeline for one source (Indian Express
UPSC Current Affairs): RSS discovery → article extraction → LLM analysis →
local storage → web dashboard. See `docs/PRD.md`, `docs/ENGINEERING_SPEC.md`,
and `docs/ROADMAP.md` for the full product and engineering plan.

## Current Status

**Sprint 0 — Project Foundation.** Only the application skeleton, configuration,
logging, and a health-check endpoint exist. RSS fetching, article extraction,
persistence, LLM analysis, and the dashboard are not yet implemented.

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

* No RSS fetching, article extraction, persistence, LLM analysis, or
  dashboard yet — Sprint 0 delivers only the project skeleton, configuration,
  logging, and a health-check endpoint.
* No database exists yet; `database/` and `logs/` are present as placeholders
  for later sprints.

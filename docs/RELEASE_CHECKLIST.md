# RELEASE_CHECKLIST.md

# CurrentMind Phase 1 Release Checklist

A concise checklist for validating the Phase 1 MVP before declaring it ready
for regular personal use. This is deliberately proportionate to a local,
single-user application — not a formal release framework. See ADR-025 for the
verification and validation posture.

---

## 1. Automated gate (network-independent)

Run from a clean checkout. None of these steps calls a live external service.

- [ ] Clean checkout of the intended commit.
- [ ] Python **3.12** available (`.python-version` pins `3.12`).
- [ ] `uv sync --frozen` succeeds with no lockfile change.
- [ ] Clean temporary database migrates: set `DATABASE_URL` to a disposable
      temp file, then
      `uv run alembic upgrade head` → `alembic downgrade base` →
      `alembic upgrade head`.
- [ ] `uv run pytest` — all tests pass.
- [ ] `uv run ruff check .` — clean.
- [ ] `uv run mypy .` — clean (strict).
- [ ] No development database is used (`find database -maxdepth 1 -type f`
      shows only `database/.gitkeep`).
- [ ] `.env` is not tracked (`git status` shows no `.env`; it is gitignored).
- [ ] No secret markers appear in output or logs (the privacy regression
      tests cover this; `git grep` for obvious key patterns as a spot check).
- [ ] CI is green (see ADR-025 / `.github/workflows/ci.yml`).

## 2. Known external warnings

Two deprecation warnings are expected and are **not** project defects; they
are left visible (no warning filters are added):

1. Starlette/httpx test-client deprecation — emitted by FastAPI/Starlette's
   `TestClient` import; the project only uses `TestClient` in tests.
2. feedparser parsed-date fallback — emitted by feedparser when a fixture
   feed uses `updated_parsed` instead of `published_parsed`.

## 3. Roadmap scenario matrix

Each roadmap failure scenario maps to existing automated tests (no live
services; the document does not duplicate the test code):

| # | Scenario | Test location |
|---|---|---|
| 1 | Valid new Article | `tests/application/test_processing.py`, `tests/infrastructure/test_processing_end_to_end.py` |
| 2 | Duplicate Article | `tests/application/test_processing.py`, `tests/infrastructure/test_sqlite_article_repository.py` |
| 3 | Unavailable RSS feed | `tests/infrastructure/test_rss_source.py`, `tests/test_cli.py` |
| 4 | Malformed RSS response | `tests/infrastructure/test_rss_source.py` |
| 5 | Insufficient extractable content | `tests/infrastructure/test_trafilatura_extractor.py`, `tests/application/test_processing.py` |
| 6 | LLM timeout / provider transport failure | `tests/infrastructure/test_openai_generator.py` (`test_sdk_operational_failures_...`) |
| 7 | Invalid structured output | `tests/infrastructure/test_openai_generator.py` (validation exhaustion) |
| 8 | Persistence across reopen | `tests/infrastructure/test_processing_end_to_end.py`, `tests/infrastructure/test_dashboard_end_to_end.py` |
| 9 | One failure among multiple Articles | `tests/application/test_processing.py` |
| 10 | Incomplete dashboard data | `tests/presentation/test_dashboard_routes.py` |
| Privacy | Cross-surface secret non-leakage | `tests/test_privacy_regression.py` |

Restart coverage note: the engine-disposal/reopen tests in the two
`*_end_to_end.py` files are accepted as sufficient restart-equivalent coverage
for Phase 1; no subprocess restart test is added.

## 4. Controlled live single-Article validation (separate approval required)

This is the one roadmap acceptance step that requires a live OpenAI call. It
is **never** run in CI and requires separate, explicit approval each time.

Preconditions and rules:

- Requires explicit approval before any live call.
- Credentials are set **locally** in the environment or `.env`. Do **not**
  paste the API key into a chat or commit it.
- Use a **disposable** SQLite database via a temporary `DATABASE_URL`.
- Bound the run to **one** Article: serve a one-entry RSS document from a
  temporary localhost HTTP server and point `RSS_URL` at it; that single entry
  links to one selected, publicly accessible real Article. Do **not** use the
  live full feed window when a one-entry local wrapper can bound the run.
- Do **not** add a production "process one URL" command for this; use the
  existing `process-feed`.

Procedure:

1. Approve the live validation.
2. Start a temporary localhost HTTP server serving a one-entry RSS document.
3. Set `RSS_URL` to that local URL and `DATABASE_URL` to a disposable temp file.
4. `uv run alembic upgrade head`.
5. `uv run python -m app.cli process-feed`.
6. Verify persistence and `ANALYZED` status (via the dashboard and/or a
   read-only check).
7. Start the dashboard (`uv run uvicorn main:app`) and inspect the article and
   its Learning Note.
8. Rerun `process-feed` to confirm idempotency (the article is skipped /
   deduplicated, no second Learning Note).
9. Produce a **sanitized** report: stages reached and success/failure only —
   never Article body, prompt, API key, or provider output.
10. Delete the disposable database and stop/remove the temporary RSS
    server/file.

## 5. Release completion

- [ ] Known-limitations review (README "Known Limitations" is current).
- [ ] Documentation review (README, ARCHITECTURE, PROMPTS current).
- [ ] Disposable data cleaned up (no temp DB or RSS file left behind; none
      committed).
- [ ] Optional operator-created `v0.1.0` Git tag — **only** after Sprint 8 is
      merged, the controlled live validation has succeeded, and final approval
      is given. No GitHub release is required for Phase 1 unless separately
      requested.

## 6. Safe local database reset

To reset a local database, first confirm `DATABASE_URL`, then delete only that
known disposable/local file (for example the default
`./database/currentmind.db`). Never blindly delete a database at an unknown
path. Re-create the schema with `uv run alembic upgrade head`.

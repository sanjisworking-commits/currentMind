"""FastAPI presentation layer: application factory, health check, and dashboard.

The dashboard is strictly read-only. Every route renders server-side Jinja2
templates (autoescaping on) and only ever calls the injected `DashboardQuery`;
no route writes to the database, calls the processing pipeline, or makes an
external request. Template and static asset directories are resolved relative
to this file, so the app works regardless of the current working directory.
"""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.application.dashboard import DashboardQuery, DashboardQueryService
from app.application.repositories import RepositoryError
from app.infrastructure.config import get_settings
from app.infrastructure.database import create_engine_from_url, create_session_factory
from app.infrastructure.sqlite_repositories import (
    SQLiteArticleRepository,
    SQLiteLearningNoteRepository,
)
from app.presentation import view_helpers

PRESENTATION_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PRESENTATION_DIR / "templates"
STATIC_DIR = PRESENTATION_DIR / "static"


def _build_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["status_presentation"] = view_helpers.status_presentation
    templates.env.globals["humanize_source"] = view_helpers.humanize_source
    templates.env.globals["format_date"] = view_helpers.format_date
    templates.env.globals["format_datetime"] = view_helpers.format_datetime
    templates.env.globals["iso_datetime"] = view_helpers.iso_datetime
    return templates


def _build_default_query() -> DashboardQuery:
    """Construct the production query service.

    Building the engine and session factory opens no database connection - a
    connection is established only when the first repository read runs, so a
    missing or unmigrated database does not prevent app construction or
    importing `main`; it surfaces later as the safe 503 path. Requires only
    `DATABASE_URL`; no OpenAI/LLM configuration is read.
    """
    settings = get_settings()
    engine = create_engine_from_url(settings.database_url)
    session_factory = create_session_factory(engine)
    return DashboardQueryService(
        article_repository=SQLiteArticleRepository(session_factory),
        learning_note_repository=SQLiteLearningNoteRepository(session_factory),
    )


def get_dashboard_query(request: Request) -> DashboardQuery:
    """FastAPI dependency returning the app's injected dashboard query object."""
    query: DashboardQuery = request.app.state.dashboard_query
    return query


DashboardQueryDep = Annotated[DashboardQuery, Depends(get_dashboard_query)]


def create_app(*, dashboard_query: DashboardQuery | None = None) -> FastAPI:
    """Build and return the configured FastAPI application.

    `dashboard_query` may be injected (for tests, or an alternate composition);
    when omitted, a real SQLite-backed `DashboardQueryService` is constructed,
    without opening a database connection at construction time.
    """
    app = FastAPI(title="CurrentMind")
    templates = _build_templates()
    app.state.dashboard_query = (
        dashboard_query if dashboard_query is not None else _build_default_query()
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report application liveness without touching dashboard data."""
        get_settings()
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, query: DashboardQueryDep) -> HTMLResponse:
        """Render the most recent Articles as a read-only list."""
        cards = query.list_recent_articles()
        return templates.TemplateResponse(request, "home.html", {"cards": cards})

    @app.get("/articles/{article_id}", response_class=HTMLResponse, name="article_detail")
    def article_detail(
        request: Request,
        article_id: UUID,
        query: DashboardQueryDep,
    ) -> HTMLResponse:
        """Render one Article's detail page, with its Learning Note when present.

        A malformed `article_id` is rejected by FastAPI as 422 before this
        runs; a well-formed but unknown id renders the 404 page.
        """
        detail = query.get_article_detail(article_id)
        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        return templates.TemplateResponse(request, "article_detail.html", {"detail": detail})

    @app.exception_handler(RepositoryError)
    def _handle_repository_error(request: Request, exc: RepositoryError) -> HTMLResponse:
        """Render a fixed, safe 503 page for any dashboard read failure.

        The underlying exception is never rendered: no message, SQL, parameters,
        database URL, path, or stack trace reaches the response.
        """
        return templates.TemplateResponse(request, "503.html", {}, status_code=503)

    return app

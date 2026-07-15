"""FastAPI presentation layer: application factory and routes."""

from fastapi import FastAPI

from app.infrastructure.config import get_settings


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(title="CurrentMind")

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report application liveness."""
        get_settings()
        return {"status": "ok"}

    return app

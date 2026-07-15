"""CurrentMind application entry point."""

import uvicorn

from app.infrastructure.config import get_settings
from app.infrastructure.logging import configure_logging
from app.presentation.api import create_app

configure_logging(get_settings().log_level)
app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

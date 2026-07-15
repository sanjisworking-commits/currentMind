"""Application logging configuration."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure standard library logging for the application.

    Logs to stdout only. Never logs secrets, API keys, or full request/response
    bodies; callers must avoid passing sensitive values into log messages.
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

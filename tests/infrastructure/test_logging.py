import sys
from typing import Any

import pytest

from app.infrastructure.logging import configure_logging


def test_configure_logging_uses_stdout_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_basic_config(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("logging.basicConfig", fake_basic_config)

    configure_logging("INFO")

    assert captured["stream"] is sys.stdout

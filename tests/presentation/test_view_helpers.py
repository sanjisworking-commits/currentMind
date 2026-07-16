"""Tests for `app.presentation.view_helpers` display formatting."""

from datetime import UTC, datetime

from app.domain.enums import ProcessingStatus
from app.presentation.view_helpers import (
    _STATUS_PRESENTATION,
    format_date,
    format_datetime,
    humanize_source,
    iso_datetime,
    status_presentation,
)


def test_status_map_covers_every_processing_status_exactly() -> None:
    # A future enum member cannot silently render with an incorrect fallback.
    assert set(_STATUS_PRESENTATION) == set(ProcessingStatus)


def test_status_presentation_returns_label_class_and_explanation() -> None:
    presentation = status_presentation(ProcessingStatus.ANALYZED)
    assert presentation.label == "Analyzed"
    assert presentation.css_class == "status-analyzed"
    assert presentation.explanation


def test_humanize_known_source() -> None:
    assert humanize_source("indian_express") == "The Indian Express"


def test_humanize_unknown_source_is_safe_fallback() -> None:
    assert humanize_source("some_new_source") == "Some New Source"
    assert humanize_source("x") == "X"


def test_format_date_is_deterministic() -> None:
    assert format_date(datetime(2026, 7, 5, tzinfo=UTC)) == "5 July 2026"


def test_format_date_none_fallback() -> None:
    assert format_date(None) == "Publication date unavailable"


def test_format_datetime_includes_utc() -> None:
    assert format_datetime(datetime(2026, 7, 15, 20, 41, tzinfo=UTC)) == "15 July 2026, 20:41 UTC"


def test_iso_datetime_roundtrips() -> None:
    value = datetime(2026, 7, 15, 20, 41, tzinfo=UTC)
    assert iso_datetime(value) == value.isoformat()

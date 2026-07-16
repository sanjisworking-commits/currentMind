"""Strictly display-related helpers for the dashboard templates.

These functions turn domain values into human-readable display strings -
status labels/classes, source names, and formatted dates. They own no data
selection logic (topic tags, summary excerpts, GS papers, and note existence
are assembled in `app.application.dashboard`), and they never mutate persisted
values. Display labels deliberately live here rather than on the domain enums.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ProcessingStatus


@dataclass(frozen=True, slots=True)
class StatusPresentation:
    """How one `ProcessingStatus` is shown: label, CSS class, short note."""

    label: str
    css_class: str
    explanation: str


# Every ProcessingStatus is mapped explicitly. A test asserts the key set
# equals set(ProcessingStatus), so a future enum member cannot silently fall
# back to an incorrect default.
_STATUS_PRESENTATION: dict[ProcessingStatus, StatusPresentation] = {
    ProcessingStatus.DISCOVERED: StatusPresentation(
        label="Discovered",
        css_class="status-discovered",
        explanation="Queued; article content has not been extracted yet.",
    ),
    ProcessingStatus.EXTRACTED: StatusPresentation(
        label="Extracted",
        css_class="status-extracted",
        explanation="Article text extracted; analysis is pending.",
    ),
    ProcessingStatus.ANALYSIS_PENDING: StatusPresentation(
        label="Analysis pending",
        css_class="status-analysis-pending",
        explanation="Analysis has started or was interrupted before completing.",
    ),
    ProcessingStatus.ANALYZED: StatusPresentation(
        label="Analyzed",
        css_class="status-analyzed",
        explanation="A Learning Note is available for this article.",
    ),
    ProcessingStatus.FAILED: StatusPresentation(
        label="Failed",
        css_class="status-failed",
        explanation="Processing did not complete. See the reason below.",
    ),
}

_SOURCE_LABELS: dict[str, str] = {
    "indian_express": "The Indian Express",
}

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def status_presentation(status: ProcessingStatus) -> StatusPresentation:
    """Return the display label, CSS class, and explanation for a status."""
    return _STATUS_PRESENTATION[status]


def humanize_source(source: str) -> str:
    """Return a human-readable source name, falling back safely for unknowns.

    The persisted source identifier is never modified; an unknown identifier
    is title-cased with underscores turned into spaces so it still reads
    cleanly (and remains autoescaped in templates).
    """
    known = _SOURCE_LABELS.get(source)
    if known is not None:
        return known
    return source.replace("_", " ").strip().title() or source


def format_date(value: datetime | None) -> str:
    """Format a date as `15 July 2026`, or a fixed fallback when absent.

    Uses explicit numeric/name formatting rather than platform-specific
    strftime directives (for example `%-d`), so output is deterministic
    across operating systems.
    """
    if value is None:
        return "Publication date unavailable"
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def format_datetime(value: datetime) -> str:
    """Format a UTC timestamp as `15 July 2026, 20:41 UTC`."""
    return (
        f"{value.day} {_MONTHS[value.month - 1]} {value.year}, "
        f"{value.hour:02d}:{value.minute:02d} UTC"
    )


def iso_datetime(value: datetime) -> str:
    """Return an ISO-8601 string for a `<time datetime=...>` attribute."""
    return value.isoformat()

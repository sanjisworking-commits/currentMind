"""Domain contract for article content extraction outcomes.

Defines the shape of an extraction result so that a later sprint can
implement an ``ArticleExtractor`` against a stable interface. No
extraction behaviour is implemented here.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.domain.base import DomainModel
from app.domain.validation import ensure_utc, non_empty_text, utc_now, validate_http_url


class ExtractionStatus(StrEnum):
    """Outcome of an attempt to extract clean article content from a URL."""

    SUCCESS = "success"
    INSUFFICIENT_CONTENT = "insufficient_content"
    NETWORK_ERROR = "network_error"
    UNSUPPORTED_PAGE = "unsupported_page"
    UNEXPECTED_ERROR = "unexpected_error"


class ExtractedArticle(DomainModel):
    """Result of attempting to extract content from an article URL."""

    url: str
    status: ExtractionStatus
    text: str | None = None
    extracted_at: datetime = Field(default_factory=utc_now)
    error_reason: str | None = None

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("extracted_at")
    @classmethod
    def _validate_extracted_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("error_reason")
    @classmethod
    def _validate_error_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return non_empty_text(value)

    @model_validator(mode="before")
    @classmethod
    def _validate_status_consistency(cls, data: Any) -> Any:
        # mode="before" (rather than "after") so that, under validate_assignment,
        # this sees the complete proposed field state before any field is
        # mutated on the instance - an invalid proposal is rejected outright
        # instead of being applied and then flagged.
        if not isinstance(data, dict):
            return data
        status = data.get("status")
        text = data.get("text")
        error_reason = data.get("error_reason")
        if status == ExtractionStatus.SUCCESS:
            if text is None or not str(text).strip():
                raise ValueError("a successful extraction must include non-empty text")
            if error_reason is not None:
                raise ValueError("a successful extraction must not include an error_reason")
        elif status is not None and error_reason is None:
            raise ValueError(f"status {status!r} requires a non-empty error_reason")
        return data

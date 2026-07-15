"""Domain contract for article content extraction outcomes.

Defines the shape of an extraction result so that a later sprint can
implement an ``ArticleExtractor`` against a stable interface. No
extraction behaviour is implemented here.
"""

from datetime import datetime
from enum import StrEnum

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

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> "ExtractedArticle":
        if self.status is ExtractionStatus.SUCCESS:
            if self.text is None or not self.text.strip():
                raise ValueError("a successful extraction must include non-empty text")
            if self.error_reason is not None:
                raise ValueError("a successful extraction must not include an error_reason")
        elif self.error_reason is None:
            raise ValueError(f"status '{self.status}' requires a non-empty error_reason")
        return self

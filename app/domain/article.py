"""Article domain models: pre-persistence candidates and persisted articles."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.enums import ProcessingStatus
from app.domain.validation import ensure_utc, non_empty_text, utc_now, validate_http_url


class ArticleCandidate(BaseModel):
    """A source-neutral article discovered from a feed, before persistence."""

    source: str
    external_id: str | None = None
    title: str
    url: str
    author: str | None = None
    published_at: datetime | None = None
    categories: list[str] = Field(default_factory=list)

    @field_validator("source", "title")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return non_empty_text(value)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("published_at")
    @classmethod
    def _validate_published_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)


class Article(BaseModel):
    """A persisted article moving through the processing pipeline."""

    id: UUID = Field(default_factory=uuid4)
    source: str
    external_id: str | None = None
    title: str
    url: str
    author: str | None = None
    published_at: datetime | None = None
    categories: list[str] = Field(default_factory=list)
    raw_text: str | None = None
    processing_status: ProcessingStatus
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("source", "title")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return non_empty_text(value)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return validate_http_url(value)

    @field_validator("published_at")
    @classmethod
    def _validate_published_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _validate_timestamps(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _validate_updated_not_before_created(self) -> "Article":
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self

"""Article domain models: pre-persistence candidates and persisted articles."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.domain.base import DomainModel
from app.domain.enums import ProcessingStatus
from app.domain.validation import (
    clean_text_list,
    ensure_utc,
    non_empty_text,
    utc_now,
    validate_http_url,
)


class ArticleCandidate(DomainModel):
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

    @field_validator("categories")
    @classmethod
    def _validate_categories(cls, value: list[str]) -> list[str]:
        return clean_text_list(value)


class Article(DomainModel):
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
    failure_reason: str | None = None
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

    @field_validator("categories")
    @classmethod
    def _validate_categories(cls, value: list[str]) -> list[str]:
        return clean_text_list(value)

    @field_validator("failure_reason")
    @classmethod
    def _validate_failure_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return non_empty_text(value)

    @model_validator(mode="before")
    @classmethod
    def _validate_failure_reason_consistency(cls, data: Any) -> Any:
        # mode="before" (rather than "after") so that, under validate_assignment,
        # this sees the complete proposed field state before any field is
        # mutated on the instance - an invalid proposal is rejected outright
        # instead of being applied and then flagged.
        if not isinstance(data, dict):
            return data
        processing_status = data.get("processing_status")
        failure_reason = data.get("failure_reason")
        if processing_status == ProcessingStatus.FAILED:
            if failure_reason is None or not str(failure_reason).strip():
                raise ValueError("a failed article must include a non-empty failure_reason")
        elif processing_status is not None and failure_reason is not None:
            raise ValueError(
                f"processing_status {processing_status!r} must not include a failure_reason"
            )
        return data

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime, info: ValidationInfo) -> datetime:
        value = ensure_utc(value)
        updated_at = info.data.get("updated_at")
        if updated_at is not None and value > updated_at:
            raise ValueError("created_at must not be later than updated_at")
        return value

    @field_validator("updated_at")
    @classmethod
    def _validate_updated_at(cls, value: datetime, info: ValidationInfo) -> datetime:
        value = ensure_utc(value)
        created_at = info.data.get("created_at")
        if created_at is not None and value < created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return value

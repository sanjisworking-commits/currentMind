"""Learning Note domain models: the structured UPSC-oriented output."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from app.domain.base import DomainModel
from app.domain.enums import GSPaper
from app.domain.validation import clean_text_list, ensure_utc, non_empty_text, utc_now


class PrelimsQuestion(DomainModel):
    """A UPSC-style Prelims multiple-choice question with exactly 4 options."""

    question: str
    options: list[str]
    correct_option: int = Field(strict=True, ge=0, le=3)
    explanation: str

    @field_validator("question", "explanation")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return non_empty_text(value)

    @field_validator("options")
    @classmethod
    def _validate_options(cls, value: list[str]) -> list[str]:
        if len(value) != 4:
            raise ValueError("a PrelimsQuestion must have exactly 4 options")
        cleaned = [non_empty_text(option) for option in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("PrelimsQuestion options must not contain duplicates")
        return cleaned


class MainsQuestion(DomainModel):
    """A UPSC-style Mains analytical question."""

    question: str

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        return non_empty_text(value)


class LearningNoteContent(DomainModel):
    """The AI-authored content of a Learning Note, validated on its own.

    Contains only fields an LLM may produce. Trusted metadata that must never
    be influenced by model output - `id`, `article_id`, `model_name`,
    `prompt_version`, `created_at` - lives exclusively on `LearningNote` and
    is supplied locally by application code (see
    `app.application.learning_notes.assemble_learning_note`).

    Every field is required with no default: OpenAI Structured Outputs
    requires all fields to be present in the model's response, so an
    irrelevant category must be returned as an explicit empty list by the
    model itself, never omitted and backfilled locally.
    """

    summary: str
    why_it_matters: str
    gs_papers: list[GSPaper]
    subjects: list[str]
    syllabus_topics: list[str]
    static_concepts: list[str]
    constitutional_linkages: list[str]
    government_schemes: list[str]
    reports_and_committees: list[str]
    international_dimensions: list[str]
    important_facts: list[str]
    prelims_questions: list[PrelimsQuestion]
    mains_questions: list[MainsQuestion]
    revision_note: str
    keywords: list[str]

    @field_validator("summary", "why_it_matters", "revision_note")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return non_empty_text(value)

    @field_validator(
        "subjects",
        "syllabus_topics",
        "static_concepts",
        "constitutional_linkages",
        "government_schemes",
        "reports_and_committees",
        "international_dimensions",
        "important_facts",
        "keywords",
    )
    @classmethod
    def _validate_text_lists(cls, value: list[str]) -> list[str]:
        return clean_text_list(value)


class LearningNote(DomainModel):
    """The structured, UPSC-oriented learning output generated from an article."""

    id: UUID = Field(default_factory=uuid4)
    article_id: UUID
    summary: str
    why_it_matters: str
    gs_papers: list[GSPaper] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    syllabus_topics: list[str] = Field(default_factory=list)
    static_concepts: list[str] = Field(default_factory=list)
    constitutional_linkages: list[str] = Field(default_factory=list)
    government_schemes: list[str] = Field(default_factory=list)
    reports_and_committees: list[str] = Field(default_factory=list)
    international_dimensions: list[str] = Field(default_factory=list)
    important_facts: list[str] = Field(default_factory=list)
    prelims_questions: list[PrelimsQuestion] = Field(default_factory=list)
    mains_questions: list[MainsQuestion] = Field(default_factory=list)
    revision_note: str
    keywords: list[str] = Field(default_factory=list)
    model_name: str
    prompt_version: str
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("summary", "why_it_matters", "revision_note", "model_name", "prompt_version")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        return non_empty_text(value)

    @field_validator(
        "subjects",
        "syllabus_topics",
        "static_concepts",
        "constitutional_linkages",
        "government_schemes",
        "reports_and_committees",
        "international_dimensions",
        "important_facts",
        "keywords",
    )
    @classmethod
    def _validate_text_lists(cls, value: list[str]) -> list[str]:
        return clean_text_list(value)

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

"""Learning Note domain models: the structured UPSC-oriented output."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import GSPaper
from app.domain.validation import ensure_utc, non_empty_text, utc_now


class PrelimsQuestion(BaseModel):
    """A UPSC-style Prelims multiple-choice question with exactly 4 options."""

    question: str
    options: list[str]
    correct_option: int
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

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "PrelimsQuestion":
        if not 0 <= self.correct_option < len(self.options):
            raise ValueError("correct_option must reference an existing option")
        return self


class MainsQuestion(BaseModel):
    """A UPSC-style Mains analytical question."""

    question: str

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        return non_empty_text(value)


class LearningNote(BaseModel):
    """The structured, UPSC-oriented learning output generated from an article."""

    model_config = ConfigDict(protected_namespaces=())

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

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

"""Application-facing contract for generating Learning Notes from Articles.

Concrete infrastructure adapters (for example an OpenAI-based implementation)
implement `LearningNoteGenerator`. Application-layer workflows depend on this
port and on the error types defined here, never on a specific LLM provider
SDK, so the provider can be replaced later without touching orchestration
code.

The generator produces the complete, trusted `LearningNote` - it does not
decide when an Article is ready for analysis (a future orchestration
decision) and it does not persist anything.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.article import Article
from app.domain.learning_note import LearningNote, LearningNoteContent


class LearningNoteGenerationError(Exception):
    """Base error for Learning Note generation failures."""


class LearningNoteProviderError(LearningNoteGenerationError):
    """A non-retryable provider-level failure.

    Covers transport failures, authentication/permission/rate-limit/server
    errors, an explicit model refusal, an incomplete response, and any other
    SDK-level failure that a repeated identical request would not fix.
    """


class LearningNoteValidationError(LearningNoteGenerationError):
    """Raised when bounded validation-retry attempts are exhausted.

    Every attempt produced a completed, non-refusal response, but none ever
    yielded a structurally valid `LearningNoteContent`.
    """


class LearningNoteGenerator(Protocol):
    """Generates a validated Learning Note from an Article's extracted content."""

    def generate(self, article: Article) -> LearningNote:
        """Transform `article.raw_text` into a validated, structured LearningNote.

        Raises:
            ValueError: if `article.raw_text` is None, or is blank or
                whitespace-only. No provider request is made in this case.
            LearningNoteProviderError: for a non-retryable provider failure.
            LearningNoteValidationError: if bounded validation-retry attempts
                are exhausted without producing a valid structured response.
        """
        ...


def assemble_learning_note(
    content: LearningNoteContent,
    *,
    article_id: UUID,
    model_name: str,
    prompt_version: str,
    created_at: datetime | None = None,
) -> LearningNote:
    """Build the final, trusted `LearningNote` from validated AI-authored content.

    Every AI-authored field comes from `content`, named explicitly - never
    from an unchecked dict merge. Every trusted field (`article_id`,
    `model_name`, `prompt_version`) is supplied only from the parameters
    here; the model has no way to influence them, since `LearningNoteContent`
    has no fields corresponding to them. `id` and `created_at` use
    `LearningNote`'s own domain defaults unless `created_at` is explicitly
    injected (for deterministic tests).
    """
    if created_at is None:
        return LearningNote(
            summary=content.summary,
            why_it_matters=content.why_it_matters,
            gs_papers=content.gs_papers,
            subjects=content.subjects,
            syllabus_topics=content.syllabus_topics,
            static_concepts=content.static_concepts,
            constitutional_linkages=content.constitutional_linkages,
            government_schemes=content.government_schemes,
            reports_and_committees=content.reports_and_committees,
            international_dimensions=content.international_dimensions,
            important_facts=content.important_facts,
            prelims_questions=content.prelims_questions,
            mains_questions=content.mains_questions,
            revision_note=content.revision_note,
            keywords=content.keywords,
            article_id=article_id,
            model_name=model_name,
            prompt_version=prompt_version,
        )
    return LearningNote(
        summary=content.summary,
        why_it_matters=content.why_it_matters,
        gs_papers=content.gs_papers,
        subjects=content.subjects,
        syllabus_topics=content.syllabus_topics,
        static_concepts=content.static_concepts,
        constitutional_linkages=content.constitutional_linkages,
        government_schemes=content.government_schemes,
        reports_and_committees=content.reports_and_committees,
        international_dimensions=content.international_dimensions,
        important_facts=content.important_facts,
        prelims_questions=content.prelims_questions,
        mains_questions=content.mains_questions,
        revision_note=content.revision_note,
        keywords=content.keywords,
        article_id=article_id,
        model_name=model_name,
        prompt_version=prompt_version,
        created_at=created_at,
    )

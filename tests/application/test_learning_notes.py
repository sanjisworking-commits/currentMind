"""Tests for `app.application.learning_notes`: the `LearningNoteGenerator`
Protocol shape and the pure `assemble_learning_note` assembly function.

No I/O, no provider, no fakes needed - `assemble_learning_note` is a pure
function operating entirely on in-memory domain objects.
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.learning_notes import LearningNoteGenerator, assemble_learning_note
from app.domain.article import Article
from app.domain.enums import GSPaper
from app.domain.learning_note import (
    LearningNote,
    LearningNoteContent,
    MainsQuestion,
    PrelimsQuestion,
)


def _valid_content(**overrides: object) -> LearningNoteContent:
    kwargs: dict[str, object] = {
        "summary": "A concise summary.",
        "why_it_matters": "It matters because of Z.",
        "gs_papers": [GSPaper.GS2],
        "subjects": ["polity"],
        "syllabus_topics": ["governance"],
        "static_concepts": ["federalism"],
        "constitutional_linkages": ["Article 32"],
        "government_schemes": ["PM-KISAN"],
        "reports_and_committees": ["Sarkaria Commission"],
        "international_dimensions": ["UNSC"],
        "important_facts": ["fact one"],
        "prelims_questions": [
            PrelimsQuestion(
                question="Q",
                options=["A", "B", "C", "D"],
                correct_option=1,
                explanation="E",
            )
        ],
        "mains_questions": [MainsQuestion(question="Discuss X.")],
        "revision_note": "Revise this.",
        "keywords": ["federalism"],
    }
    kwargs.update(overrides)
    return LearningNoteContent(**kwargs)  # type: ignore[arg-type]


def test_assemble_learning_note_uses_supplied_article_id() -> None:
    content = _valid_content()
    article_id = uuid4()
    note = assemble_learning_note(
        content, article_id=article_id, model_name="gpt-test", prompt_version="v1"
    )
    assert note.article_id == article_id


def test_assemble_learning_note_uses_supplied_model_name_and_prompt_version() -> None:
    content = _valid_content()
    note = assemble_learning_note(
        content, article_id=uuid4(), model_name="gpt-5.4", prompt_version="v1"
    )
    assert note.model_name == "gpt-5.4"
    assert note.prompt_version == "v1"


def test_assemble_learning_note_generates_id_and_created_at_by_default() -> None:
    content = _valid_content()
    first = assemble_learning_note(
        content, article_id=uuid4(), model_name="m", prompt_version="v1"
    )
    second = assemble_learning_note(
        content, article_id=uuid4(), model_name="m", prompt_version="v1"
    )
    assert first.id != second.id
    assert first.created_at.tzinfo == UTC


def test_assemble_learning_note_accepts_injected_created_at() -> None:
    content = _valid_content()
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    note = assemble_learning_note(
        content, article_id=uuid4(), model_name="m", prompt_version="v1", created_at=fixed
    )
    assert note.created_at == fixed


def test_assemble_learning_note_transfers_every_ai_authored_field() -> None:
    content = _valid_content()
    note = assemble_learning_note(content, article_id=uuid4(), model_name="m", prompt_version="v1")
    assert note.summary == content.summary
    assert note.why_it_matters == content.why_it_matters
    assert note.gs_papers == content.gs_papers
    assert note.subjects == content.subjects
    assert note.syllabus_topics == content.syllabus_topics
    assert note.static_concepts == content.static_concepts
    assert note.constitutional_linkages == content.constitutional_linkages
    assert note.government_schemes == content.government_schemes
    assert note.reports_and_committees == content.reports_and_committees
    assert note.international_dimensions == content.international_dimensions
    assert note.important_facts == content.important_facts
    assert note.prelims_questions == content.prelims_questions
    assert note.mains_questions == content.mains_questions
    assert note.revision_note == content.revision_note
    assert note.keywords == content.keywords


def test_assemble_learning_note_trusted_metadata_comes_only_from_local_inputs() -> None:
    """`LearningNoteContent` has no id/article_id/model_name/prompt_version/
    created_at fields at all, so there is no dict-merge or attribute path
    through which content could influence trusted metadata. This test
    documents and locks in that guarantee.
    """
    content = _valid_content()
    article_id = uuid4()
    note = assemble_learning_note(
        content, article_id=article_id, model_name="trusted-model", prompt_version="trusted-v1"
    )
    assert not hasattr(content, "id")
    assert not hasattr(content, "article_id")
    assert not hasattr(content, "model_name")
    assert not hasattr(content, "prompt_version")
    assert not hasattr(content, "created_at")
    assert note.article_id == article_id
    assert note.model_name == "trusted-model"
    assert note.prompt_version == "trusted-v1"


def test_learning_note_generator_protocol_shape() -> None:
    """A minimal conforming implementation satisfies the Protocol structurally."""

    class _StubGenerator:
        def generate(self, article: Article) -> LearningNote:
            raise NotImplementedError

    generator: LearningNoteGenerator = _StubGenerator()
    assert hasattr(generator, "generate")

from datetime import UTC
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import GSPaper
from app.domain.learning_note import LearningNote, MainsQuestion, PrelimsQuestion


def _valid_options() -> list[str]:
    return ["Option A", "Option B", "Option C", "Option D"]


def test_valid_prelims_question() -> None:
    question = PrelimsQuestion(
        question="Which article deals with X?",
        options=_valid_options(),
        correct_option=2,
        explanation="Because of Y.",
    )
    assert question.options == _valid_options()


@pytest.mark.parametrize("options", [["A", "B", "C"], ["A", "B", "C", "D", "E"]])
def test_prelims_question_requires_exactly_four_options(options: list[str]) -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(question="Q", options=options, correct_option=0, explanation="E")


def test_prelims_question_rejects_duplicate_options() -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(
            question="Q",
            options=["A", "A", "B", "C"],
            correct_option=0,
            explanation="E",
        )


@pytest.mark.parametrize("correct_option", [-1, 4])
def test_prelims_question_rejects_out_of_range_correct_option(correct_option: int) -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(
            question="Q",
            options=_valid_options(),
            correct_option=correct_option,
            explanation="E",
        )


def test_prelims_question_rejects_empty_question() -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(question="  ", options=_valid_options(), correct_option=0, explanation="E")


def test_prelims_question_rejects_empty_explanation() -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(
            question="Q", options=_valid_options(), correct_option=0, explanation="  "
        )


def test_prelims_question_rejects_empty_option_text() -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(
            question="Q",
            options=["A", "B", "  ", "D"],
            correct_option=0,
            explanation="E",
        )


@pytest.mark.parametrize("correct_option", [True, "2", 1.0])
def test_prelims_question_rejects_non_strict_correct_option(correct_option: object) -> None:
    with pytest.raises(ValidationError):
        PrelimsQuestion(
            question="Q",
            options=_valid_options(),
            correct_option=correct_option,  # type: ignore[arg-type]
            explanation="E",
        )


def test_valid_mains_question() -> None:
    question = MainsQuestion(question="Discuss the significance of X.")
    assert question.question == "Discuss the significance of X."


def test_mains_question_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        MainsQuestion(question="   ")


def _valid_learning_note_kwargs() -> dict[str, Any]:
    return {
        "article_id": uuid4(),
        "summary": "A concise summary.",
        "why_it_matters": "It matters because of Z.",
        "revision_note": "Revise the key points.",
        "model_name": "gpt-test",
        "prompt_version": "v1",
    }


def test_valid_learning_note_with_minimal_fields() -> None:
    note = LearningNote(**_valid_learning_note_kwargs())
    assert note.gs_papers == []
    assert note.prelims_questions == []
    assert note.mains_questions == []
    assert note.created_at.tzinfo == UTC


def test_learning_note_ids_are_unique_by_default() -> None:
    kwargs = _valid_learning_note_kwargs()
    first = LearningNote(**kwargs)
    second = LearningNote(**kwargs)
    assert first.id != second.id


def test_learning_note_accepts_gs_papers_enum_values() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["gs_papers"] = [GSPaper.GS2, GSPaper.GS3]
    note = LearningNote(**kwargs)
    assert note.gs_papers == [GSPaper.GS2, GSPaper.GS3]


def test_learning_note_rejects_unknown_gs_paper() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["gs_papers"] = ["gs5"]
    with pytest.raises(ValidationError):
        LearningNote(**kwargs)


@pytest.mark.parametrize(
    "field", ["summary", "why_it_matters", "revision_note", "model_name", "prompt_version"]
)
def test_learning_note_rejects_empty_required_text(field: str) -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs[field] = "   "
    with pytest.raises(ValidationError):
        LearningNote(**kwargs)


def test_learning_note_default_lists_are_independent() -> None:
    first = LearningNote(**_valid_learning_note_kwargs())
    second = LearningNote(**_valid_learning_note_kwargs())
    first.keywords.append("x")
    assert second.keywords == []


def test_learning_note_propagates_invalid_nested_prelims_question() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["prelims_questions"] = [
        {"question": "Q", "options": ["A", "B"], "correct_option": 0, "explanation": "E"}
    ]
    with pytest.raises(ValidationError):
        LearningNote(**kwargs)


def test_learning_note_accepts_valid_nested_questions() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["prelims_questions"] = [
        {
            "question": "Q",
            "options": _valid_options(),
            "correct_option": 0,
            "explanation": "E",
        }
    ]
    kwargs["mains_questions"] = [{"question": "Discuss X."}]
    note = LearningNote(**kwargs)
    assert len(note.prelims_questions) == 1
    assert len(note.mains_questions) == 1


def test_learning_note_rejects_unknown_field() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["bogus_field"] = "x"
    with pytest.raises(ValidationError):
        LearningNote(**kwargs)


@pytest.mark.parametrize(
    "field",
    [
        "subjects",
        "syllabus_topics",
        "static_concepts",
        "constitutional_linkages",
        "government_schemes",
        "reports_and_committees",
        "international_dimensions",
        "important_facts",
        "keywords",
    ],
)
def test_learning_note_rejects_blank_text_list_entry(field: str) -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs[field] = ["Polity", "   "]
    with pytest.raises(ValidationError):
        LearningNote(**kwargs)


def test_learning_note_rejects_duplicate_text_list_entries() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["keywords"] = ["monsoon", " monsoon "]
    with pytest.raises(ValidationError):
        LearningNote(**kwargs)


def test_learning_note_strips_text_list_entries() -> None:
    kwargs = _valid_learning_note_kwargs()
    kwargs["keywords"] = [" monsoon ", "el nino"]
    note = LearningNote(**kwargs)
    assert note.keywords == ["monsoon", "el nino"]

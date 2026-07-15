"""Mapper tests: pure Article/LearningNote <-> ORM row translation.

No database is used here - these functions only translate in-memory values.
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

from app.domain.article import Article
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import MainsQuestion, PrelimsQuestion
from app.infrastructure.mappers import (
    article_to_row,
    learning_note_to_row,
    row_to_article,
    row_to_learning_note,
    update_row_from_article,
)
from tests.infrastructure.factories import make_article, make_learning_note


def test_article_round_trip_preserves_all_fields() -> None:
    article = make_article(
        external_id="ext-42",
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=["polity", "economy"],
        raw_text="Body text.",
        processing_status=ProcessingStatus.ANALYZED,
    )

    reconstructed = row_to_article(article_to_row(article))

    assert reconstructed == article


def test_article_round_trip_preserves_uuid_type() -> None:
    article = make_article()
    reconstructed = row_to_article(article_to_row(article))
    assert reconstructed.id == article.id
    assert isinstance(reconstructed.id, type(article.id))


def test_article_round_trip_preserves_optional_none_fields() -> None:
    article = make_article(external_id=None, author=None, published_at=None, raw_text=None)
    reconstructed = row_to_article(article_to_row(article))
    assert reconstructed.external_id is None
    assert reconstructed.author is None
    assert reconstructed.published_at is None
    assert reconstructed.raw_text is None


def test_article_round_trip_preserves_every_processing_status() -> None:
    for status in ProcessingStatus:
        failure_reason = "a reason" if status == ProcessingStatus.FAILED else None
        article = make_article(processing_status=status, failure_reason=failure_reason)
        reconstructed = row_to_article(article_to_row(article))
        assert reconstructed.processing_status == status
        assert reconstructed.failure_reason == failure_reason


def test_article_round_trip_preserves_failure_reason() -> None:
    article = make_article(
        processing_status=ProcessingStatus.FAILED, failure_reason="Network timeout."
    )
    reconstructed = row_to_article(article_to_row(article))
    assert reconstructed.failure_reason == "Network timeout."


def test_article_round_trip_preserves_large_text() -> None:
    large_text = "Paragraph. " * 20_000
    article = make_article(raw_text=large_text)
    reconstructed = row_to_article(article_to_row(article))
    assert reconstructed.raw_text == large_text


def test_article_round_trip_preserves_empty_categories() -> None:
    article = make_article(categories=[])
    reconstructed = row_to_article(article_to_row(article))
    assert reconstructed.categories == []


def test_article_row_reconstructs_naive_datetime_as_utc() -> None:
    article = make_article()
    row = article_to_row(article)
    row.created_at = row.created_at.replace(tzinfo=None)
    row.updated_at = row.updated_at.replace(tzinfo=None)

    reconstructed = row_to_article(row)

    assert reconstructed.created_at.tzinfo == UTC
    assert reconstructed.updated_at.tzinfo == UTC


def test_article_row_normalizes_non_utc_aware_datetime() -> None:
    article = make_article()
    row = article_to_row(article)
    ist = timezone(timedelta(hours=5, minutes=30))
    row.created_at = row.created_at.astimezone(ist)

    reconstructed = row_to_article(row)

    assert reconstructed.created_at.tzinfo == UTC
    assert reconstructed.created_at == article.created_at


def test_article_categories_are_copied_not_shared() -> None:
    article = make_article(categories=["polity"])
    row = article_to_row(article)

    article.categories.append("mutated")

    assert row.categories == ["polity"]


def test_update_row_from_article_copies_categories_not_shared() -> None:
    original = make_article(categories=["polity"])
    row = article_to_row(original)

    updated = original.model_copy(update={"categories": ["economy"]})
    update_row_from_article(row, updated)
    updated.categories.append("mutated")

    assert row.categories == ["economy"]


def test_update_row_from_article_updates_domain_backed_columns() -> None:
    original = make_article(title="Old Title")
    row = article_to_row(original)

    changed_kwargs = original.model_dump()
    changed_kwargs["title"] = "New Title"
    changed_kwargs["processing_status"] = ProcessingStatus.FAILED
    changed_kwargs["failure_reason"] = "Extraction failed."
    changed = Article(**changed_kwargs)

    update_row_from_article(row, changed)

    reconstructed = row_to_article(row)
    assert reconstructed.title == "New Title"
    assert reconstructed.processing_status == ProcessingStatus.FAILED
    assert reconstructed.failure_reason == "Extraction failed."
    assert reconstructed.id == original.id


def _sample_prelims_question() -> PrelimsQuestion:
    return PrelimsQuestion(
        question="What is the capital of India?",
        options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
        correct_option=1,
        explanation="New Delhi is the capital of India.",
    )


def test_learning_note_round_trip_preserves_all_fields() -> None:
    note = make_learning_note()
    note = note.model_copy(
        update={
            "gs_papers": [GSPaper.GS2, GSPaper.GS3],
            "subjects": ["polity", "economy"],
            "syllabus_topics": ["governance"],
            "static_concepts": ["federalism"],
            "constitutional_linkages": ["Article 32"],
            "government_schemes": ["PM-KISAN"],
            "reports_and_committees": ["Sarkaria Commission"],
            "international_dimensions": ["UNSC"],
            "important_facts": ["fact one"],
            "prelims_questions": [_sample_prelims_question()],
            "mains_questions": [MainsQuestion(question="Discuss federalism in India.")],
            "keywords": ["federalism", "governance"],
        }
    )

    reconstructed = row_to_learning_note(learning_note_to_row(note))

    assert reconstructed == note


def test_learning_note_round_trip_preserves_uuid_types() -> None:
    note = make_learning_note()
    reconstructed = row_to_learning_note(learning_note_to_row(note))
    assert reconstructed.id == note.id
    assert reconstructed.article_id == note.article_id
    assert isinstance(reconstructed.id, type(note.id))
    assert isinstance(reconstructed.article_id, type(note.article_id))


def test_learning_note_round_trip_preserves_empty_list_fields() -> None:
    note = make_learning_note()
    reconstructed = row_to_learning_note(learning_note_to_row(note))
    assert reconstructed.gs_papers == []
    assert reconstructed.subjects == []
    assert reconstructed.prelims_questions == []
    assert reconstructed.mains_questions == []


def test_learning_note_round_trip_preserves_gs_papers() -> None:
    note = make_learning_note().model_copy(update={"gs_papers": [GSPaper.GS1, GSPaper.GS4]})
    reconstructed = row_to_learning_note(learning_note_to_row(note))
    assert reconstructed.gs_papers == [GSPaper.GS1, GSPaper.GS4]
    assert all(isinstance(paper, GSPaper) for paper in reconstructed.gs_papers)


def test_learning_note_round_trip_preserves_nested_prelims_questions() -> None:
    question = _sample_prelims_question()
    note = make_learning_note().model_copy(update={"prelims_questions": [question]})

    reconstructed = row_to_learning_note(learning_note_to_row(note))

    assert reconstructed.prelims_questions == [question]
    assert isinstance(reconstructed.prelims_questions[0], PrelimsQuestion)


def test_learning_note_round_trip_preserves_nested_mains_questions() -> None:
    question = MainsQuestion(question="Analyze the impact of federalism.")
    note = make_learning_note().model_copy(update={"mains_questions": [question]})

    reconstructed = row_to_learning_note(learning_note_to_row(note))

    assert reconstructed.mains_questions == [question]
    assert isinstance(reconstructed.mains_questions[0], MainsQuestion)


def test_learning_note_row_reconstructs_naive_datetime_as_utc() -> None:
    note = make_learning_note()
    row = learning_note_to_row(note)
    row.created_at = row.created_at.replace(tzinfo=None)

    reconstructed = row_to_learning_note(row)

    assert reconstructed.created_at.tzinfo == UTC


def test_learning_note_list_fields_are_copied_not_shared() -> None:
    note = make_learning_note().model_copy(update={"subjects": ["polity"]})
    row = learning_note_to_row(note)

    note.subjects.append("mutated")

    assert row.subjects == ["polity"]


def test_learning_note_round_trip_preserves_article_id_link() -> None:
    article_id = uuid4()
    note = make_learning_note(article_id=article_id)
    reconstructed = row_to_learning_note(learning_note_to_row(note))
    assert reconstructed.article_id == article_id

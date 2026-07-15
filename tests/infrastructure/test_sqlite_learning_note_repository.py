"""Contract, constraint, and cascade tests for `SQLiteLearningNoteRepository`.

Every test runs against a migration-created temporary SQLite database (see
`conftest.py`); none touch the real development database.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.repositories import (
    ArticleRepository,
    DuplicateLearningNoteError,
    LearningNoteRepository,
    RelatedArticleNotFoundError,
)
from app.domain.enums import GSPaper
from app.infrastructure.orm_models import ArticleRow, LearningNoteRow
from tests.infrastructure.factories import make_article, make_learning_note


def test_add_and_get_by_article_id(
    article_repository: ArticleRepository, learning_note_repository: LearningNoteRepository
) -> None:
    article = make_article()
    article_repository.add(article)
    note = make_learning_note(article_id=article.id)

    learning_note_repository.add(note)
    fetched = learning_note_repository.get_by_article_id(article.id)

    assert fetched == note


def test_get_by_article_id_missing_returns_none(
    learning_note_repository: LearningNoteRepository,
) -> None:
    assert learning_note_repository.get_by_article_id(uuid4()) is None


def test_full_structured_round_trip(
    article_repository: ArticleRepository, learning_note_repository: LearningNoteRepository
) -> None:
    article = make_article()
    article_repository.add(article)
    note = make_learning_note(article_id=article.id).model_copy(
        update={
            "gs_papers": [GSPaper.GS2],
            "subjects": ["polity"],
            "syllabus_topics": ["governance"],
            "static_concepts": ["federalism"],
            "constitutional_linkages": ["Article 32"],
            "government_schemes": ["PM-KISAN"],
            "reports_and_committees": ["Sarkaria Commission"],
            "international_dimensions": ["UNSC"],
            "important_facts": ["fact one"],
            "keywords": ["federalism"],
        }
    )

    learning_note_repository.add(note)
    fetched = learning_note_repository.get_by_article_id(article.id)

    assert fetched == note


def test_missing_parent_article_translated_meaningfully(
    learning_note_repository: LearningNoteRepository,
) -> None:
    orphan_note = make_learning_note(article_id=uuid4())

    with pytest.raises(RelatedArticleNotFoundError):
        learning_note_repository.add(orphan_note)


def test_second_note_for_same_article_rejected(
    article_repository: ArticleRepository, learning_note_repository: LearningNoteRepository
) -> None:
    article = make_article()
    article_repository.add(article)
    first_note = make_learning_note(article_id=article.id)
    learning_note_repository.add(first_note)

    second_note = make_learning_note(article_id=article.id)
    with pytest.raises(DuplicateLearningNoteError):
        learning_note_repository.add(second_note)


def test_rollback_leaves_no_partial_row_on_duplicate(
    article_repository: ArticleRepository, learning_note_repository: LearningNoteRepository
) -> None:
    article = make_article()
    article_repository.add(article)
    first_note = make_learning_note(article_id=article.id)
    learning_note_repository.add(first_note)

    second_note = make_learning_note(article_id=article.id)
    with pytest.raises(DuplicateLearningNoteError):
        learning_note_repository.add(second_note)

    # only the original note is stored, and the repository remains usable
    fetched = learning_note_repository.get_by_article_id(article.id)
    assert fetched == first_note

    other_article = make_article(url="https://x.com/other", external_id="ext-other")
    article_repository.add(other_article)
    other_note = make_learning_note(article_id=other_article.id)
    learning_note_repository.add(other_note)
    assert learning_note_repository.get_by_article_id(other_article.id) == other_note


def test_parent_article_deletion_cascades_to_learning_note(
    article_repository: ArticleRepository,
    learning_note_repository: LearningNoteRepository,
    session_factory: sessionmaker[Session],
) -> None:
    article = make_article()
    article_repository.add(article)
    note = make_learning_note(article_id=article.id)
    learning_note_repository.add(note)

    with session_factory.begin() as session:
        row = session.get(ArticleRow, article.id)
        session.delete(row)

    with session_factory() as session:
        remaining = session.execute(
            select(LearningNoteRow).where(LearningNoteRow.article_id == article.id)
        ).scalar_one_or_none()
        assert remaining is None

"""End-to-end dashboard tests over real SQLite persistence.

Real Alembic-migrated temporary database, real repositories, real
`DashboardQueryService` injected into `create_app`. Only the HTTP client is a
test harness; no network, no OpenAI, no development database. These tests also
assert that dashboard GET requests never mutate persisted state.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.application.dashboard import DashboardQueryService
from app.domain.article import Article
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import LearningNote, MainsQuestion, PrelimsQuestion
from app.infrastructure.database import create_engine_from_url, create_session_factory
from app.infrastructure.sqlite_repositories import (
    SQLiteArticleRepository,
    SQLiteLearningNoteRepository,
)
from app.presentation.api import create_app


@pytest.fixture
def client_and_repos(
    session_factory: sessionmaker[Session],
) -> Iterator[tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository]]:
    articles = SQLiteArticleRepository(session_factory)
    notes = SQLiteLearningNoteRepository(session_factory)
    service = DashboardQueryService(
        article_repository=articles, learning_note_repository=notes
    )
    with TestClient(create_app(dashboard_query=service)) as client:
        yield client, articles, notes


def _analyzed_article() -> Article:
    return Article(
        source="indian_express",
        external_id="e2e-1",
        title="A Persisted Title",
        url="https://indianexpress.com/upsc/persisted",
        author="Jane Doe",
        categories=["polity"],
        raw_text="SENSITIVE-RAW-TEXT-MARKER",
        processing_status=ProcessingStatus.ANALYZED,
    )


def _rich_note(article_id: object) -> LearningNote:
    return LearningNote(
        article_id=article_id,  # type: ignore[arg-type]
        summary="Persisted executive summary.",
        why_it_matters="Persisted why.",
        gs_papers=[GSPaper.GS2],
        subjects=["polity"],
        syllabus_topics=["governance"],
        static_concepts=["federalism"],
        important_facts=["Persisted fact."],
        prelims_questions=[
            PrelimsQuestion(
                question="Persisted question?",
                options=["Alpha", "Bravo", "Charlie", "Delta"],
                correct_option=1,
                explanation="Bravo is correct.",
            )
        ],
        mains_questions=[MainsQuestion(question="Persisted mains question.")],
        revision_note="Persisted revision note.",
        keywords=["federalism"],
        model_name="gpt-test",
        prompt_version="v1",
    )


def test_persisted_article_appears_on_home(
    client_and_repos: tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository],
) -> None:
    client, articles, notes = client_and_repos
    article = _analyzed_article()
    articles.add(article)
    notes.add(_rich_note(article.id))

    response = client.get("/")

    assert response.status_code == 200
    assert "A Persisted Title" in response.text
    assert "SENSITIVE-RAW-TEXT-MARKER" not in response.text


def test_persisted_note_renders_on_detail(
    client_and_repos: tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository],
) -> None:
    client, articles, notes = client_and_repos
    article = _analyzed_article()
    articles.add(article)
    notes.add(_rich_note(article.id))

    response = client.get(f"/articles/{article.id}")

    assert response.status_code == 200
    body = response.text
    assert "Persisted executive summary." in body
    assert "Persisted revision note." in body
    assert "B. Bravo" in body
    assert "Persisted mains question." in body
    assert "SENSITIVE-RAW-TEXT-MARKER" not in body


def test_incomplete_article_renders_status_without_note(
    client_and_repos: tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository],
) -> None:
    client, articles, _ = client_and_repos
    article = Article(
        source="indian_express",
        external_id="e2e-2",
        title="Incomplete Article",
        url="https://indianexpress.com/upsc/incomplete",
        processing_status=ProcessingStatus.DISCOVERED,
    )
    articles.add(article)

    response = client.get(f"/articles/{article.id}")

    assert response.status_code == 200
    assert "No Learning Note is available" in response.text
    assert "Discovered" in response.text


def test_missing_article_returns_404(
    client_and_repos: tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository],
) -> None:
    client, _, _ = client_and_repos
    response = client.get(f"/articles/{uuid4()}")
    assert response.status_code == 404


def test_data_survives_engine_dispose_and_reopen(migrated_db_url: str) -> None:
    engine = create_engine_from_url(migrated_db_url)
    factory = create_session_factory(engine)
    articles = SQLiteArticleRepository(factory)
    notes = SQLiteLearningNoteRepository(factory)
    article = _analyzed_article()
    articles.add(article)
    notes.add(_rich_note(article.id))
    engine.dispose()

    reopened = create_engine_from_url(migrated_db_url)
    try:
        fresh = create_session_factory(reopened)
        service = DashboardQueryService(
            article_repository=SQLiteArticleRepository(fresh),
            learning_note_repository=SQLiteLearningNoteRepository(fresh),
        )
        with TestClient(create_app(dashboard_query=service)) as client:
            response = client.get(f"/articles/{article.id}")
            assert response.status_code == 200
            assert "Persisted executive summary." in response.text
    finally:
        reopened.dispose()


def test_get_requests_do_not_mutate_persisted_state(
    client_and_repos: tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository],
) -> None:
    client, articles, notes = client_and_repos
    article = _analyzed_article()
    articles.add(article)
    notes.add(_rich_note(article.id))

    before_article = articles.get_by_id(article.id)
    before_note = notes.get_by_article_id(article.id)
    assert before_article is not None and before_note is not None

    # Exercise both dashboard reads.
    assert client.get("/").status_code == 200
    assert client.get(f"/articles/{article.id}").status_code == 200

    after_article = articles.get_by_id(article.id)
    after_note = notes.get_by_article_id(article.id)
    assert after_article is not None and after_note is not None

    assert after_article.id == before_article.id
    assert after_article.processing_status == before_article.processing_status
    assert after_article.failure_reason == before_article.failure_reason
    assert after_article.raw_text == before_article.raw_text
    assert after_article.created_at == before_article.created_at
    assert after_article.updated_at == before_article.updated_at
    assert after_note.id == before_note.id
    assert after_note.summary == before_note.summary
    assert after_note.prelims_questions == before_note.prelims_questions


def test_engine_reads_only_no_write_engine_from_health(
    client_and_repos: tuple[TestClient, SQLiteArticleRepository, SQLiteLearningNoteRepository],
) -> None:
    client, _, _ = client_and_repos
    # /health must not require or query dashboard data.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

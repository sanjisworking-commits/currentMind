"""Route and template tests for the read-only dashboard.

A small fake implementing the `DashboardQuery` Protocol is injected into
`create_app`; no database, no network, no live provider. Assertions target
semantic fragments and status codes, never whole-page HTML equality.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.application.dashboard import ArticleCard, ArticleDetail
from app.application.repositories import RepositoryError
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import LearningNote, MainsQuestion, PrelimsQuestion
from app.presentation.api import create_app

RAW_TEXT_MARKER = "UNMISTAKABLE-RAW-TEXT-MARKER"


class FakeDashboardQuery:
    """Fake implementing the DashboardQuery Protocol structurally."""

    def __init__(
        self,
        *,
        cards: tuple[ArticleCard, ...] = (),
        details: dict[UUID, ArticleDetail] | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self._cards = cards
        self._details = details or {}
        self._list_error = list_error

    def list_recent_articles(self, *, limit: int = 30) -> tuple[ArticleCard, ...]:
        if self._list_error is not None:
            raise self._list_error
        return self._cards

    def get_article_detail(self, article_id: UUID) -> ArticleDetail | None:
        return self._details.get(article_id)


def _card(
    *,
    article_id: UUID | None = None,
    title: str = "A Title",
    status: ProcessingStatus = ProcessingStatus.ANALYZED,
    has_note: bool = True,
    summary: str | None = "A card summary.",
    gs_papers: tuple[GSPaper, ...] = (GSPaper.GS2,),
    tags: tuple[str, ...] = ("federalism",),
) -> ArticleCard:
    return ArticleCard(
        article_id=article_id or uuid4(),
        title=title,
        source="indian_express",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        processing_status=status,
        has_learning_note=has_note,
        summary_excerpt=summary,
        gs_papers=gs_papers,
        topic_tags=tags,
    )


def _rich_note(article_id: UUID) -> LearningNote:
    return LearningNote(
        article_id=article_id,
        summary="Executive summary body.",
        why_it_matters="Why it matters body.",
        gs_papers=[GSPaper.GS2, GSPaper.GS3],
        subjects=["polity"],
        syllabus_topics=["governance"],
        static_concepts=["federalism"],
        constitutional_linkages=["Article 32"],
        government_schemes=["PM-KISAN"],
        reports_and_committees=["Sarkaria Commission"],
        international_dimensions=["UNSC"],
        important_facts=["Fact one."],
        prelims_questions=[
            PrelimsQuestion(
                question="Which body?",
                options=["Alpha", "Bravo", "Charlie", "Delta"],
                correct_option=2,
                explanation="Charlie is correct.",
            )
        ],
        mains_questions=[MainsQuestion(question="Discuss federalism.")],
        revision_note="Revision note body.",
        keywords=["federalism"],
        model_name="gpt-test",
        prompt_version="v1",
    )


def _detail(
    article_id: UUID,
    *,
    status: ProcessingStatus = ProcessingStatus.ANALYZED,
    failure_reason: str | None = None,
    with_note: bool = True,
    url: str = "https://indianexpress.com/upsc/article?token=SECRETTOKEN",
    title: str = "A Detail Title",
) -> ArticleDetail:
    return ArticleDetail(
        article_id=article_id,
        title=title,
        source="indian_express",
        url=url,
        author="Jane Doe",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        categories=("polity",),
        processing_status=status,
        failure_reason=failure_reason,
        created_at=datetime(2026, 7, 1, 20, 41, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, 20, 41, tzinfo=UTC),
        learning_note=_rich_note(article_id) if with_note else None,
    )


def _client(query: FakeDashboardQuery) -> TestClient:
    return TestClient(create_app(dashboard_query=query))


# --- home ---------------------------------------------------------------------


def test_home_lists_multiple_articles() -> None:
    cards = (_card(title="First"), _card(title="Second"))
    response = _client(FakeDashboardQuery(cards=cards)).get("/")
    assert response.status_code == 200
    assert "First" in response.text
    assert "Second" in response.text


def test_home_empty_state() -> None:
    response = _client(FakeDashboardQuery(cards=())).get("/")
    assert response.status_code == 200
    assert "No articles have been processed yet" in response.text


def test_home_analyzed_card_shows_summary_gs_and_tags() -> None:
    card = _card(summary="A distinctive card summary.", gs_papers=(GSPaper.GS2,), tags=("polity",))
    response = _client(FakeDashboardQuery(cards=(card,))).get("/")
    assert "A distinctive card summary." in response.text
    assert "GS2" in response.text
    assert "polity" in response.text


def test_home_incomplete_card_without_note() -> None:
    card = _card(status=ProcessingStatus.DISCOVERED, has_note=False, summary=None, gs_papers=())
    response = _client(FakeDashboardQuery(cards=(card,))).get("/")
    assert response.status_code == 200
    assert "No Learning Note yet." in response.text


@pytest.mark.parametrize("status", list(ProcessingStatus))
def test_home_renders_every_status_label(status: ProcessingStatus) -> None:
    from app.presentation.view_helpers import status_presentation

    card = _card(status=status)
    response = _client(FakeDashboardQuery(cards=(card,))).get("/")
    assert status_presentation(status).label in response.text


def test_home_shows_excerpt_not_full_long_summary() -> None:
    long_summary = "word " * 200
    excerpt = "word " * 40  # arbitrary shorter excerpt built by the service normally
    card = _card(summary=excerpt.strip())
    response = _client(FakeDashboardQuery(cards=(card,))).get("/")
    assert long_summary not in response.text


# --- detail -------------------------------------------------------------------


def test_detail_renders_all_learning_note_sections() -> None:
    aid = uuid4()
    detail = _detail(aid, with_note=True)
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    assert response.status_code == 200
    body = response.text
    for fragment in [
        "Executive summary",
        "Executive summary body.",
        "Why it matters",
        "Revision note",
        "Revision note body.",
        "Important facts",
        "Static concepts",
        "Constitutional linkages",
        "Government schemes",
        "Reports and committees",
        "International dimensions",
        "Prelims questions",
        "Mains questions",
        "Keywords",
    ]:
        assert fragment in body


def test_detail_without_note_shows_status_not_empty_headings() -> None:
    aid = uuid4()
    detail = _detail(aid, status=ProcessingStatus.EXTRACTED, with_note=False)
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    assert response.status_code == 200
    assert "No Learning Note is available" in response.text
    assert "Executive summary" not in response.text
    assert "Prelims questions" not in response.text


def test_detail_omits_empty_optional_sections() -> None:
    aid = uuid4()
    note = LearningNote(
        article_id=aid,
        summary="s",
        why_it_matters="w",
        revision_note="r",
        model_name="m",
        prompt_version="v1",
    )
    detail = ArticleDetail(
        article_id=aid,
        title="T",
        source="indian_express",
        url="https://indianexpress.com/a",
        author=None,
        published_at=None,
        categories=(),
        processing_status=ProcessingStatus.ANALYZED,
        failure_reason=None,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        learning_note=note,
    )
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    body = response.text
    assert "Important facts" not in body
    assert "Prelims questions" not in body
    assert "Mains questions" not in body
    assert "Keywords" not in body
    assert "Publication date unavailable" in body


def test_detail_prelims_labels_correct_answer_and_explanation() -> None:
    aid = uuid4()
    detail = _detail(aid, with_note=True)
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    body = response.text
    assert "Which body?" in body
    # correct_option=2 -> label C, option "Charlie"
    assert "C. Charlie" in body
    assert "Charlie is correct." in body
    assert "Show answer and explanation" in body


def test_detail_mains_question_rendered() -> None:
    aid = uuid4()
    detail = _detail(aid, with_note=True)
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    assert "Discuss federalism." in response.text


def test_detail_original_source_link_is_safe() -> None:
    aid = uuid4()
    detail = _detail(aid, url="https://indianexpress.com/upsc/a?token=SECRETTOKEN")
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    body = response.text
    assert "Open the original article" in body
    assert 'rel="noopener noreferrer"' in body
    # The query token is not shown as visible link text.
    assert ">https://indianexpress.com/upsc/a?token=SECRETTOKEN<" not in body


def test_detail_failed_status_shows_safe_reason() -> None:
    aid = uuid4()
    detail = _detail(
        aid,
        status=ProcessingStatus.FAILED,
        failure_reason="extraction: network error",
        with_note=False,
    )
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    assert "extraction: network error" in response.text
    assert "Failed" in response.text


# --- 404 / 422 / 503 ----------------------------------------------------------


def test_missing_article_returns_html_404() -> None:
    response = _client(FakeDashboardQuery(details={})).get(f"/articles/{uuid4()}")
    assert response.status_code == 404
    assert "Article not found" in response.text


def test_malformed_uuid_returns_422() -> None:
    response = _client(FakeDashboardQuery()).get("/articles/not-a-uuid")
    assert response.status_code == 422


def test_repository_error_returns_safe_503() -> None:
    secret = "SECRET-DB-DETAIL-42"
    query = FakeDashboardQuery(list_error=RepositoryError(f"connection failed {secret}"))
    response = _client(query).get("/")
    assert response.status_code == 503
    assert "temporarily unavailable" in response.text
    assert secret not in response.text
    assert "RepositoryError" not in response.text


# --- privacy / autoescaping ---------------------------------------------------


def test_hostile_content_is_autoescaped_on_detail() -> None:
    aid = uuid4()
    hostile = '<script>alert("xss")</script>'
    note = LearningNote(
        article_id=aid,
        summary=hostile,
        why_it_matters=hostile,
        revision_note=hostile,
        important_facts=[hostile],
        keywords=[hostile],
        prelims_questions=[
            PrelimsQuestion(
                question=hostile,
                options=[hostile + "1", hostile + "2", hostile + "3", hostile + "4"],
                correct_option=0,
                explanation=hostile,
            )
        ],
        mains_questions=[MainsQuestion(question=hostile)],
        model_name="m",
        prompt_version="v1",
    )
    detail = ArticleDetail(
        article_id=aid,
        title=hostile,
        source="indian_express",
        url="https://indianexpress.com/a",
        author=hostile,
        published_at=None,
        categories=(hostile,),
        processing_status=ProcessingStatus.FAILED,
        failure_reason=hostile,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        learning_note=note,
    )
    response = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    body = response.text
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_hostile_content_is_autoescaped_on_home() -> None:
    hostile = '<img src=x onerror="alert(1)">'
    card = _card(title=hostile, tags=(hostile,))
    response = _client(FakeDashboardQuery(cards=(card,))).get("/")
    body = response.text
    assert "<img src=x onerror" not in body
    assert "&lt;img" in body


def test_raw_text_marker_absent_from_all_pages() -> None:
    aid = uuid4()
    # RAW_TEXT_MARKER is never part of any read model, so it can never render.
    detail = _detail(aid, with_note=True)
    home = _client(FakeDashboardQuery(cards=(_card(),))).get("/")
    detail_resp = _client(FakeDashboardQuery(details={aid: detail})).get(f"/articles/{aid}")
    not_found = _client(FakeDashboardQuery()).get(f"/articles/{uuid4()}")
    error = _client(FakeDashboardQuery(list_error=RepositoryError("x"))).get("/")
    for resp in (home, detail_resp, not_found, error):
        assert RAW_TEXT_MARKER not in resp.text


# --- static, cwd, health ------------------------------------------------------


def test_static_css_served_locally() -> None:
    response = _client(FakeDashboardQuery()).get("/static/dashboard.css")
    assert response.status_code == 200
    assert "--color-bg" in response.text


def test_templates_and_static_work_after_cwd_change(tmp_path: Path) -> None:
    original = Path.cwd()
    os.chdir(tmp_path)
    try:
        client = _client(FakeDashboardQuery(cards=(_card(title="CWD Test"),)))
        home = client.get("/")
        css = client.get("/static/dashboard.css")
        assert home.status_code == 200
        assert "CWD Test" in home.text
        assert css.status_code == 200
    finally:
        os.chdir(original)


def test_health_unchanged() -> None:
    response = _client(FakeDashboardQuery()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_no_template_uses_the_safe_filter() -> None:
    templates_dir = Path("app/presentation/templates")
    for path in templates_dir.glob("*.html"):
        assert "|safe" not in path.read_text(encoding="utf-8")
        assert "| safe" not in path.read_text(encoding="utf-8")


def test_default_create_app_needs_no_openai_config_and_opens_no_connection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The production path builds without OpenAI/LLM config and without a live DB.

    A missing/unmigrated database must not prevent app construction; the first
    dashboard read then produces the safe 503 path.
    """
    from app.infrastructure.config import get_settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'unmigrated.db'}")
    get_settings.cache_clear()
    try:
        app = create_app()  # constructs the real query service, no connection yet
        client = TestClient(app)
        # /health works without any dashboard data.
        assert client.get("/health").json() == {"status": "ok"}
        # First read against the unmigrated database yields the safe 503 page.
        response = client.get("/")
        assert response.status_code == 503
        assert "temporarily unavailable" in response.text
    finally:
        get_settings.cache_clear()

"""Pure mapping functions between domain models and ORM rows.

No I/O happens here - these functions only translate field values. SQLite has
no native timezone storage, so every datetime read back from a row is
reconstructed as UTC-aware here (never left naive) before it reaches a domain
model, whose own validators reject naive datetimes outright. List and dict
values are always copied rather than shared, so mutating a returned domain
object can never reach back into ORM/session state.
"""

from datetime import UTC, datetime

from app.domain.article import Article
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import LearningNote, MainsQuestion, PrelimsQuestion
from app.infrastructure.orm_models import ArticleRow, LearningNoteRow


def _reconstruct_utc(value: datetime) -> datetime:
    """Reconstruct a datetime read back from SQLite as UTC-aware.

    Only UTC-aware datetimes are ever written (domain validators guarantee
    this at construction/assignment time), so a naive value coming back from
    SQLite is never ambiguous - it is always UTC. An aware value is normalized
    to UTC defensively rather than trusted as-is.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def article_to_row(article: Article) -> ArticleRow:
    """Build a new `ArticleRow` from an `Article`, for insertion."""
    return ArticleRow(
        id=article.id,
        source=article.source,
        external_id=article.external_id,
        title=article.title,
        url=article.url,
        author=article.author,
        published_at=article.published_at,
        categories=list(article.categories),
        raw_text=article.raw_text,
        processing_status=article.processing_status,
        failure_reason=article.failure_reason,
        created_at=article.created_at,
        updated_at=article.updated_at,
    )


def update_row_from_article(row: ArticleRow, article: Article) -> None:
    """Update an existing `ArticleRow` in place from the given `Article`.

    Assigns each domain-backed column individually rather than replacing the
    row wholesale, so an update can never silently drop or overwrite a column
    the domain model does not represent.
    """
    row.source = article.source
    row.external_id = article.external_id
    row.title = article.title
    row.url = article.url
    row.author = article.author
    row.published_at = article.published_at
    row.categories = list(article.categories)
    row.raw_text = article.raw_text
    row.processing_status = article.processing_status
    row.failure_reason = article.failure_reason
    row.created_at = article.created_at
    row.updated_at = article.updated_at


def row_to_article(row: ArticleRow) -> Article:
    """Reconstruct an `Article` from an `ArticleRow`."""
    return Article(
        id=row.id,
        source=row.source,
        external_id=row.external_id,
        title=row.title,
        url=row.url,
        author=row.author,
        published_at=_reconstruct_utc(row.published_at) if row.published_at else None,
        categories=list(row.categories),
        raw_text=row.raw_text,
        processing_status=ProcessingStatus(row.processing_status),
        failure_reason=row.failure_reason,
        created_at=_reconstruct_utc(row.created_at),
        updated_at=_reconstruct_utc(row.updated_at),
    )


def learning_note_to_row(note: LearningNote) -> LearningNoteRow:
    """Build a new `LearningNoteRow` from a `LearningNote`, for insertion."""
    return LearningNoteRow(
        id=note.id,
        article_id=note.article_id,
        summary=note.summary,
        why_it_matters=note.why_it_matters,
        gs_papers=[paper.value for paper in note.gs_papers],
        subjects=list(note.subjects),
        syllabus_topics=list(note.syllabus_topics),
        static_concepts=list(note.static_concepts),
        constitutional_linkages=list(note.constitutional_linkages),
        government_schemes=list(note.government_schemes),
        reports_and_committees=list(note.reports_and_committees),
        international_dimensions=list(note.international_dimensions),
        important_facts=list(note.important_facts),
        prelims_questions=[q.model_dump(mode="json") for q in note.prelims_questions],
        mains_questions=[q.model_dump(mode="json") for q in note.mains_questions],
        revision_note=note.revision_note,
        keywords=list(note.keywords),
        model_name=note.model_name,
        prompt_version=note.prompt_version,
        created_at=note.created_at,
    )


def row_to_learning_note(row: LearningNoteRow) -> LearningNote:
    """Reconstruct a `LearningNote` from a `LearningNoteRow`."""
    return LearningNote(
        id=row.id,
        article_id=row.article_id,
        summary=row.summary,
        why_it_matters=row.why_it_matters,
        gs_papers=[GSPaper(value) for value in row.gs_papers],
        subjects=list(row.subjects),
        syllabus_topics=list(row.syllabus_topics),
        static_concepts=list(row.static_concepts),
        constitutional_linkages=list(row.constitutional_linkages),
        government_schemes=list(row.government_schemes),
        reports_and_committees=list(row.reports_and_committees),
        international_dimensions=list(row.international_dimensions),
        important_facts=list(row.important_facts),
        prelims_questions=[PrelimsQuestion(**q) for q in row.prelims_questions],
        mains_questions=[MainsQuestion(**q) for q in row.mains_questions],
        revision_note=row.revision_note,
        keywords=list(row.keywords),
        model_name=row.model_name,
        prompt_version=row.prompt_version,
        created_at=_reconstruct_utc(row.created_at),
    )

"""End-to-end feed-processing workflow: discovery through Learning Note persistence.

`ProcessNewsFeedService` connects the existing application ports -
`ArticleSource`, `ArticleExtractor`, `ArticleRepository`,
`LearningNoteRepository`, and `LearningNoteGenerator` - into one synchronous,
sequential, idempotent pipeline. It depends only on application ports and
domain types, never on a concrete infrastructure implementation.

Key workflow properties:

* Database unique constraints remain the final duplicate boundary; identity
  lookups here are a convenience, and a `DuplicateArticleError` insert race is
  recovered by re-reading, never by a second blind insert.
* The Learning Note is always persisted before the Article is finalized as
  `ANALYZED`, so the system can never durably record `ANALYZED` before the
  note exists. The reverse gap (note saved, finalization failed) is healed by
  note-existence reconciliation on the next run - the deliberate
  no-Unit-of-Work recovery path.
* Resumption decisions are driven by ground truth (Learning Note existence
  and accepted `raw_text` presence), never by parsing `failure_reason` text.
* One candidate's failure never stops the batch: each candidate is processed
  inside its own isolation boundary and reported through `FailureDetail`.
* A total source-discovery failure is batch-level: `process()` propagates the
  existing `ArticleSourceError` and produces no `ProcessingSummary` at all.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from app.application.extraction import ArticleExtractor
from app.application.learning_notes import (
    LearningNoteGenerator,
    LearningNoteProviderError,
    LearningNoteValidationError,
)
from app.application.repositories import (
    ArticleRepository,
    DuplicateArticleError,
    DuplicateLearningNoteError,
    LearningNoteRepository,
    RepositoryError,
)
from app.application.sources import ArticleSource
from app.domain.article import Article, ArticleCandidate
from app.domain.enums import ProcessingStatus
from app.domain.extraction import ExtractionStatus
from app.domain.learning_note import LearningNote
from app.domain.validation import utc_now

logger = logging.getLogger(__name__)

# Fixed, safe persisted failure reasons. These are operator-facing labels only:
# no control flow anywhere parses them back to choose a recovery stage.
REASON_EXTRACTION_INSUFFICIENT = "extraction: insufficient content"
REASON_EXTRACTION_NETWORK = "extraction: network error"
REASON_EXTRACTION_UNSUPPORTED = "extraction: unsupported page"
REASON_EXTRACTION_UNEXPECTED = "extraction: unexpected error"
REASON_EXTRACTION_URL_MISMATCH = "extraction: result URL mismatch"
REASON_ANALYSIS_PROVIDER = "analysis: provider failure"
REASON_ANALYSIS_VALIDATION = "analysis: validation exhausted"
REASON_NOTE_ARTICLE_MISMATCH = "analysis: learning note article mismatch"
REASON_NOTE_SAVE_FAILED = "persistence: learning note save failed"
REASON_MISSING_NOTE = "persistence: analyzed article missing learning note"
REASON_ARTICLE_UPDATE_FAILED = "persistence: article update failed"
REASON_ARTICLE_INSERT_FAILED = "persistence: article insert failed"
REASON_FINALIZATION_FAILED = "persistence: article finalization failed"
REASON_IDENTITY_CONFLICT = "identity: conflicting article records"
REASON_IDENTITY_LOOKUP_FAILED = "identity: article lookup failed"
REASON_PIPELINE_UNEXPECTED = "pipeline: unexpected error"

_EXTRACTION_FAILURES: Final[dict[ExtractionStatus, tuple[str, str]]] = {
    ExtractionStatus.INSUFFICIENT_CONTENT: (REASON_EXTRACTION_INSUFFICIENT, "insufficient_content"),
    ExtractionStatus.NETWORK_ERROR: (REASON_EXTRACTION_NETWORK, "network_error"),
    ExtractionStatus.UNSUPPORTED_PAGE: (REASON_EXTRACTION_UNSUPPORTED, "unsupported_page"),
    ExtractionStatus.UNEXPECTED_ERROR: (REASON_EXTRACTION_UNEXPECTED, "unexpected_error"),
}


class ArticleNotFoundError(LookupError):
    """Raised by `retry_article()` when no Article with the given id exists."""


class PipelineStage(StrEnum):
    """Where in the pipeline an Article-level failure occurred.

    A diagnostic categorization of this service's own control flow - never
    persisted and never part of a domain model's state. Total source-discovery
    failure has no stage here because it aborts the batch before any
    per-Article processing begins (it propagates as `ArticleSourceError`).
    """

    IDENTITY_RESOLUTION = "identity_resolution"
    PERSISTENCE = "persistence"
    EXTRACTION = "extraction"
    ANALYSIS = "analysis"
    FINALIZATION = "finalization"


def _safe_url(url: str) -> str:
    """Reduce a URL to scheme://netloc/path, dropping query and fragment."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


@dataclass(frozen=True, slots=True)
class FailureDetail:
    """A safe, structured description of one Article-level pipeline failure.

    Contains only identifiers and fixed categorization - never article text,
    prompts, provider output, SQL detail, or raw exception representations.
    `article_id` is None when no single persisted Article can be named (an
    identity conflict or a failed insert).
    """

    article_id: UUID | None
    source: str
    external_id: str | None
    url: str | None
    stage: PipelineStage
    reason_category: str
    message: str


@dataclass(frozen=True, slots=True)
class ArticleProcessingResult:
    """The outcome of processing one candidate or one targeted retry.

    Flags are independent stage outcomes, not a partition: a brand-new
    article that succeeds end to end has `created`, `extracted`, and
    `analyzed` all True. `created=True` together with a `failure` is valid
    (the insert succeeded, a later stage failed). An identity conflict has
    `article_id=None` and only a `failure`.
    """

    article_id: UUID | None
    created: bool = False
    skipped: bool = False
    extracted: bool = False
    analyzed: bool = False
    reconciled: bool = False
    failure: FailureDetail | None = None

    def __post_init__(self) -> None:
        if self.skipped and (
            self.created
            or self.extracted
            or self.analyzed
            or self.reconciled
            or self.failure is not None
        ):
            raise ValueError("a skipped result must carry no other outcome")
        if self.analyzed and self.reconciled:
            raise ValueError("a result cannot be both analyzed and reconciled")
        if self.analyzed and self.failure is not None:
            raise ValueError("an analyzed result cannot also carry a failure")
        if self.reconciled and self.failure is not None:
            raise ValueError("a reconciled result cannot also carry a failure")


@dataclass(frozen=True, slots=True)
class ProcessingSummary:
    """The outcome of one `process()` run.

    Counters are independent operational metrics and intentionally overlap:
    one candidate may increment several. There is no partition invariant -
    `new_articles + duplicates_skipped + failed` does NOT equal
    `total_discovered` when existing incomplete Articles resume successfully
    or stale statuses are reconciled. The only mandatory arithmetic invariant
    is `failed == len(failure_details)`.

    Semantics:

    * `total_discovered` - candidates returned by the source after its own
      filtering and within-response deduplication.
    * `new_articles` - Article rows successfully inserted this run.
    * `duplicates_skipped` - existing Articles for which no extraction,
      analysis, reconciliation, or new failure was performed (fully-completed
      matches, and FAILED matches not retried this run).
    * `successfully_extracted` - accepted extraction text successfully
      persisted this run.
    * `successfully_analyzed` - a new Learning Note was durably persisted AND
      the Article was durably finalized as ANALYZED this run.
    * `reconciled` - an existing Learning Note was reused and the Article
      status was corrected to ANALYZED without generating a new note.
    * `failed` - Article-level failures produced this run.
    * `failure_details` - deterministic, feed-order details for `failed`.
    """

    total_discovered: int
    new_articles: int
    duplicates_skipped: int
    successfully_extracted: int
    successfully_analyzed: int
    reconciled: int
    failed: int
    failure_details: tuple[FailureDetail, ...]

    def __post_init__(self) -> None:
        counts = {
            "total_discovered": self.total_discovered,
            "new_articles": self.new_articles,
            "duplicates_skipped": self.duplicates_skipped,
            "successfully_extracted": self.successfully_extracted,
            "successfully_analyzed": self.successfully_analyzed,
            "reconciled": self.reconciled,
            "failed": self.failed,
        }
        for name, value in counts.items():
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.failed != len(self.failure_details):
            raise ValueError("failed must equal len(failure_details)")


class _Unchanged:
    """Private sentinel type marking `raw_text` as deliberately untouched."""

    __slots__ = ()


_UNCHANGED: Final = _Unchanged()


def new_article_from_candidate(candidate: ArticleCandidate) -> Article:
    """Build a new `Article` in its initial pipeline state from a candidate.

    Transfers the source-provided metadata; the Article's own domain defaults
    supply the locally controlled fields (UUID, UTC timestamps). `raw_text`,
    `processing_status=DISCOVERED`, and `failure_reason=None` are the explicit
    initial pipeline state. Mutable category data is copied, never shared.
    """
    return Article(
        source=candidate.source,
        external_id=candidate.external_id,
        title=candidate.title,
        url=candidate.url,
        author=candidate.author,
        published_at=candidate.published_at,
        categories=list(candidate.categories),
        raw_text=None,
        processing_status=ProcessingStatus.DISCOVERED,
        failure_reason=None,
    )


def reconstruct_article(
    article: Article,
    *,
    processing_status: ProcessingStatus,
    failure_reason: str | None,
    raw_text: str | None | _Unchanged = _UNCHANGED,
    updated_at: datetime | None = None,
) -> Article:
    """Rebuild an Article in a new workflow state through full domain validation.

    Constructs a brand-new `Article(**data)` - never `model_copy(update=...)`,
    which patches state without re-running validators and would silently
    bypass the FAILED/failure_reason invariant. The original `article` is
    never mutated: a rejected reconstruction raises and leaves it unchanged.

    `processing_status` and `failure_reason` are both required so every call
    site decides the coupled pair explicitly - a non-FAILED status must pass
    `failure_reason=None`, and FAILED must pass a meaningful safe reason, or
    domain validation rejects the reconstruction.

    `raw_text` defaults to a private sentinel meaning "keep the current
    value"; pass an explicit `str` or `None` to change it. `updated_at`
    defaults to now (UTC) and is clamped so it never moves backwards relative
    to the previous `updated_at`.
    """
    data = article.model_dump()
    data["processing_status"] = processing_status
    data["failure_reason"] = failure_reason
    if not isinstance(raw_text, _Unchanged):
        data["raw_text"] = raw_text
    proposed_updated_at = updated_at if updated_at is not None else utc_now()
    data["updated_at"] = max(proposed_updated_at, article.updated_at)
    return Article(**data)


def _with_refreshed_url(article: Article, url: str) -> Article:
    """Rebuild an Article with a refreshed canonical URL, fully validated.

    Preserves the id, creation time, processing state, accepted raw text, and
    failure reason; only the URL and `updated_at` change.
    """
    data = article.model_dump()
    data["url"] = url
    data["updated_at"] = max(utc_now(), article.updated_at)
    return Article(**data)


class ProcessNewsFeedService:
    """Synchronous, idempotent orchestration of the complete feed pipeline.

    All per-run state lives in local variables and immutable result objects -
    the service instance holds only its injected ports, so concurrent or
    repeated `process()` calls can never observe each other's counters.
    """

    def __init__(
        self,
        *,
        article_source: ArticleSource,
        article_extractor: ArticleExtractor,
        article_repository: ArticleRepository,
        learning_note_repository: LearningNoteRepository,
        learning_note_generator: LearningNoteGenerator,
    ) -> None:
        self._source = article_source
        self._extractor = article_extractor
        self._articles = article_repository
        self._notes = learning_note_repository
        self._generator = learning_note_generator

    def process(self, *, retry_failed: bool = False) -> ProcessingSummary:
        """Discover candidates from the source and process each one.

        `retry_failed=True` additionally retries FAILED Articles that are
        rediscovered in the current feed window; it never reaches a FAILED
        Article that has dropped out of the feed - use `retry_article()` for
        those.

        Raises:
            ArticleSourceError: if discovery fails entirely; no summary is
                produced because no candidate list was ever obtained.
        """
        logger.info("processing batch started retry_failed=%s", retry_failed)
        candidates = self._source.discover_articles()
        logger.info("discovery completed candidates=%d", len(candidates))

        results = [
            self._process_candidate(candidate, retry_failed=retry_failed)
            for candidate in candidates
        ]

        summary = ProcessingSummary(
            total_discovered=len(candidates),
            new_articles=sum(1 for r in results if r.created),
            duplicates_skipped=sum(1 for r in results if r.skipped),
            successfully_extracted=sum(1 for r in results if r.extracted),
            successfully_analyzed=sum(1 for r in results if r.analyzed),
            reconciled=sum(1 for r in results if r.reconciled),
            failed=sum(1 for r in results if r.failure is not None),
            failure_details=tuple(r.failure for r in results if r.failure is not None),
        )
        logger.info(
            "processing batch completed total=%d new=%d skipped=%d extracted=%d "
            "analyzed=%d reconciled=%d failed=%d",
            summary.total_discovered,
            summary.new_articles,
            summary.duplicates_skipped,
            summary.successfully_extracted,
            summary.successfully_analyzed,
            summary.reconciled,
            summary.failed,
        )
        return summary

    def retry_article(self, article_id: UUID) -> ArticleProcessingResult:
        """Explicitly retry one persisted Article, regardless of feed presence.

        Never calls the article source: the persisted Article state (including
        its stored URL) is the sole input. Resumption follows the same ground
        truth as feed processing - an existing Learning Note reconciles
        immediately, accepted `raw_text` resumes at analysis, and its absence
        resumes at extraction. `failure_reason` text is never parsed.

        Raises:
            ArticleNotFoundError: if no Article with `article_id` exists.
            RepositoryError: if the initial Article lookup itself fails.
        """
        pair = self._articles.get_with_learning_note(article_id)
        if pair is None:
            raise ArticleNotFoundError(f"no article with id {article_id} exists")
        logger.info("targeted retry started article_id=%s", article_id)
        return self._guarded_process(
            pair.article, pair.learning_note, allow_failed_retry=True, created=False
        )

    # --- per-candidate orchestration -----------------------------------------

    def _process_candidate(
        self, candidate: ArticleCandidate, *, retry_failed: bool
    ) -> ArticleProcessingResult:
        """Process one candidate inside its own defensive isolation boundary."""
        try:
            return self._resolve_and_process(candidate, retry_failed=retry_failed)
        except Exception as exc:
            # Last-resort isolation for unexpected defects during identity
            # resolution (post-resolution stages have their own boundary in
            # `_guarded_process`, which returns rather than raises, so this
            # can never produce a second FailureDetail for the same candidate).
            logger.error(
                "unexpected candidate failure url=%s error_type=%s",
                _safe_url(candidate.url),
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=None,
                failure=self._candidate_failure(
                    candidate,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="unexpected_error",
                    message=REASON_PIPELINE_UNEXPECTED,
                ),
            )

    def _resolve_and_process(
        self, candidate: ArticleCandidate, *, retry_failed: bool
    ) -> ArticleProcessingResult:
        """Resolve candidate identity, then hand off to the shared pipeline core."""
        try:
            by_url = self._articles.get_by_url(candidate.url)
            by_external = (
                self._articles.get_by_source_external_id(candidate.source, candidate.external_id)
                if candidate.external_id is not None
                else None
            )
        except RepositoryError as exc:
            logger.error(
                "identity lookup failed url=%s error_type=%s",
                _safe_url(candidate.url),
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=None,
                failure=self._candidate_failure(
                    candidate,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="database_error",
                    message=REASON_IDENTITY_LOOKUP_FAILED,
                ),
            )

        if by_url is not None and by_external is not None and by_url.id != by_external.id:
            logger.error(
                "identity conflict url=%s url_article_id=%s external_article_id=%s",
                _safe_url(candidate.url),
                by_url.id,
                by_external.id,
            )
            return ArticleProcessingResult(
                article_id=None,
                failure=self._candidate_failure(
                    candidate,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="identity_conflict",
                    message=REASON_IDENTITY_CONFLICT,
                ),
            )

        existing = by_url if by_url is not None else by_external

        if existing is None:
            return self._insert_and_process(candidate, retry_failed=retry_failed)

        return self._prepare_existing_candidate(
            existing,
            candidate,
            matched_by_current_url=by_url is not None,
            retry_failed=retry_failed,
        )

    def _prepare_existing_candidate(
        self,
        existing: Article,
        candidate: ArticleCandidate,
        *,
        matched_by_current_url: bool,
        retry_failed: bool,
    ) -> ArticleProcessingResult:
        """Refresh a changed candidate URL if needed, then run the pipeline core.

        Shared by the ordinary identity path and insert-race recovery so both
        apply the changed-URL rule identically. When the current candidate URL
        did not match the resolved Article (only `(source, external_id)`
        matched) and the URL differs, the candidate URL - already confirmed
        unowned by the caller's URL lookup - is refreshed and persisted before
        any extraction, so a known-stale URL is never used. An update-time
        `DuplicateArticleError` becomes an identity conflict.
        """
        if not matched_by_current_url and candidate.url != existing.url:
            refreshed_or_failure = self._refresh_url(existing, candidate)
            if isinstance(refreshed_or_failure, FailureDetail):
                return ArticleProcessingResult(
                    article_id=existing.id, failure=refreshed_or_failure
                )
            existing = refreshed_or_failure

        return self._load_and_process(existing, retry_failed=retry_failed)

    def _insert_and_process(
        self, candidate: ArticleCandidate, *, retry_failed: bool
    ) -> ArticleProcessingResult:
        article = new_article_from_candidate(candidate)
        try:
            self._articles.add(article)
        except DuplicateArticleError:
            logger.info(
                "insert race detected url=%s; re-reading existing article",
                _safe_url(candidate.url),
            )
            return self._recover_from_insert_race(candidate, retry_failed=retry_failed)
        except RepositoryError as exc:
            logger.error(
                "article insert failed url=%s error_type=%s",
                _safe_url(candidate.url),
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=None,
                failure=self._candidate_failure(
                    candidate,
                    stage=PipelineStage.PERSISTENCE,
                    category="article_insert_failed",
                    message=REASON_ARTICLE_INSERT_FAILED,
                ),
            )
        logger.info("article created article_id=%s source=%s", article.id, article.source)
        return self._guarded_process(
            article, None, allow_failed_retry=retry_failed, created=True
        )

    def _recover_from_insert_race(
        self, candidate: ArticleCandidate, *, retry_failed: bool
    ) -> ArticleProcessingResult:
        """After a `DuplicateArticleError`, re-read once and continue - never re-insert."""
        try:
            by_url = self._articles.get_by_url(candidate.url)
            by_external = (
                self._articles.get_by_source_external_id(candidate.source, candidate.external_id)
                if candidate.external_id is not None
                else None
            )
        except RepositoryError as exc:
            logger.error(
                "insert-race re-read failed url=%s error_type=%s",
                _safe_url(candidate.url),
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=None,
                failure=self._candidate_failure(
                    candidate,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="database_error",
                    message=REASON_IDENTITY_LOOKUP_FAILED,
                ),
            )

        conflicting = (
            by_url is not None and by_external is not None and by_url.id != by_external.id
        )
        existing = by_url if by_url is not None else by_external
        if conflicting or existing is None:
            logger.error("insert race unresolvable url=%s", _safe_url(candidate.url))
            return ArticleProcessingResult(
                article_id=None,
                failure=self._candidate_failure(
                    candidate,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="identity_conflict",
                    message=REASON_IDENTITY_CONFLICT,
                ),
            )
        # Same changed-URL rule as the ordinary path: if the duplicate insert
        # arose from a (source, external_id) collision and the URL changed,
        # refresh it before processing rather than extracting from the stale URL.
        return self._prepare_existing_candidate(
            existing,
            candidate,
            matched_by_current_url=by_url is not None,
            retry_failed=retry_failed,
        )

    def _refresh_url(
        self, existing: Article, candidate: ArticleCandidate
    ) -> Article | FailureDetail:
        """Durably persist the candidate's URL onto the existing Article."""
        refreshed = _with_refreshed_url(existing, candidate.url)
        try:
            self._articles.update(refreshed)
        except DuplicateArticleError as exc:
            # Another Article claimed this URL between the lookup and this
            # update - a race-time identity conflict, not a merge opportunity.
            logger.error(
                "url refresh conflict article_id=%s error_type=%s",
                existing.id,
                type(exc).__name__,
            )
            return self._article_failure(
                existing,
                stage=PipelineStage.IDENTITY_RESOLUTION,
                category="identity_conflict",
                message=REASON_IDENTITY_CONFLICT,
            )
        except RepositoryError as exc:
            logger.error(
                "url refresh failed article_id=%s error_type=%s",
                existing.id,
                type(exc).__name__,
            )
            return self._article_failure(
                existing,
                stage=PipelineStage.PERSISTENCE,
                category="article_update_failed",
                message=REASON_ARTICLE_UPDATE_FAILED,
            )
        logger.info("article url refreshed article_id=%s", existing.id)
        return refreshed

    def _load_and_process(
        self, existing: Article, *, retry_failed: bool
    ) -> ArticleProcessingResult:
        """Load the Article together with its Learning Note, then run the core."""
        try:
            pair = self._articles.get_with_learning_note(existing.id)
        except RepositoryError as exc:
            logger.error(
                "article load failed article_id=%s error_type=%s",
                existing.id,
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=existing.id,
                failure=self._article_failure(
                    existing,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="database_error",
                    message=REASON_IDENTITY_LOOKUP_FAILED,
                ),
            )
        if pair is None:
            logger.error("article disappeared during processing article_id=%s", existing.id)
            return ArticleProcessingResult(
                article_id=existing.id,
                failure=self._article_failure(
                    existing,
                    stage=PipelineStage.IDENTITY_RESOLUTION,
                    category="database_error",
                    message=REASON_IDENTITY_LOOKUP_FAILED,
                ),
            )
        return self._guarded_process(
            pair.article, pair.learning_note, allow_failed_retry=retry_failed, created=False
        )

    # --- shared pipeline core (feed candidates and targeted retries) ----------

    def _guarded_process(
        self,
        article: Article,
        note: LearningNote | None,
        *,
        allow_failed_retry: bool,
        created: bool,
    ) -> ArticleProcessingResult:
        """Run the pipeline core inside the per-Article defensive boundary."""
        try:
            return self._process_resolved(
                article, note, allow_failed_retry=allow_failed_retry, created=created
            )
        except Exception as exc:
            logger.error(
                "unexpected pipeline failure article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )
            self._best_effort_mark_failed(article)
            return ArticleProcessingResult(
                article_id=article.id,
                created=created,
                failure=self._article_failure(
                    article,
                    stage=PipelineStage.FINALIZATION,
                    category="unexpected_error",
                    message=REASON_PIPELINE_UNEXPECTED,
                ),
            )

    def _best_effort_mark_failed(self, article: Article) -> None:
        """Attempt to persist a FAILED state, but never over a durable note.

        If a Learning Note already exists (or its existence cannot be
        confirmed), the last durable checkpoint is left untouched so that
        note-existence reconciliation can heal the Article on the next run.
        """
        try:
            if self._notes.get_by_article_id(article.id) is not None:
                return
            failed = reconstruct_article(
                article,
                processing_status=ProcessingStatus.FAILED,
                failure_reason=REASON_PIPELINE_UNEXPECTED,
            )
            self._articles.update(failed)
        except Exception as exc:
            logger.error(
                "best-effort failed-state update failed article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )

    def _process_resolved(
        self,
        article: Article,
        note: LearningNote | None,
        *,
        allow_failed_retry: bool,
        created: bool,
    ) -> ArticleProcessingResult:
        """Decide and execute what one Article needs, from its ground truth."""
        if note is not None:
            if article.processing_status is ProcessingStatus.ANALYZED:
                logger.info("duplicate skipped article_id=%s", article.id)
                return ArticleProcessingResult(article_id=article.id, skipped=True)
            return self._reconcile(article, created=created)

        if article.processing_status is ProcessingStatus.ANALYZED:
            return self._mark_invariant_violation(article, created=created)

        if article.processing_status is ProcessingStatus.FAILED and not allow_failed_retry:
            logger.info("failed article skipped article_id=%s", article.id)
            return ArticleProcessingResult(article_id=article.id, skipped=True)

        has_text = article.raw_text is not None and bool(article.raw_text.strip())

        if article.processing_status is ProcessingStatus.FAILED:
            resumed_status = (
                ProcessingStatus.EXTRACTED if has_text else ProcessingStatus.DISCOVERED
            )
            resumed = reconstruct_article(
                article, processing_status=resumed_status, failure_reason=None
            )
            try:
                self._articles.update(resumed)
            except RepositoryError as exc:
                logger.error(
                    "retry state reset failed article_id=%s error_type=%s",
                    article.id,
                    type(exc).__name__,
                )
                return ArticleProcessingResult(
                    article_id=article.id,
                    created=created,
                    failure=self._article_failure(
                        article,
                        stage=PipelineStage.PERSISTENCE,
                        category="article_update_failed",
                        message=REASON_ARTICLE_UPDATE_FAILED,
                    ),
                )
            article = resumed
            logger.info(
                "retry initiated article_id=%s resume_stage=%s",
                article.id,
                "analysis" if has_text else "extraction",
            )

        extracted = False
        if not has_text:
            extraction_outcome = self._extract_and_persist(article)
            if isinstance(extraction_outcome, FailureDetail):
                return ArticleProcessingResult(
                    article_id=article.id, created=created, failure=extraction_outcome
                )
            article = extraction_outcome
            extracted = True

        return self._analyze_and_persist(article, created=created, extracted=extracted)

    def _reconcile(
        self, article: Article, *, created: bool, extracted: bool = False
    ) -> ArticleProcessingResult:
        """Correct a stale status to ANALYZED using the already-durable note."""
        reconciled = reconstruct_article(
            article, processing_status=ProcessingStatus.ANALYZED, failure_reason=None
        )
        try:
            self._articles.update(reconciled)
        except RepositoryError as exc:
            # The note is durable: never overwrite this checkpoint with FAILED.
            logger.error(
                "reconciliation update failed article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=article.id,
                created=created,
                extracted=extracted,
                failure=self._article_failure(
                    article,
                    stage=PipelineStage.FINALIZATION,
                    category="finalization_failed",
                    message=REASON_FINALIZATION_FAILED,
                ),
            )
        logger.info("stale status reconciled article_id=%s", article.id)
        return ArticleProcessingResult(
            article_id=article.id, created=created, extracted=extracted, reconciled=True
        )

    def _mark_invariant_violation(
        self, article: Article, *, created: bool
    ) -> ArticleProcessingResult:
        """An ANALYZED Article has no Learning Note: report, never auto-regenerate.

        This state should be impossible under the note-first write ordering, so
        it is surfaced as a failure rather than silently healed - automatic
        regeneration could mask a real correctness bug. A later explicit
        `retry_article()` or `retry_failed=True` run resumes it deliberately.
        """
        logger.error("analyzed article missing learning note article_id=%s", article.id)
        failed = reconstruct_article(
            article,
            processing_status=ProcessingStatus.FAILED,
            failure_reason=REASON_MISSING_NOTE,
        )
        try:
            self._articles.update(failed)
        except RepositoryError as exc:
            logger.error(
                "invariant-violation state update failed article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )
        return ArticleProcessingResult(
            article_id=article.id,
            created=created,
            failure=self._article_failure(
                article,
                stage=PipelineStage.FINALIZATION,
                category="invariant_violation",
                message=REASON_MISSING_NOTE,
            ),
        )

    def _extract_and_persist(self, article: Article) -> Article | FailureDetail:
        """Extract content for an Article and persist the outcome."""
        logger.info("extraction started article_id=%s", article.id)
        result = self._extractor.extract(article.url)

        if result.url != article.url:
            # Integrity guard: the extractor returned a result for a different
            # URL than requested. Treat it as an extraction failure - never
            # persist its text or analyze it - without logging either raw URL.
            logger.error(
                "extraction result url mismatch article_id=%s", article.id
            )
            failed = reconstruct_article(
                article,
                processing_status=ProcessingStatus.FAILED,
                failure_reason=REASON_EXTRACTION_URL_MISMATCH,
            )
            try:
                self._articles.update(failed)
            except RepositoryError as exc:
                logger.error(
                    "url-mismatch failure state update failed article_id=%s error_type=%s",
                    article.id,
                    type(exc).__name__,
                )
            return self._article_failure(
                article,
                stage=PipelineStage.EXTRACTION,
                category="result_url_mismatch",
                message=REASON_EXTRACTION_URL_MISMATCH,
            )

        if result.status is ExtractionStatus.SUCCESS:
            updated = reconstruct_article(
                article,
                processing_status=ProcessingStatus.EXTRACTED,
                failure_reason=None,
                raw_text=result.text,
            )
            try:
                self._articles.update(updated)
            except RepositoryError as exc:
                logger.error(
                    "extracted text persistence failed article_id=%s error_type=%s",
                    article.id,
                    type(exc).__name__,
                )
                return self._article_failure(
                    article,
                    stage=PipelineStage.PERSISTENCE,
                    category="article_update_failed",
                    message=REASON_ARTICLE_UPDATE_FAILED,
                )
            logger.info("extraction succeeded article_id=%s", article.id)
            return updated

        reason, category = _EXTRACTION_FAILURES[result.status]
        # Unusable partial extraction text is never persisted into raw_text:
        # raw_text stays strictly "accepted, analysis-ready text or nothing",
        # which the resumption logic depends on.
        failed = reconstruct_article(
            article, processing_status=ProcessingStatus.FAILED, failure_reason=reason
        )
        try:
            self._articles.update(failed)
        except RepositoryError as exc:
            logger.error(
                "extraction failure state update failed article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )
        logger.warning("extraction failed article_id=%s category=%s", article.id, category)
        return self._article_failure(
            article, stage=PipelineStage.EXTRACTION, category=category, message=reason
        )

    def _analyze_and_persist(
        self, article: Article, *, created: bool, extracted: bool
    ) -> ArticleProcessingResult:
        """Generate and durably persist a Learning Note, note before finalization."""
        pending = reconstruct_article(
            article,
            processing_status=ProcessingStatus.ANALYSIS_PENDING,
            failure_reason=None,
        )
        try:
            self._articles.update(pending)
        except RepositoryError as exc:
            logger.error(
                "analysis-pending checkpoint failed article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=article.id,
                created=created,
                extracted=extracted,
                failure=self._article_failure(
                    article,
                    stage=PipelineStage.PERSISTENCE,
                    category="article_update_failed",
                    message=REASON_ARTICLE_UPDATE_FAILED,
                ),
            )

        logger.info("analysis started article_id=%s", pending.id)
        try:
            note = self._generator.generate(pending)
        except LearningNoteProviderError:
            return self._fail_analysis(
                pending,
                reason=REASON_ANALYSIS_PROVIDER,
                category="provider_failure",
                created=created,
                extracted=extracted,
            )
        except LearningNoteValidationError:
            return self._fail_analysis(
                pending,
                reason=REASON_ANALYSIS_VALIDATION,
                category="validation_exhausted",
                created=created,
                extracted=extracted,
            )

        if note.article_id != pending.id:
            # Integrity guard: the generated note claims a different Article.
            # Never persist it against any Article; fail the current one
            # (retaining its accepted raw_text) without exposing the wrong id.
            logger.error(
                "learning note article mismatch article_id=%s", pending.id
            )
            return self._fail_analysis(
                pending,
                reason=REASON_NOTE_ARTICLE_MISMATCH,
                category="result_identity_mismatch",
                created=created,
                extracted=extracted,
            )

        try:
            self._notes.add(note)
        except DuplicateLearningNoteError:
            # Durable prior progress from an interrupted earlier run: reuse the
            # existing note and finalize, never replace it.
            logger.info("existing learning note found during save article_id=%s", pending.id)
            return self._reconcile(pending, created=created, extracted=extracted)
        except RepositoryError as exc:
            logger.error(
                "learning note save failed article_id=%s error_type=%s",
                pending.id,
                type(exc).__name__,
            )
            failed = reconstruct_article(
                pending,
                processing_status=ProcessingStatus.FAILED,
                failure_reason=REASON_NOTE_SAVE_FAILED,
            )
            try:
                self._articles.update(failed)
            except RepositoryError as update_exc:
                logger.error(
                    "note-save failure state update failed article_id=%s error_type=%s",
                    pending.id,
                    type(update_exc).__name__,
                )
            return ArticleProcessingResult(
                article_id=pending.id,
                created=created,
                extracted=extracted,
                failure=self._article_failure(
                    pending,
                    stage=PipelineStage.PERSISTENCE,
                    category="note_save_failed",
                    message=REASON_NOTE_SAVE_FAILED,
                ),
            )

        logger.info("learning note saved article_id=%s note_id=%s", pending.id, note.id)

        final = reconstruct_article(
            pending, processing_status=ProcessingStatus.ANALYZED, failure_reason=None
        )
        try:
            self._articles.update(final)
        except RepositoryError as exc:
            # The note is durable. The Article deliberately stays at its last
            # durable checkpoint (ANALYSIS_PENDING) rather than being marked
            # FAILED: the next run's note-existence reconciliation finalizes
            # it without regenerating - the intended no-Unit-of-Work recovery.
            logger.error(
                "article finalization failed after durable note article_id=%s error_type=%s",
                pending.id,
                type(exc).__name__,
            )
            return ArticleProcessingResult(
                article_id=pending.id,
                created=created,
                extracted=extracted,
                failure=self._article_failure(
                    pending,
                    stage=PipelineStage.FINALIZATION,
                    category="finalization_failed",
                    message=REASON_FINALIZATION_FAILED,
                ),
            )

        logger.info("analysis succeeded article_id=%s", final.id)
        return ArticleProcessingResult(
            article_id=final.id, created=created, extracted=extracted, analyzed=True
        )

    def _fail_analysis(
        self,
        article: Article,
        *,
        reason: str,
        category: str,
        created: bool,
        extracted: bool,
    ) -> ArticleProcessingResult:
        """Persist a FAILED analysis outcome, retaining the accepted raw text."""
        failed = reconstruct_article(
            article, processing_status=ProcessingStatus.FAILED, failure_reason=reason
        )
        try:
            self._articles.update(failed)
        except RepositoryError as exc:
            logger.error(
                "analysis failure state update failed article_id=%s error_type=%s",
                article.id,
                type(exc).__name__,
            )
        logger.warning("analysis failed article_id=%s category=%s", article.id, category)
        return ArticleProcessingResult(
            article_id=article.id,
            created=created,
            extracted=extracted,
            failure=self._article_failure(
                article, stage=PipelineStage.ANALYSIS, category=category, message=reason
            ),
        )

    # --- failure-detail construction ------------------------------------------

    @staticmethod
    def _candidate_failure(
        candidate: ArticleCandidate, *, stage: PipelineStage, category: str, message: str
    ) -> FailureDetail:
        return FailureDetail(
            article_id=None,
            source=candidate.source,
            external_id=candidate.external_id,
            url=_safe_url(candidate.url),
            stage=stage,
            reason_category=category,
            message=message,
        )

    @staticmethod
    def _article_failure(
        article: Article, *, stage: PipelineStage, category: str, message: str
    ) -> FailureDetail:
        return FailureDetail(
            article_id=article.id,
            source=article.source,
            external_id=article.external_id,
            url=_safe_url(article.url),
            stage=stage,
            reason_category=category,
            message=message,
        )

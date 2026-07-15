"""Domain enumerations for processing state and UPSC classification."""

from enum import StrEnum


class ProcessingStatus(StrEnum):
    """Lifecycle state of an Article as it moves through the pipeline."""

    DISCOVERED = "discovered"
    EXTRACTED = "extracted"
    ANALYSIS_PENDING = "analysis_pending"
    ANALYZED = "analyzed"
    FAILED = "failed"


class GSPaper(StrEnum):
    """UPSC General Studies paper classification (GS1 through GS4)."""

    GS1 = "gs1"
    GS2 = "gs2"
    GS3 = "gs3"
    GS4 = "gs4"

"""OpenAI-based implementation of `LearningNoteGenerator`.

Uses the OpenAI Responses API's native structured-output parsing
(`client.responses.parse(..., text_format=LearningNoteContent)`) exclusively
- there is no manual JSON parsing, Markdown stripping, or regex extraction
anywhere in this module. Pydantic (via the SDK's own use of
`LearningNoteContent.model_validate_json`) remains the sole validator of
model output.

Only the narrow `responses.parse` surface is abstracted behind
`_ResponsesClient`, a private structural Protocol - this is a test seam, not
a second application-facing provider abstraction. Production code always
constructs the real `openai.OpenAI` client; tests inject a handwritten fake
implementing `_ResponsesClient` and never touch the network.
"""

import logging
from pathlib import Path
from typing import Protocol, cast

import pydantic
from openai import OpenAI, OpenAIError
from openai.types.responses import EasyInputMessageParam, ParsedResponse

from app.application.learning_notes import (
    LearningNoteProviderError,
    LearningNoteValidationError,
    assemble_learning_note,
)
from app.domain.article import Article
from app.domain.learning_note import LearningNote, LearningNoteContent
from app.infrastructure.prompt_loader import load_prompt_template

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_SDK_MAX_RETRIES = 2

# Fixed Sprint 5 application policy: at most one original structured-output
# request plus two validation-repair requests. Not configurable by callers -
# SDK transport retries (`sdk_max_retries`) remain separately configurable,
# but this bound on *application-level* validation retries is not.
MAX_VALIDATION_ATTEMPTS = 3

_SYSTEM_PROMPT_FILENAME = f"learning_note_{PROMPT_VERSION}_system.txt"
_USER_PROMPT_FILENAME = f"learning_note_{PROMPT_VERSION}_user.txt"
_USER_PROMPT_PLACEHOLDERS = frozenset({"article_metadata", "article_text", "repair_instruction"})

_GENERIC_REPAIR_INSTRUCTION = (
    "Your previous response did not match the required schema. "
    "Return corrected structured output that matches the schema exactly, "
    "with every field present and every list explicit (use an empty list "
    "when a category is not relevant)."
)


class _ResponsesClient(Protocol):
    """The narrow subset of `openai.resources.responses.Responses` this adapter needs."""

    def parse(
        self,
        *,
        model: str,
        input: list[EasyInputMessageParam],
        text_format: type[LearningNoteContent],
    ) -> ParsedResponse[LearningNoteContent]:
        """Request structured output parsed into `LearningNoteContent`."""
        ...


def _build_article_metadata(article: Article) -> str:
    """Build the article metadata block, omitting absent optional fields."""
    lines = [
        f"Title: {article.title}",
        f"Source: {article.source}",
        f"URL: {article.url}",
    ]
    if article.author:
        lines.append(f"Author: {article.author}")
    if article.published_at is not None:
        lines.append(f"Published: {article.published_at.isoformat()}")
    if article.categories:
        lines.append(f"Categories: {', '.join(article.categories)}")
    return "\n".join(lines)


def _build_repair_instruction(error: pydantic.ValidationError | None) -> str:
    """Build a concise, sanitized repair instruction for a retry attempt.

    Includes only each error's field location and type/message - never the
    rejected input value, and never the complete `str(exc)` rendering.
    """
    if error is None:
        return _GENERIC_REPAIR_INSTRUCTION
    issues = [
        f"- {'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
        for err in error.errors(include_url=False, include_context=False, include_input=False)
    ]
    issue_list = "\n".join(issues[:10])
    return (
        "Your previous response did not match the required schema. "
        f"Specific issues:\n{issue_list}\n"
        "Return corrected structured output that matches the schema exactly."
    )


def _find_refusal(response: ParsedResponse[LearningNoteContent]) -> str | None:
    """Return the refusal text if the response contains typed refusal content."""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "refusal":
                    return content.refusal
    return None


class OpenAILearningNoteGenerator:
    """Generates validated Learning Notes using the OpenAI Responses API."""

    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None = None,
        responses: _ResponsesClient | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        sdk_max_retries: int = DEFAULT_SDK_MAX_RETRIES,
        prompts_dir: Path | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if responses is not None:
            if api_key is not None:
                raise ValueError("provide exactly one of `api_key` or `responses`, not both")
            self._responses: _ResponsesClient = responses
        elif api_key is not None:
            if not api_key.strip():
                raise ValueError("api_key must be a non-empty string")
            client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=sdk_max_retries)
            # `Responses.parse` accepts far more optional parameters (all
            # `Omit`-defaulted) than `_ResponsesClient` declares; only the
            # `model`/`input`/`text_format` keyword arguments are ever passed
            # below, which is valid at runtime - confirmed by direct source
            # inspection, not assumed. The cast bridges the real, complex SDK
            # signature to this adapter's narrow test seam.
            self._responses = cast(_ResponsesClient, client.responses)
        else:
            raise ValueError("provide exactly one of `api_key` or `responses`")

        self._model_name = model_name
        self._system_template = load_prompt_template(
            _SYSTEM_PROMPT_FILENAME,
            expected_placeholders=frozenset(),
            prompts_dir=prompts_dir,
        )
        self._user_template = load_prompt_template(
            _USER_PROMPT_FILENAME,
            expected_placeholders=_USER_PROMPT_PLACEHOLDERS,
            prompts_dir=prompts_dir,
        )

    def generate(self, article: Article) -> LearningNote:
        if article.raw_text is None or not article.raw_text.strip():
            raise ValueError("article.raw_text must not be None, blank, or whitespace-only")

        system_prompt = self._system_template.substitute()
        article_metadata = _build_article_metadata(article)

        last_validation_error: pydantic.ValidationError | None = None
        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            repair_instruction = (
                "" if attempt == 1 else _build_repair_instruction(last_validation_error)
            )
            user_prompt = self._user_template.substitute(
                article_metadata=article_metadata,
                article_text=article.raw_text,
                repair_instruction=repair_instruction,
            )

            logger.info(
                "learning note generation started article_id=%s attempt=%d model=%s",
                article.id,
                attempt,
                self._model_name,
            )

            try:
                response = self._responses.parse(
                    model=self._model_name,
                    input=[
                        EasyInputMessageParam(role="system", content=system_prompt),
                        EasyInputMessageParam(role="user", content=user_prompt),
                    ],
                    text_format=LearningNoteContent,
                )
            except pydantic.ValidationError as exc:
                last_validation_error = exc
                logger.warning(
                    "learning note validation failed article_id=%s attempt=%d "
                    "category=schema_validation",
                    article.id,
                    attempt,
                )
                continue
            except OpenAIError as exc:
                logger.error(
                    "learning note provider failure article_id=%s attempt=%d error_type=%s",
                    article.id,
                    attempt,
                    type(exc).__name__,
                )
                raise LearningNoteProviderError(
                    f"OpenAI provider error: {type(exc).__name__}"
                ) from exc

            status = response.status

            if status == "incomplete":
                details = response.incomplete_details
                reason = details.reason if details else None
                known_reasons = ("max_output_tokens", "content_filter")
                category = reason if reason in known_reasons else "unknown"
                logger.error(
                    "learning note incomplete response article_id=%s attempt=%d category=%s",
                    article.id,
                    attempt,
                    category,
                )
                raise LearningNoteProviderError(f"incomplete response: {category}")

            if status in ("failed", "cancelled", "in_progress", "queued"):
                # Provider outcomes, not validation failures: never retried, and
                # never carrying raw response error detail into the message. A
                # synchronous, non-background, non-streaming `responses.parse()`
                # call is not expected to return `in_progress`/`queued`, but they
                # are handled explicitly rather than falling through into the
                # "no parsed content" retry path, which is reserved for
                # `completed` responses only.
                logger.error(
                    "learning note response not completed article_id=%s attempt=%d status=%s",
                    article.id,
                    attempt,
                    status,
                )
                raise LearningNoteProviderError(f"response status: {status}")

            if status != "completed":
                # Defensive: any other unrecognized status value.
                unexpected_status = status if status is not None else "unknown"
                logger.error(
                    "learning note response unexpected status article_id=%s attempt=%d status=%s",
                    article.id,
                    attempt,
                    unexpected_status,
                )
                raise LearningNoteProviderError(f"response status: {unexpected_status}")

            if _find_refusal(response) is not None:
                logger.error(
                    "learning note refused article_id=%s attempt=%d",
                    article.id,
                    attempt,
                )
                raise LearningNoteProviderError("model refused to generate a Learning Note")

            content = response.output_parsed
            if content is not None:
                logger.info(
                    "learning note generation succeeded article_id=%s attempts=%d "
                    "model=%s prompt_version=%s",
                    article.id,
                    attempt,
                    self._model_name,
                    PROMPT_VERSION,
                )
                return assemble_learning_note(
                    content,
                    article_id=article.id,
                    model_name=self._model_name,
                    prompt_version=PROMPT_VERSION,
                )

            last_validation_error = None
            logger.warning(
                "learning note validation retry article_id=%s attempt=%d category=%s",
                article.id,
                attempt,
                "no_parsed_content",
            )

        logger.error(
            "learning note validation exhausted article_id=%s attempts=%d",
            article.id,
            MAX_VALIDATION_ATTEMPTS,
        )
        raise LearningNoteValidationError(
            f"exhausted {MAX_VALIDATION_ATTEMPTS} validation attempts"
        ) from last_validation_error

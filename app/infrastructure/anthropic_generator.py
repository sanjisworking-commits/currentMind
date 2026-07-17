"""Anthropic-based implementation of `LearningNoteGenerator`.

Uses the Anthropic Messages API's native structured-output parsing
(`client.messages.parse(..., output_format=LearningNoteContent)`) exclusively
- there is no manual JSON parsing, Markdown stripping, or regex extraction
anywhere in this module. Pydantic (via the SDK's own use of
`TypeAdapter.validate_json`) remains the sole validator of model output, so an
invalid response raises `pydantic.ValidationError` exactly as the OpenAI
adapter's `responses.parse` does.

Only the narrow `messages.parse` surface is abstracted behind
`_MessagesClient`, a private structural Protocol - this is a test seam, not a
second application-facing provider abstraction. Production code always
constructs the real `anthropic.Anthropic` client; tests inject a handwritten
fake implementing `_MessagesClient` and never touch the network.

This adapter mirrors `OpenAILearningNoteGenerator`: the same fixed
three-attempt validation-repair policy, the same privacy rules (no article
text, no raw provider output, no API key, no rejected value ever logged), and
the same source-neutral prompt files (`learning_note_v1_*`) and prompt
version. Only the provider SDK and its response shape differ.
"""

import logging
from pathlib import Path
from typing import Protocol, cast

import pydantic
from anthropic import Anthropic, AnthropicError
from anthropic.types import MessageParam, ParsedMessage

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

# Upper bound on tokens the model may produce for one structured Learning
# Note. Generous enough for the 15 fields plus a few Prelims/Mains questions;
# a truncated response surfaces as stop_reason="max_tokens" and is treated as
# a non-retryable incomplete-response provider failure, never silently used.
DEFAULT_MAX_TOKENS = 8192

# Fixed application policy, identical to the OpenAI adapter: at most one
# original structured-output request plus two validation-repair requests. Not
# configurable by callers - SDK transport retries (`sdk_max_retries`) remain
# separately configurable, but this bound on *application-level* validation
# retries is not.
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


class _MessagesClient(Protocol):
    """The narrow subset of `anthropic.resources.messages.Messages` this adapter needs."""

    def parse(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[MessageParam],
        output_format: type[LearningNoteContent],
    ) -> ParsedMessage[LearningNoteContent]:
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


class AnthropicLearningNoteGenerator:
    """Generates validated Learning Notes using the Anthropic Messages API."""

    def __init__(
        self,
        *,
        model_name: str,
        api_key: str | None = None,
        messages: _MessagesClient | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        sdk_max_retries: int = DEFAULT_SDK_MAX_RETRIES,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        prompts_dir: Path | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")

        if messages is not None:
            if api_key is not None:
                raise ValueError("provide exactly one of `api_key` or `messages`, not both")
            self._messages: _MessagesClient = messages
        elif api_key is not None:
            if not api_key.strip():
                raise ValueError("api_key must be a non-empty string")
            client = Anthropic(
                api_key=api_key, timeout=timeout_seconds, max_retries=sdk_max_retries
            )
            # `Messages.parse` accepts far more optional parameters (all
            # `Omit`-defaulted) than `_MessagesClient` declares; only the
            # `model`/`max_tokens`/`system`/`messages`/`output_format` keyword
            # arguments are ever passed below, which is valid at runtime. The
            # cast bridges the real, complex SDK signature to this adapter's
            # narrow test seam.
            self._messages = cast(_MessagesClient, client.messages)
        else:
            raise ValueError("provide exactly one of `api_key` or `messages`")

        self._model_name = model_name
        self._max_tokens = max_tokens
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
                response = self._messages.parse(
                    model=self._model_name,
                    max_tokens=self._max_tokens,
                    system=system_prompt,
                    messages=[MessageParam(role="user", content=user_prompt)],
                    output_format=LearningNoteContent,
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
            except AnthropicError as exc:
                logger.error(
                    "learning note provider failure article_id=%s attempt=%d error_type=%s",
                    article.id,
                    attempt,
                    type(exc).__name__,
                )
                raise LearningNoteProviderError(
                    f"Anthropic provider error: {type(exc).__name__}"
                ) from exc

            stop_reason = response.stop_reason

            if stop_reason == "refusal":
                # A safety refusal is a provider outcome, never a validation
                # failure: raised immediately, never retried, and never
                # carrying the refusal explanation into the message or logs.
                logger.error(
                    "learning note refused article_id=%s attempt=%d",
                    article.id,
                    attempt,
                )
                raise LearningNoteProviderError("model refused to generate a Learning Note")

            if stop_reason == "max_tokens":
                logger.error(
                    "learning note incomplete response article_id=%s attempt=%d category=%s",
                    article.id,
                    attempt,
                    "max_output_tokens",
                )
                raise LearningNoteProviderError("incomplete response: max_output_tokens")

            if stop_reason != "end_turn":
                # `end_turn` is the ONLY accepted normal-completion signal for
                # this tool-free, single-message request. `tool_use`,
                # `pause_turn`, `stop_sequence`, a missing `None`, and any
                # future/unknown value are all treated as provider outcomes and
                # rejected immediately - never accepted as success and never
                # falling through into the "no parsed content" retry path. This
                # allowlist-of-one keeps the check safe against SDK stop-reason
                # values added after this code was written.
                logger.error(
                    "learning note response unexpected stop reason article_id=%s attempt=%d "
                    "stop_reason=%s",
                    article.id,
                    attempt,
                    stop_reason,
                )
                raise LearningNoteProviderError(f"response stop reason: {stop_reason}")

            content = response.parsed_output
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

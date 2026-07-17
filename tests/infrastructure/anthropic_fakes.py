"""Handwritten fakes for testing `AnthropicLearningNoteGenerator` with no network access.

`FakeMessagesClient` implements the same narrow `_MessagesClient` surface the
adapter depends on (`.parse(model=..., max_tokens=..., system=..., messages=...,
output_format=...)`) - it is a fake of the low-level SDK call surface, not a
fake of the generator itself, so tests exercise the real retry/assembly/
error-translation logic.
"""

from typing import Any

from anthropic.types import ParsedMessage
from anthropic.types.parsed_message import ParsedTextBlock

from app.domain.learning_note import LearningNoteContent


def make_parsed_message(
    *,
    content: LearningNoteContent | None = None,
    stop_reason: str | None = "end_turn",
) -> ParsedMessage[LearningNoteContent]:
    """Build a real `ParsedMessage`, using `model_construct` to skip validating
    the many response fields this adapter never reads.

    When `content` is provided, a parsed text block carries it (mirroring how
    the SDK's `messages.parse` attaches the validated `parsed_output`). When it
    is `None`, the message has no parsed content block.
    """
    content_blocks: list[Any] = []
    if content is not None:
        content_blocks.append(
            ParsedTextBlock.model_construct(
                type="text", text="{}", citations=None, parsed_output=content
            )
        )
    return ParsedMessage.model_construct(
        id="msg_1",
        container=None,
        content=content_blocks,
        model="claude-test",
        role="assistant",
        stop_details=None,
        stop_reason=stop_reason,
        stop_sequence=None,
        type="message",
        usage=None,
    )


class FakeMessagesClient:
    """Scripted fake: each `.parse()` call pops and returns/raises the next result."""

    def __init__(
        self, results: list[ParsedMessage[LearningNoteContent] | BaseException]
    ) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    def parse(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[Any],
        output_format: type[LearningNoteContent],
    ) -> ParsedMessage[LearningNoteContent]:
        self.calls.append(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
                "output_format": output_format,
            }
        )
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

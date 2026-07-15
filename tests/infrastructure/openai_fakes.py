"""Handwritten fakes for testing `OpenAILearningNoteGenerator` with no network access.

`FakeResponsesClient` implements the same narrow `_ResponsesClient` surface
the adapter depends on (`.parse(model=..., input=..., text_format=...)`) -
it is a fake of the low-level SDK call surface, not a fake of the generator
itself, so tests exercise the real retry/assembly/error-translation logic.
"""

from typing import Any

from openai.types.responses import ParsedResponse
from openai.types.responses.parsed_response import (
    ParsedResponseOutputMessage,
    ParsedResponseOutputText,
)
from openai.types.responses.response import IncompleteDetails
from openai.types.responses.response_output_refusal import ResponseOutputRefusal

from app.domain.learning_note import LearningNoteContent


def make_parsed_response(
    *,
    content: LearningNoteContent | None = None,
    refusal: str | None = None,
    status: str = "completed",
    incomplete_reason: str | None = None,
) -> ParsedResponse[LearningNoteContent]:
    """Build a real `ParsedResponse`, using `model_construct` to skip
    validating the many response fields this adapter never reads.
    """
    content_items: list[Any] = []
    if content is not None:
        content_items.append(
            ParsedResponseOutputText.model_construct(
                type="output_text", text="{}", annotations=[], parsed=content
            )
        )
    if refusal is not None:
        content_items.append(
            ResponseOutputRefusal.model_construct(type="refusal", refusal=refusal)
        )

    message: ParsedResponseOutputMessage[LearningNoteContent] = (
        ParsedResponseOutputMessage.model_construct(
            type="message",
            id="msg_1",
            status="completed",
            role="assistant",
            content=content_items,
        )
    )
    incomplete_details = (
        IncompleteDetails(reason=incomplete_reason) if status == "incomplete" else None  # type: ignore[arg-type]
    )
    return ParsedResponse.model_construct(
        id="resp_1",
        created_at=0.0,
        model="gpt-test",
        object="response",
        output=[message],
        status=status,
        incomplete_details=incomplete_details,
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
    )


class FakeResponsesClient:
    """Scripted fake: each `.parse()` call pops and returns/raises the next result."""

    def __init__(self, results: list[ParsedResponse[LearningNoteContent] | BaseException]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    def parse(
        self,
        *,
        model: str,
        input: list[Any],
        text_format: type[LearningNoteContent],
    ) -> ParsedResponse[LearningNoteContent]:
        self.calls.append({"model": model, "input": input, "text_format": text_format})
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

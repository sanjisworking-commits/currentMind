"""Tests for `OpenAILearningNoteGenerator`.

Every test injects a handwritten `FakeResponsesClient` (see `openai_fakes.py`)
via the adapter's `responses=` constructor parameter - no test ever
constructs a real `openai.OpenAI` client or touches the network. These tests
exercise the real generator: retry policy, request construction, response
handling, error translation, and logging - never a fake `LearningNoteGenerator`.
"""

import logging

import httpx
import pydantic
import pytest
from openai import APIConnectionError, AuthenticationError, InternalServerError, RateLimitError

from app.application.learning_notes import LearningNoteProviderError, LearningNoteValidationError
from app.domain.article import Article
from app.domain.enums import GSPaper, ProcessingStatus
from app.domain.learning_note import LearningNoteContent
from app.infrastructure.openai_generator import OpenAILearningNoteGenerator
from tests.infrastructure.openai_fakes import FakeResponsesClient, make_parsed_response

_VALID_CONTENT = LearningNoteContent(
    summary="s",
    why_it_matters="w",
    gs_papers=[GSPaper.GS2],
    subjects=[],
    syllabus_topics=[],
    static_concepts=[],
    constitutional_linkages=[],
    government_schemes=[],
    reports_and_committees=[],
    international_dimensions=[],
    important_facts=[],
    prelims_questions=[],
    mains_questions=[],
    revision_note="r",
    keywords=[],
)


def _make_article(
    *, raw_text: str | None = "Some article body text about a UPSC topic."
) -> Article:
    return Article(
        source="indian_express",
        title="A Title",
        url="https://indianexpress.com/article",
        raw_text=raw_text,
        processing_status=ProcessingStatus.EXTRACTED,
    )


def _make_validation_error() -> pydantic.ValidationError:
    try:
        LearningNoteContent.model_validate({})
    except pydantic.ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def _auth_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/responses")


# --- construction -----------------------------------------------------------


def test_constructor_requires_exactly_one_of_api_key_or_responses() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        OpenAILearningNoteGenerator(model_name="gpt-test")


def test_constructor_rejects_both_api_key_and_responses() -> None:
    fake = FakeResponsesClient([])
    with pytest.raises(ValueError, match="not both"):
        OpenAILearningNoteGenerator(model_name="gpt-test", api_key="sk-test", responses=fake)


def test_constructor_rejects_blank_model_name() -> None:
    fake = FakeResponsesClient([])
    with pytest.raises(ValueError):
        OpenAILearningNoteGenerator(model_name="   ", responses=fake)


# --- caller contract: invalid input ------------------------------------------


def test_raw_text_none_rejected_before_provider_call() -> None:
    fake = FakeResponsesClient([])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(ValueError):
        generator.generate(_make_article(raw_text=None))
    assert fake.calls == []


def test_blank_raw_text_rejected_before_provider_call() -> None:
    fake = FakeResponsesClient([])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(ValueError):
        generator.generate(_make_article(raw_text="   "))
    assert fake.calls == []


# --- successful generation and request construction --------------------------


def test_valid_first_response_returns_learning_note() -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    article = _make_article()

    note = generator.generate(article)

    assert note.article_id == article.id
    assert note.summary == _VALID_CONTENT.summary


def test_request_uses_configured_model() -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-configured", responses=fake)
    generator.generate(_make_article())
    assert fake.calls[0]["model"] == "gpt-configured"


def test_request_passes_learning_note_content_as_text_format() -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    generator.generate(_make_article())
    assert fake.calls[0]["text_format"] is LearningNoteContent


def test_final_metadata_is_locally_supplied_not_from_content() -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-configured", responses=fake)
    article = _make_article()
    note = generator.generate(article)
    assert note.model_name == "gpt-configured"
    assert note.prompt_version == "v1"
    assert note.article_id == article.id


# --- validation retry policy --------------------------------------------------


def test_recoverable_validation_failure_then_success() -> None:
    fake = FakeResponsesClient(
        [_make_validation_error(), make_parsed_response(content=_VALID_CONTENT)]
    )
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    note = generator.generate(_make_article())
    assert note.summary == _VALID_CONTENT.summary
    assert len(fake.calls) == 2


def test_repair_instruction_empty_on_first_attempt_and_present_on_retry() -> None:
    fake = FakeResponsesClient(
        [_make_validation_error(), make_parsed_response(content=_VALID_CONTENT)]
    )
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    generator.generate(_make_article())

    first_user_content = fake.calls[0]["input"][1]["content"]
    second_user_content = fake.calls[1]["input"][1]["content"]
    assert first_user_content != second_user_content
    assert "did not match the required schema" in second_user_content


def test_completed_response_without_parsed_content_then_success() -> None:
    fake = FakeResponsesClient(
        [make_parsed_response(content=None), make_parsed_response(content=_VALID_CONTENT)]
    )
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    note = generator.generate(_make_article())
    assert note.summary == _VALID_CONTENT.summary
    assert len(fake.calls) == 2


def test_three_failed_validation_attempts_raise_validation_error() -> None:
    error = _make_validation_error()
    fake = FakeResponsesClient([error, error, error])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteValidationError):
        generator.generate(_make_article())
    assert len(fake.calls) == 3


def test_only_three_total_attempts_occur_even_with_more_scripted_failures() -> None:
    error = _make_validation_error()
    fake = FakeResponsesClient([error, error, error, make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteValidationError):
        generator.generate(_make_article())
    assert len(fake.calls) == 3


def test_validation_error_exception_chaining_preserved() -> None:
    error = _make_validation_error()
    fake = FakeResponsesClient([error, error, error])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteValidationError) as excinfo:
        generator.generate(_make_article())
    assert excinfo.value.__cause__ is error


# --- non-retryable provider failures ------------------------------------------


def test_refusal_produces_immediate_provider_error_with_no_retry() -> None:
    fake = FakeResponsesClient([make_parsed_response(refusal="I will not help with that.")])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteProviderError):
        generator.generate(_make_article())
    assert len(fake.calls) == 1


def test_incomplete_max_output_tokens_produces_immediate_provider_error() -> None:
    fake = FakeResponsesClient(
        [make_parsed_response(status="incomplete", incomplete_reason="max_output_tokens")]
    )
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteProviderError, match="max_output_tokens"):
        generator.generate(_make_article())
    assert len(fake.calls) == 1


def test_incomplete_content_filter_produces_immediate_provider_error() -> None:
    fake = FakeResponsesClient(
        [make_parsed_response(status="incomplete", incomplete_reason="content_filter")]
    )
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteProviderError, match="content_filter"):
        generator.generate(_make_article())
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "status",
    ["failed", "cancelled", "in_progress", "queued"],
)
def test_non_completed_status_produces_immediate_provider_error_with_no_retry(
    status: str,
) -> None:
    """Every non-`completed`, non-`incomplete` Responses status is a provider
    outcome, never a validation failure: it must raise `LearningNoteProviderError`
    immediately, with exactly one provider call, never treated as malformed
    structured output eligible for a validation retry.
    """
    fake = FakeResponsesClient([make_parsed_response(status=status, content=None)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteProviderError, match=status):
        generator.generate(_make_article())
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "status",
    ["failed", "cancelled", "in_progress", "queued", "incomplete"],
)
def test_non_completed_status_error_contains_only_safe_category(
    status: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Error messages and logs for a non-completed status must contain only the
    safe status category - never article text or raw response content.
    """
    sensitive_marker = "UNMISTAKABLE-ARTICLE-BODY-MARKER"
    fake = FakeResponsesClient([make_parsed_response(status=status, content=None)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with caplog.at_level(logging.INFO), pytest.raises(LearningNoteProviderError) as excinfo:
        generator.generate(_make_article(raw_text=sensitive_marker))
    assert sensitive_marker not in str(excinfo.value)
    assert sensitive_marker not in caplog.text
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "sdk_error_factory",
    [
        lambda: APIConnectionError(request=_auth_request()),
        lambda: AuthenticationError(
            "invalid api key", response=httpx.Response(401, request=_auth_request()), body=None
        ),
        lambda: RateLimitError(
            "rate limited", response=httpx.Response(429, request=_auth_request()), body=None
        ),
        lambda: InternalServerError(
            "server error", response=httpx.Response(500, request=_auth_request()), body=None
        ),
    ],
    ids=["connection", "authentication", "rate_limit", "server_error"],
)
def test_sdk_operational_failures_produce_provider_error_with_no_application_retry(
    sdk_error_factory: "object",
) -> None:
    error = sdk_error_factory()  # type: ignore[operator]
    fake = FakeResponsesClient([error])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with pytest.raises(LearningNoteProviderError) as excinfo:
        generator.generate(_make_article())
    assert len(fake.calls) == 1
    assert excinfo.value.__cause__ is error


# --- logging and privacy ------------------------------------------------------


def test_logs_do_not_contain_article_body(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    article = _make_article(raw_text="UNMISTAKABLE-ARTICLE-BODY-MARKER")
    with caplog.at_level(logging.INFO):
        generator.generate(article)
    assert "UNMISTAKABLE-ARTICLE-BODY-MARKER" not in caplog.text


def test_logs_do_not_contain_api_key(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with caplog.at_level(logging.INFO):
        generator.generate(_make_article())
    assert "sk-" not in caplog.text


def test_logs_do_not_contain_raw_output_or_refusal_text(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeResponsesClient([make_parsed_response(refusal="UNMISTAKABLE-REFUSAL-TEXT")])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with caplog.at_level(logging.INFO), pytest.raises(LearningNoteProviderError):
        generator.generate(_make_article())
    assert "UNMISTAKABLE-REFUSAL-TEXT" not in caplog.text


def test_logs_do_not_contain_rejected_pydantic_input_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = _make_validation_error()
    fake = FakeResponsesClient([error, error, error])
    generator = OpenAILearningNoteGenerator(model_name="gpt-test", responses=fake)
    with caplog.at_level(logging.INFO), pytest.raises(LearningNoteValidationError):
        generator.generate(_make_article())
    # the ValidationError's default str() rendering embeds the rejected input;
    # confirm that full rendering never appears in any log record.
    assert str(error) not in caplog.text


def test_logs_include_safe_context(caplog: pytest.LogCaptureFixture) -> None:
    fake = FakeResponsesClient([make_parsed_response(content=_VALID_CONTENT)])
    generator = OpenAILearningNoteGenerator(model_name="gpt-configured", responses=fake)
    article = _make_article()
    with caplog.at_level(logging.INFO):
        generator.generate(article)
    assert str(article.id) in caplog.text
    assert "gpt-configured" in caplog.text

"""Tests for provider selection in the CLI composition root (`_build_generator`).

These exercise the real `app.cli._build_generator` against a real `Settings`
instance, with the two concrete generator constructors monkeypatched to
recorders. No SDK client is constructed, no database is touched, and no external
service is contacted: the recorders prove which adapter was selected, the model
name and provider key passed to it, and that the unselected provider was never
constructed.

**Dotenv loading is explicitly disabled.** `Settings` is normally configured to
read the repository's `.env`, so an untracked developer `.env` could otherwise
change `LLM_PROVIDER` (or the keys) under these tests. Every `Settings` here is
built via `_settings_without_dotenv()` (`_env_file=None`), so the tests read
*only* the environment variables installed through `monkeypatch` - never a
`.env`, the current working directory, a developer's provider selection, or a
developer's real keys.
"""

from pathlib import Path

import pytest

import app.cli as cli
from app.infrastructure.config import Settings


def _settings_without_dotenv() -> Settings:
    """Build `Settings` with dotenv loading disabled.

    Passing `_env_file=None` overrides the model's configured `.env` file so the
    resulting settings are sourced only from process environment variables (and
    field defaults) - making these tests independent of any local `.env`.
    """
    # `_env_file` is a real pydantic-settings `BaseSettings.__init__` argument
    # (it disables dotenv loading at runtime, verified in this module's tests),
    # but it is not part of the field-only `__init__` signature the type checker
    # synthesizes for the model - hence the targeted ignore.
    return Settings(_env_file=None)  # type: ignore[call-arg]


class _Recorder:
    """Stand-in for a generator constructor; records how it was called."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    def __call__(self, *, model_name: str, api_key: str) -> object:
        self.calls.append({"model_name": model_name, "api_key": api_key})
        return object()


def _patch_generators(monkeypatch: pytest.MonkeyPatch) -> tuple[_Recorder, _Recorder]:
    openai_recorder = _Recorder()
    anthropic_recorder = _Recorder()
    monkeypatch.setattr(cli, "OpenAILearningNoteGenerator", openai_recorder)
    monkeypatch.setattr(cli, "AnthropicLearningNoteGenerator", anthropic_recorder)
    return openai_recorder, anthropic_recorder


def _prepare_env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: str | None = None,
    openai_key: str = "sk-openai-not-real",
    anthropic_key: str = "sk-ant-not-real",
    model: str = "the-model",
) -> None:
    """Set the four configuration variables `_build_generator` reads.

    `provider=None` leaves `LLM_PROVIDER` unset so the `Settings` default
    applies. An empty-string key or model represents an absent/blank value.
    """
    if provider is None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("OPENAI_API_KEY", openai_key)
    monkeypatch.setenv("ANTHROPIC_API_KEY", anthropic_key)
    monkeypatch.setenv("LLM_MODEL", model)


# --- selection ---------------------------------------------------------------


def test_default_provider_selects_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider=None)

    cli._build_generator(_settings_without_dotenv())

    assert len(openai_recorder.calls) == 1
    assert openai_recorder.calls[0] == {"model_name": "the-model", "api_key": "sk-openai-not-real"}
    assert anthropic_recorder.calls == []


def test_explicit_openai_selects_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="openai")

    cli._build_generator(_settings_without_dotenv())

    assert len(openai_recorder.calls) == 1
    assert anthropic_recorder.calls == []


def test_explicit_anthropic_selects_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="anthropic")

    cli._build_generator(_settings_without_dotenv())

    assert len(anthropic_recorder.calls) == 1
    assert anthropic_recorder.calls[0] == {
        "model_name": "the-model",
        "api_key": "sk-ant-not-real",
    }
    assert openai_recorder.calls == []


@pytest.mark.parametrize(
    ("raw_provider", "expected"),
    [
        ("  anthropic  ", "anthropic"),
        ("OpenAI", "openai"),
        ("  ANTHROPIC", "anthropic"),
        ("openai  ", "openai"),
    ],
)
def test_provider_value_is_normalized_for_whitespace_and_case(
    monkeypatch: pytest.MonkeyPatch, raw_provider: str, expected: str
) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider=raw_provider)

    cli._build_generator(_settings_without_dotenv())

    if expected == "anthropic":
        assert len(anthropic_recorder.calls) == 1
        assert openai_recorder.calls == []
    else:
        assert len(openai_recorder.calls) == 1
        assert anthropic_recorder.calls == []


def test_llm_provider_alone_determines_adapter_when_both_keys_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    # Both keys are non-empty; only LLM_PROVIDER should decide.
    _prepare_env(
        monkeypatch, provider="anthropic", openai_key="sk-openai-set", anthropic_key="sk-ant-set"
    )

    cli._build_generator(_settings_without_dotenv())

    assert len(anthropic_recorder.calls) == 1
    assert anthropic_recorder.calls[0]["api_key"] == "sk-ant-set"
    assert openai_recorder.calls == []


# --- provider-specific configuration requirements ----------------------------


def test_openai_requires_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="openai", openai_key="")

    with pytest.raises(cli.CompositionError, match="OPENAI_API_KEY is required"):
        cli._build_generator(_settings_without_dotenv())
    assert openai_recorder.calls == []
    assert anthropic_recorder.calls == []


def test_openai_does_not_require_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="openai", anthropic_key="")

    cli._build_generator(_settings_without_dotenv())

    assert len(openai_recorder.calls) == 1
    assert anthropic_recorder.calls == []


def test_anthropic_requires_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="anthropic", anthropic_key="")

    with pytest.raises(cli.CompositionError, match="ANTHROPIC_API_KEY is required"):
        cli._build_generator(_settings_without_dotenv())
    assert anthropic_recorder.calls == []
    assert openai_recorder.calls == []


def test_anthropic_does_not_require_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="anthropic", openai_key="")

    cli._build_generator(_settings_without_dotenv())

    assert len(anthropic_recorder.calls) == 1
    assert openai_recorder.calls == []


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_both_providers_require_llm_model(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider=provider, model="")

    with pytest.raises(cli.CompositionError, match="LLM_MODEL is required"):
        cli._build_generator(_settings_without_dotenv())
    assert openai_recorder.calls == []
    assert anthropic_recorder.calls == []


# --- unknown provider --------------------------------------------------------


def test_unknown_provider_raises_safe_actionable_error_and_constructs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    _prepare_env(monkeypatch, provider="gemini")

    with pytest.raises(cli.CompositionError) as excinfo:
        cli._build_generator(_settings_without_dotenv())

    message = str(excinfo.value)
    assert "gemini" in message
    assert "openai" in message
    assert "anthropic" in message
    # An unknown provider must construct no SDK client (neither recorder was
    # called). `_build_generator` never touches the database or a network
    # service, so a clean rejection here proves no external effect occurs.
    assert openai_recorder.calls == []
    assert anthropic_recorder.calls == []


# --- dotenv isolation regression ---------------------------------------------


def test_helper_ignores_a_conflicting_dotenv_in_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A `.env` in the working directory must not influence these tests.

    With a `.env` that selects `anthropic` sitting in the current working
    directory and `LLM_PROVIDER` unset in the environment,
    `_settings_without_dotenv()` must still resolve the built-in default
    (`openai`) - proving dotenv loading is disabled and only monkeypatched
    environment variables (and field defaults) are read.
    """
    (tmp_path / ".env").write_text(
        "LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-ant-from-dotenv\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    openai_recorder, anthropic_recorder = _patch_generators(monkeypatch)
    # LLM_PROVIDER deliberately unset in the environment; only the .env sets it.
    _prepare_env(monkeypatch, provider=None)

    cli._build_generator(_settings_without_dotenv())

    # The default (openai) wins, not the .env's anthropic - dotenv was ignored.
    assert len(openai_recorder.calls) == 1
    assert anthropic_recorder.calls == []


def test_settings_would_read_dotenv_without_the_isolation_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control case: proves the `.env` in the working directory is real and
    would otherwise be read - so the isolation in the test above is meaningful,
    not vacuous. A plain `Settings()` (dotenv enabled) picks up the file, while
    `_settings_without_dotenv()` does not.
    """
    (tmp_path / ".env").write_text("LLM_PROVIDER=anthropic\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    assert Settings().llm_provider == "anthropic"  # dotenv-enabled reads the file
    assert _settings_without_dotenv().llm_provider == "openai"  # isolated: default

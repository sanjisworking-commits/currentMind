"""Loads and validates prompt templates for LLM generation.

Prompt files live under `prompts/` (outside Python source), one file per
role per prompt version. Templates are rendered with `string.Template`,
using `$identifier` placeholders exclusively: article content is untrusted
and may contain literal `{}`/`%` characters that other templating syntaxes
would need escaping for, so `string.Template` sidesteps that risk entirely.

A missing file, an empty file, or a placeholder set that does not exactly
match what the caller expects is a configuration or programming failure and
raises before any provider request is made - never a silent fallback to a
built-in prompt.
"""

from pathlib import Path
from string import Template

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def load_prompt_template(
    filename: str,
    *,
    expected_placeholders: frozenset[str],
    prompts_dir: Path | None = None,
) -> Template:
    """Load a prompt template and validate its placeholder set exactly.

    Args:
        filename: the prompt file name, resolved relative to `prompts_dir`.
        expected_placeholders: the exact `$identifier` set the template must
            contain - no more, no fewer.
        prompts_dir: overrides the real `prompts/` directory; a test seam.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the file is empty or whitespace-only, or its
            placeholder set does not exactly match `expected_placeholders`.
    """
    directory = prompts_dir if prompts_dir is not None else _DEFAULT_PROMPTS_DIR
    path = directory / filename
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"prompt template not found: {path}") from exc

    if not text.strip():
        raise ValueError(f"prompt template is empty: {path}")

    template = Template(text)
    found_placeholders = frozenset(template.get_identifiers())
    if found_placeholders != expected_placeholders:
        missing = expected_placeholders - found_placeholders
        unknown = found_placeholders - expected_placeholders
        raise ValueError(
            f"prompt template {path} placeholders do not match the expected set "
            f"{sorted(expected_placeholders)}: "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}"
        )

    return template

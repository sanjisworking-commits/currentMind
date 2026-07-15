"""Tests for `app.infrastructure.prompt_loader`."""

import os
from pathlib import Path

import pytest

from app.infrastructure.prompt_loader import load_prompt_template


def test_loads_real_shipped_system_prompt() -> None:
    template = load_prompt_template(
        "learning_note_v1_system.txt", expected_placeholders=frozenset()
    )
    rendered = template.substitute()
    assert "UPSC" in rendered
    assert len(rendered.strip()) > 0


def test_loads_real_shipped_user_prompt() -> None:
    template = load_prompt_template(
        "learning_note_v1_user.txt",
        expected_placeholders=frozenset({"article_metadata", "article_text", "repair_instruction"}),
    )
    rendered = template.substitute(
        article_metadata="Title: X", article_text="Body text.", repair_instruction=""
    )
    assert "Body text." in rendered


def test_path_resolution_independent_of_cwd(tmp_path: Path) -> None:
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        template = load_prompt_template(
            "learning_note_v1_system.txt", expected_placeholders=frozenset()
        )
        assert template.substitute()
    finally:
        os.chdir(original_cwd)


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt_template(
            "does_not_exist.txt", expected_placeholders=frozenset(), prompts_dir=tmp_path
        )


def test_empty_file_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_prompt_template("empty.txt", expected_placeholders=frozenset(), prompts_dir=tmp_path)


def test_whitespace_only_file_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "blank.txt").write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_prompt_template("blank.txt", expected_placeholders=frozenset(), prompts_dir=tmp_path)


def test_missing_placeholder_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "partial.txt").write_text("Hello $name", encoding="utf-8")
    with pytest.raises(ValueError, match="missing"):
        load_prompt_template(
            "partial.txt",
            expected_placeholders=frozenset({"name", "greeting"}),
            prompts_dir=tmp_path,
        )


def test_unknown_placeholder_raises_value_error(tmp_path: Path) -> None:
    (tmp_path / "extra.txt").write_text("Hello $name and $surprise", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown"):
        load_prompt_template(
            "extra.txt", expected_placeholders=frozenset({"name"}), prompts_dir=tmp_path
        )


def test_exact_placeholder_match_succeeds(tmp_path: Path) -> None:
    (tmp_path / "exact.txt").write_text("Hello $name", encoding="utf-8")
    template = load_prompt_template(
        "exact.txt", expected_placeholders=frozenset({"name"}), prompts_dir=tmp_path
    )
    assert template.substitute(name="world") == "Hello world"


def test_substitute_raises_on_missing_substitution_value(tmp_path: Path) -> None:
    (tmp_path / "needs_value.txt").write_text("Hello $name", encoding="utf-8")
    template = load_prompt_template(
        "needs_value.txt", expected_placeholders=frozenset({"name"}), prompts_dir=tmp_path
    )
    with pytest.raises(KeyError):
        template.substitute()


def test_article_content_with_braces_and_dollar_signs_is_inserted_literally(
    tmp_path: Path,
) -> None:
    (tmp_path / "article.txt").write_text("Article: $article_text", encoding="utf-8")
    template = load_prompt_template(
        "article.txt", expected_placeholders=frozenset({"article_text"}), prompts_dir=tmp_path
    )
    tricky_text = 'Body with {braces}, a JSON snippet {"key": "value"}, and a literal $5 price.'
    rendered = template.substitute(article_text=tricky_text)
    assert tricky_text in rendered


# --- prompt-injection boundary content ---------------------------------------
#
# These tests verify the *construction and boundaries* of the shipped prompts
# - that metadata and body are explicitly labelled untrusted and placed in
# clearly delimited blocks. They do not, and cannot, claim that prompt
# injection is mathematically eliminated.


def test_shipped_system_prompt_identifies_metadata_and_body_as_untrusted() -> None:
    template = load_prompt_template(
        "learning_note_v1_system.txt", expected_placeholders=frozenset()
    )
    rendered = template.substitute()
    assert "untrusted" in rendered.lower()
    assert "metadata" in rendered.lower()
    assert "body" in rendered.lower()


def test_shipped_system_prompt_states_delimiter_looking_text_remains_untrusted() -> None:
    template = load_prompt_template(
        "learning_note_v1_system.txt", expected_placeholders=frozenset()
    )
    rendered = template.substitute().lower()
    assert "delimiter" in rendered
    assert "not a boundary" in rendered or "never as directions" in rendered


def test_shipped_user_prompt_places_metadata_in_its_own_untrusted_block() -> None:
    template = load_prompt_template(
        "learning_note_v1_user.txt",
        expected_placeholders=frozenset({"article_metadata", "article_text", "repair_instruction"}),
    )
    sentinel = "SENTINEL-METADATA-VALUE"
    rendered = template.substitute(
        article_metadata=sentinel, article_text="Body.", repair_instruction=""
    )
    begin = rendered.index("BEGIN ARTICLE METADATA")
    end = rendered.index("END ARTICLE METADATA")
    sentinel_index = rendered.index(sentinel)
    assert begin < sentinel_index < end
    assert "UNTRUSTED SOURCE DATA" in rendered[begin:end]


def test_shipped_user_prompt_places_body_in_its_own_untrusted_block() -> None:
    template = load_prompt_template(
        "learning_note_v1_user.txt",
        expected_placeholders=frozenset({"article_metadata", "article_text", "repair_instruction"}),
    )
    sentinel = "SENTINEL-BODY-VALUE"
    rendered = template.substitute(
        article_metadata="Title: X", article_text=sentinel, repair_instruction=""
    )
    begin = rendered.index("BEGIN ARTICLE BODY")
    end = rendered.index("END ARTICLE BODY")
    sentinel_index = rendered.index(sentinel)
    assert begin < sentinel_index < end
    assert "UNTRUSTED SOURCE DATA" in rendered[begin:end]

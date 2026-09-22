"""Tests for the Markdown shortcode preprocessor and extension registration."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import pelican.plugins.tabular.tabular as _mod

_HAS_MARKDOWN = _mod._HAS_MARKDOWN

pytestmark = pytest.mark.skipif(not _HAS_MARKDOWN, reason="markdown not installed")


@pytest.mark.parametrize("view", [False, True], ids=["plain", "view"])
@pytest.mark.parametrize(
    ("shortcode", "template"),
    [
        pytest.param("table", "{% table rows.yaml OPTIONS %}", id="standard"),
        pytest.param("table", "{%- table rows.yaml\n OPTIONS -%}", id="multiline"),
        pytest.param("data-table", "{% data-table rows.yaml OPTIONS %}", id="custom"),
    ],
)
def test_markdown_table_shortcodes_render_outside_paragraphs(
    tmp_path: Path, view: bool, shortcode: str, template: str
) -> None:
    import markdown

    (tmp_path / "rows.yaml").write_text("- title: Example\n")
    source = template.replace("OPTIONS", 'view="works"' if view else "")
    content = MagicMock()
    content._content = markdown.markdown(
        f"Before\n\n{source}\n\nAfter",
        extensions=[_mod._ShortcodePreserveExtension()],
    )
    settings = _mod._resolve_settings(
        {"TABULAR_SHORTCODE": shortcode, "TABULAR_VIEWS": {"works": {}}}
    )
    _mod._process_content(content, settings, tmp_path, {})
    result = content._content
    assert result.startswith("<p>Before</p>\n")
    assert "<p>After</p>" in result
    assert not re.search(r"<p>\s*<(?:section|div|table)\b", result)
    assert not re.search(r"</(?:section|div|table)>\s*</p>", result)
    assert "Example" in result
    assert "{%" not in result


def test_shortcode_paragraph_cleanup_preserves_surrounding_content(
    tmp_path: Path,
) -> None:
    (tmp_path / "rows.yaml").write_text("- title: Example\n")
    content = MagicMock()
    content._content = (
        '<p><em>Before</em></p>\n<p>{% table rows.yaml view="works" %}\n'
        "{% table rows.yaml %}</p>\n<p>{% other rows.yaml %}</p>"
        "<p>After</p>"
    )
    _mod._process_content(
        content,
        _mod._resolve_settings({"TABULAR_VIEWS": {"works": {}}}),
        tmp_path,
        {},
    )
    assert "<p><section" not in content._content
    assert "</div></p>" not in content._content
    assert "<p><em>Before</em></p>" in content._content
    assert "<p>{% other rows.yaml %}</p><p>After</p>" in content._content


# ---------------------------------------------------------------------------
# _ShortcodePreprocessor.run — shortcodes are stashed
# ---------------------------------------------------------------------------


def test_preprocessor_stashes_shortcode() -> None:
    """{% table ... %} shortcode should be replaced with an htmlStash placeholder."""
    import markdown

    md = markdown.Markdown()
    preprocessor = _mod._ShortcodePreprocessor(md)
    lines = ["before", "{% table data/books.yaml %}", "after"]
    result = preprocessor.run(lines)

    joined = "\n".join(result)
    # Original shortcode should NOT appear verbatim anymore.
    assert "{% table" not in joined
    # An htmlStash placeholder (STX digit ETX pattern) should have been inserted.
    assert "\x02" in joined  # STX is the stash sentinel character


def test_preprocessor_leaves_non_shortcode_lines_untouched() -> None:
    """Lines without a shortcode should pass through unchanged."""
    import markdown

    md = markdown.Markdown()
    preprocessor = _mod._ShortcodePreprocessor(md)
    lines = ["# heading", "Some paragraph text.", "- list item"]
    result = preprocessor.run(lines)

    assert result == lines


def test_preprocessor_stashes_dash_variant() -> None:
    """{%- table ... -%} (dash-trimmed) should also be stashed."""
    import markdown

    md = markdown.Markdown()
    preprocessor = _mod._ShortcodePreprocessor(md)
    lines = ["{%- table data/books.yaml -%}"]
    result = preprocessor.run(lines)
    joined = "\n".join(result)

    assert "{%- table" not in joined
    assert "\x02" in joined


# ---------------------------------------------------------------------------
# _register_markdown_extension — added once, not duplicated
# ---------------------------------------------------------------------------


def test_register_markdown_extension_adds_extension() -> None:
    """_register_markdown_extension should add the extension to MARKDOWN settings."""
    from unittest.mock import MagicMock

    pelican = MagicMock()
    pelican.settings = {}

    _mod._register_markdown_extension(pelican)

    extensions = pelican.settings["MARKDOWN"]["extensions"]
    assert len(extensions) == 1
    assert isinstance(extensions[0], _mod._ShortcodePreserveExtension)


def test_register_markdown_extension_not_duplicated() -> None:
    """Calling _register_markdown_extension twice should not add a second copy."""
    from unittest.mock import MagicMock

    pelican = MagicMock()
    pelican.settings = {}

    _mod._register_markdown_extension(pelican)
    _mod._register_markdown_extension(pelican)

    extensions = pelican.settings["MARKDOWN"]["extensions"]
    # Only one instance, no duplicates.
    instances = [
        e for e in extensions if isinstance(e, _mod._ShortcodePreserveExtension)
    ]
    assert len(instances) == 1

"""Tests for the Markdown shortcode preprocessor and extension registration."""

from __future__ import annotations

import pytest

import pelican.plugins.tabular.tabular as _mod

_HAS_MARKDOWN = _mod._HAS_MARKDOWN

pytestmark = pytest.mark.skipif(not _HAS_MARKDOWN, reason="markdown not installed")


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

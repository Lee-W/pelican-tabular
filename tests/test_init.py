"""Tests for _init and _process_article plugin lifecycle hooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pelican.plugins.tabular.tabular as _mod
from pelican.plugins.tabular.tabular import _init, _process_article

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_pelican(settings: dict[str, Any]) -> MagicMock:
    pel = MagicMock()
    pel.settings = settings
    return pel


# ---------------------------------------------------------------------------
# _init — PATH / TABULAR_DATA_ROOT resolution
# ---------------------------------------------------------------------------


def test_init_data_root_defaults_to_content_path(tmp_path: Path) -> None:
    """Without TABULAR_DATA_ROOT, _data_root should equal _content_path."""
    content = tmp_path / "content"
    content.mkdir()
    pel = _make_pelican({"PATH": str(content)})

    with patch.object(_mod, "_register_markdown_extension"):
        _init(pel)

    assert _mod._data_root == content
    assert _mod._content_path == content
    assert _mod._data_root == _mod._content_path


def test_init_data_root_uses_tabular_setting(tmp_path: Path) -> None:
    """With TABULAR_DATA_ROOT set, _data_root should use that value."""
    content = tmp_path / "content"
    data = tmp_path / "data"
    content.mkdir()
    data.mkdir()
    pel = _make_pelican({"PATH": str(content), "TABULAR_DATA_ROOT": str(data)})

    with patch.object(_mod, "_register_markdown_extension"):
        _init(pel)

    assert _mod._data_root == data
    assert _mod._content_path == content
    assert _mod._data_root != _mod._content_path


def test_init_resets_article_url_map(tmp_path: Path) -> None:
    """_init should always reset _article_url_map to an empty dict."""
    content = tmp_path / "content"
    content.mkdir()
    _mod._article_url_map = {"stale": "http://example.com/stale"}
    pel = _make_pelican({"PATH": str(content)})

    with patch.object(_mod, "_register_markdown_extension"):
        _init(pel)

    assert _mod._article_url_map == {}


# ---------------------------------------------------------------------------
# _process_article — early return and URL map writes
# ---------------------------------------------------------------------------


def test_process_article_early_return_when_settings_none() -> None:
    """If _settings is None, _process_article should return without side effects."""
    _mod._settings = None
    _mod._data_root = None
    _mod._content_path = None
    _mod._article_url_map = {}

    content = MagicMock()
    content.source_path = "/some/path.md"
    content.url = "some/path/"

    _process_article(content)

    assert _mod._article_url_map == {}


def test_process_article_writes_url_map(tmp_path: Path) -> None:
    """source_path + url both set: _article_url_map should get the abs URL."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _mod._settings = {
        "shortcode": "table",
        "fields": [],
        "field_labels": {},
        "count_template": "{n} rows",
        "group_count_template": "{n} rows",
        "siteurl": "https://example.com",
    }
    _mod._data_root = data_dir
    _mod._content_path = content_dir
    _mod._article_url_map = {}

    src = str(content_dir / "posts" / "hello.md")
    content = MagicMock()
    content.source_path = src
    content.url = "posts/hello/"
    content._content = ""  # no shortcode, skip rendering

    _process_article(content)

    assert _mod._article_url_map[src] == "https://example.com/posts/hello/"
    # relative key should also be written
    assert _mod._article_url_map["posts/hello.md"] == "https://example.com/posts/hello/"


def test_process_article_no_source_path_skips_url_map(tmp_path: Path) -> None:
    """If source_path or url is missing/falsy, url map should not be updated."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _mod._settings = {
        "shortcode": "table",
        "fields": [],
        "field_labels": {},
        "count_template": "{n} rows",
        "group_count_template": "{n} rows",
        "siteurl": "https://example.com",
    }
    _mod._data_root = data_dir
    _mod._content_path = content_dir
    _mod._article_url_map = {}

    content = MagicMock()
    content.source_path = None
    content.url = "posts/hello/"
    content._content = ""

    _process_article(content)

    assert _mod._article_url_map == {}

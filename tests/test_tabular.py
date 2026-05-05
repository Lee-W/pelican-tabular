"""Tests for pelican-tabular plugin."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from pelican.plugins.tabular.tabular import (
    _detect_columns,
    _load_data_file,
    _make_pattern,
    _parse_shortcode_args,
    _process_content,
    _render_table_html,
    _replace_match,
    _resolve_settings,
)

# ---------------------------------------------------------------------------
# _parse_shortcode_args
# ---------------------------------------------------------------------------


def test_parse_args_file_only() -> None:
    path, kwargs = _parse_shortcode_args("data/books.yaml")
    assert path == "data/books.yaml"
    assert kwargs == {}


def test_parse_args_with_kwargs() -> None:
    path, kwargs = _parse_shortcode_args('data/books.yaml sort_by="rating" sort_order="desc"')
    assert path == "data/books.yaml"
    assert kwargs == {"sort_by": "rating", "sort_order": "desc"}


def test_parse_args_empty_raises() -> None:
    with pytest.raises(ValueError):
        _parse_shortcode_args("")


def test_parse_args_hidden_fields() -> None:
    path, kwargs = _parse_shortcode_args('data/books.yaml hidden="year,difficulty"')
    assert kwargs["hidden"] == "year,difficulty"


# ---------------------------------------------------------------------------
# _load_data_file
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    {"title": "Book A", "rating": 9, "year": 2020},
    {"title": "Book B", "rating": 7, "year": 2021},
]


def test_load_yaml(tmp_path: Path) -> None:
    f = tmp_path / "books.yaml"
    f.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")
    rows = _load_data_file(f)
    assert rows == SAMPLE_ROWS


def test_load_json(tmp_path: Path) -> None:
    import json

    f = tmp_path / "books.json"
    f.write_text(json.dumps(SAMPLE_ROWS), encoding="utf-8")
    rows = _load_data_file(f)
    assert rows == SAMPLE_ROWS


def test_load_csv(tmp_path: Path) -> None:
    f = tmp_path / "books.csv"
    f.write_text("title,rating,year\nBook A,9,2020\nBook B,7,2021", encoding="utf-8")
    rows = _load_data_file(f)
    assert rows[0]["title"] == "Book A"
    assert rows[1]["year"] == "2021"  # CSV values are always strings


def test_load_unsupported_format(tmp_path: Path) -> None:
    f = tmp_path / "books.toml"
    f.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        _load_data_file(f)


def test_load_non_list_raises(tmp_path: Path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text(yaml.dump({"key": "value"}), encoding="utf-8")
    with pytest.raises(TypeError, match="Expected a list"):
        _load_data_file(f)


# ---------------------------------------------------------------------------
# _detect_columns
# ---------------------------------------------------------------------------


def test_detect_columns_preserves_order() -> None:
    rows = [{"b": 1, "a": 2}, {"c": 3, "b": 4}]
    assert _detect_columns(rows) == ["b", "a", "c"]


def test_detect_columns_empty() -> None:
    assert _detect_columns([]) == []


# ---------------------------------------------------------------------------
# _render_table_html
# ---------------------------------------------------------------------------


def test_render_basic() -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
    )
    assert "<table" in html
    assert "<th>title</th>" in html
    assert "<td>Book A</td>" in html


def test_render_sort_desc() -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by="rating",
        sort_order="desc",
    )
    assert html.index("Book A") < html.index("Book B")


def test_render_sort_asc() -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by="rating",
        sort_order="asc",
    )
    assert html.index("Book B") < html.index("Book A")


def test_render_hidden_field() -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=[],
        field_labels={},
        hidden={"year"},
        sort_by=None,
        sort_order="asc",
    )
    assert "<th>year</th>" not in html
    assert "<th>title</th>" in html


def test_render_field_labels() -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=[],
        field_labels={"rating": "Score"},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
    )
    assert "<th>Score</th>" in html
    assert "<th>rating</th>" not in html


def test_render_explicit_fields_ordering() -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=["year", "title"],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
    )
    assert html.index("<th>year</th>") < html.index("<th>title</th>")
    assert "<th>rating</th>" not in html


def test_render_list_cell_value() -> None:
    rows = [{"tags": ["sci-fi", "classic"]}]
    html = _render_table_html(
        rows,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
    )
    assert "sci-fi, classic" in html


# ---------------------------------------------------------------------------
# _process_content (integration)
# ---------------------------------------------------------------------------


class _FakeContent:
    def __init__(self, text: str) -> None:
        self._content = text


def test_process_content_replaces_shortcode(tmp_path: Path) -> None:
    data_file = tmp_path / "books.yaml"
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _resolve_settings(
        {"TABULAR_DATA_ROOT": str(tmp_path), "PATH": str(tmp_path)}
    )
    content = _FakeContent(f'{{% table books.yaml %}}')

    _process_content(content, settings, tmp_path)  # type: ignore[arg-type]
    assert "<table" in content._content
    assert "<td>Book A</td>" in content._content


def test_process_content_missing_file(tmp_path: Path) -> None:
    settings = _resolve_settings({"TABULAR_DATA_ROOT": str(tmp_path), "PATH": str(tmp_path)})
    content = _FakeContent("{% table missing.yaml %}")

    _process_content(content, settings, tmp_path)  # type: ignore[arg-type]
    assert "tabular-error" in content._content


def test_process_content_no_shortcode(tmp_path: Path) -> None:
    settings = _resolve_settings({})
    content = _FakeContent("<p>No shortcode here.</p>")

    _process_content(content, settings, tmp_path)  # type: ignore[arg-type]
    assert content._content == "<p>No shortcode here.</p>"


# ---------------------------------------------------------------------------
# shortcode pattern
# ---------------------------------------------------------------------------


def test_pattern_matches_standard() -> None:
    pattern = _make_pattern("table")
    m = pattern.search("{% table data/books.yaml %}")
    assert m is not None
    assert m.group(1).strip() == "data/books.yaml"


def test_pattern_matches_with_dash() -> None:
    pattern = _make_pattern("table")
    m = pattern.search("{%- table data/books.yaml -%}")
    assert m is not None


def test_pattern_captures_kwargs() -> None:
    pattern = _make_pattern("table")
    m = pattern.search('{% table data/books.yaml sort_by="rating" %}')
    assert m is not None
    assert 'sort_by="rating"' in m.group(1)

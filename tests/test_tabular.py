"""Tests for pelican-tabular plugin."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from pytest_regressions.file_regression import FileRegressionFixture

from pelican.plugins.tabular.tabular import (
    BUILTIN_COUNT_TEMPLATES,
    BUILTIN_GROUP_COUNT_TEMPLATES,
    DEFAULT_COUNT_TEMPLATE,
    DEFAULT_GROUP_COUNT_TEMPLATE,
    DEFAULT_REF_HREF_TEMPLATE,
    DEFAULT_REF_ROOTS,
    DEFAULT_REF_SUFFIX,
    DEFAULT_REF_TEXT_FIELD,
    RefRenderContext,
    TabularRefError,
    _aggregate_field,
    _build_global_ref_index,
    _cell_value,
    _collapse_rows,
    _detect_columns,
    _extract_year,
    _extract_years,
    _field_transform,
    _field_value,
    _find_ref_item,
    _format_ref_href,
    _format_scalar,
    _get_global_ref_index,
    _get_nested,
    _group_key_value,
    _load_data_file,
    _load_ref_file,
    _make_pattern,
    _parse_aggregate_kwarg,
    _parse_csv_kwarg,
    _parse_shortcode_args,
    _process_content,
    _render_table_html,
    _resolve_count_template,
    _resolve_filename_url,
    _resolve_global_ref,
    _resolve_group_count_template,
    _resolve_path_ref,
    _resolve_ref_href,
    _resolve_ref_rows,
    _resolve_ref_value,
    _resolve_rows,
    _resolve_settings,
    _resolve_value,
    _slugify,
    _split_ref_href_templates,
    _template_fields,
    _template_is_applicable,
)

EMPTY_REF_CTX = RefRenderContext(
    frozenset(), DEFAULT_REF_TEXT_FIELD, DEFAULT_REF_HREF_TEMPLATE
)

# ---------------------------------------------------------------------------
# _parse_shortcode_args
# ---------------------------------------------------------------------------


def test_parse_args_file_only() -> None:
    path, kwargs = _parse_shortcode_args("data/books.yaml")
    assert path == "data/books.yaml"
    assert kwargs == {}


def test_parse_args_with_kwargs() -> None:
    path, kwargs = _parse_shortcode_args(
        'data/books.yaml sort_by="rating" sort_order="desc"'
    )
    assert path == "data/books.yaml"
    assert kwargs == {"sort_by": "rating", "sort_order": "desc"}


def test_parse_args_empty_raises() -> None:
    with pytest.raises(ValueError):
        _parse_shortcode_args("")


def test_parse_args_hidden_fields() -> None:
    _path, kwargs = _parse_shortcode_args('data/books.yaml hidden="year,difficulty"')
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
    assert _load_data_file(f) == SAMPLE_ROWS


def test_load_json(tmp_path: Path) -> None:
    import json

    f = tmp_path / "books.json"
    f.write_text(json.dumps(SAMPLE_ROWS), encoding="utf-8")
    assert _load_data_file(f) == SAMPLE_ROWS


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
# _resolve_filename_url
# ---------------------------------------------------------------------------

URL_MAP = {"posts/review/2024/foo.md": "https://example.com/posts/review/2024/foo/"}


def test_resolve_filename_url_plain() -> None:
    assert (
        _resolve_filename_url("{filename}posts/review/2024/foo.md", URL_MAP)
        == "https://example.com/posts/review/2024/foo/"
    )


def test_resolve_filename_url_with_fragment() -> None:
    url = _resolve_filename_url("{filename}posts/review/2024/foo.md#section", URL_MAP)
    assert url == "https://example.com/posts/review/2024/foo/#section"


def test_resolve_filename_url_leading_slash() -> None:
    url = _resolve_filename_url("{filename}/posts/review/2024/foo.md", URL_MAP)
    assert url == "https://example.com/posts/review/2024/foo/"


def test_resolve_filename_url_passthrough() -> None:
    assert (
        _resolve_filename_url("https://example.com", URL_MAP) == "https://example.com"
    )


def test_resolve_filename_url_unknown_warns(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        result = _resolve_filename_url("{filename}unknown.md", URL_MAP)
    assert result == "{filename}unknown.md"
    assert "could not resolve" in caplog.text


# ---------------------------------------------------------------------------
# _resolve_value / _resolve_rows
# ---------------------------------------------------------------------------


def test_resolve_value_string() -> None:
    assert (
        _resolve_value("{filename}posts/review/2024/foo.md", URL_MAP)
        == "https://example.com/posts/review/2024/foo/"
    )


def test_resolve_value_plain_string_passthrough() -> None:
    assert _resolve_value("hello", URL_MAP) == "hello"


def test_resolve_value_dict() -> None:
    val = {"text": "review", "href": "{filename}posts/review/2024/foo.md"}
    result = _resolve_value(val, URL_MAP)
    assert result["href"] == "https://example.com/posts/review/2024/foo/"
    assert result["text"] == "review"


def test_resolve_value_list() -> None:
    val = ["{filename}posts/review/2024/foo.md", "https://other.com"]
    result = _resolve_value(val, URL_MAP)
    assert result[0] == "https://example.com/posts/review/2024/foo/"
    assert result[1] == "https://other.com"


def test_resolve_rows() -> None:
    rows = [{"url": "{filename}posts/review/2024/foo.md", "title": "Foo"}]
    result = _resolve_rows(rows, URL_MAP)
    assert result[0]["url"] == "https://example.com/posts/review/2024/foo/"
    assert result[0]["title"] == "Foo"


# ---------------------------------------------------------------------------
# _cell_value
# ---------------------------------------------------------------------------


def test_cell_value_none() -> None:
    assert _cell_value(None) == ""


def test_cell_value_string() -> None:
    assert _cell_value("hello") == "hello"


def test_cell_value_number() -> None:
    assert _cell_value(9.5) == "9.5"


def test_cell_value_date() -> None:
    assert _cell_value(datetime.date(2024, 1, 15)) == "2024-01-15"


def test_cell_value_link_dict() -> None:
    html = _cell_value({"text": "review", "href": "https://example.com"})
    assert html == '<a href="https://example.com">review</a>'


def test_cell_value_link_dict_url_alias() -> None:
    html = _cell_value({"text": "review", "url": "https://example.com"})
    assert html == '<a href="https://example.com">review</a>'


def test_cell_value_link_dict_href_as_text_fallback() -> None:
    html = _cell_value({"href": "https://example.com"})
    assert "https://example.com" in html


def test_cell_value_list_of_links() -> None:
    val = [
        {"text": "2020", "href": "https://example.com/2020"},
        {"text": "2024", "href": "https://example.com/2024"},
    ]
    html = _cell_value(val)
    assert "<ul " in html and html.endswith("</ul>")
    assert html.count("<li>") == 2
    assert "2020" in html and "2024" in html


def test_cell_value_list_single_item() -> None:
    val = [{"text": "review", "href": "https://example.com"}]
    html = _cell_value(val)
    assert html == '<a href="https://example.com">review</a>'


def test_cell_value_list_of_strings() -> None:
    html = _cell_value(["a", "b", "c"])
    assert "<ul " in html
    assert "<li>a</li><li>b</li><li>c</li>" in html


def test_cell_value_list_single_string() -> None:
    assert _cell_value(["only"]) == "only"


# ---------------------------------------------------------------------------
# _format_scalar / _slugify / _extract_year / _extract_years
# ---------------------------------------------------------------------------


def test_format_scalar_date() -> None:
    assert _format_scalar(datetime.date(2024, 3, 1)) == "2024-03-01"


def test_format_scalar_datetime() -> None:
    assert _format_scalar(datetime.datetime(2024, 3, 1, 12, 0)) == "2024-03-01T12:00:00"


def test_format_scalar_string() -> None:
    assert _format_scalar("hello") == "hello"


def test_format_scalar_int() -> None:
    assert _format_scalar(42) == "42"


def test_slugify_ascii() -> None:
    assert _slugify("SSS Tier") == "sss-tier"


def test_slugify_cjk() -> None:
    result = _slugify("神作")
    assert result == "神作"


def test_slugify_empty() -> None:
    assert _slugify("!!!") == "group"


def test_extract_year_int() -> None:
    assert _extract_year(2024) == 2024


def test_extract_year_string() -> None:
    assert _extract_year("2024-01-15") == 2024


def test_extract_year_date() -> None:
    assert _extract_year(datetime.date(2024, 3, 1)) == 2024


def test_extract_year_none_on_bad_int() -> None:
    assert _extract_year(99) is None


def test_extract_years_list() -> None:
    assert _extract_years([2020, 2022, 2024]) == [2020, 2022, 2024]


# ---------------------------------------------------------------------------
# _aggregate_field
# ---------------------------------------------------------------------------


def test_aggregate_field_year() -> None:
    places = [{"year": 2022}, {"year": 2020}, {"year": 2022}]
    result = _aggregate_field("year", "year", places)
    assert result == "2020, 2022"


def test_aggregate_field_unknown_op(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        result = _aggregate_field("median", "count", [{"count": 3}])
    assert result == ""
    assert "unknown aggregate op" in caplog.text


def test_aggregate_field_count() -> None:
    places: list[dict[str, Any]] = [
        {"rating": 9},
        {"rating": None},
        {"rating": 7},
        {},
    ]
    assert _aggregate_field("count", "rating", places) == 2


def test_aggregate_field_sum() -> None:
    places: list[dict[str, Any]] = [
        {"pages": 100},
        {"pages": 250},
        {"pages": None},
    ]
    assert _aggregate_field("sum", "pages", places) == "350"


def test_aggregate_field_avg() -> None:
    places = [{"rating": 9}, {"rating": 7}, {"rating": 8}]
    assert _aggregate_field("avg", "rating", places) == "8"


def test_aggregate_field_avg_rounds() -> None:
    places = [{"rating": 9}, {"rating": 8}, {"rating": 8}]
    assert _aggregate_field("avg", "rating", places) == "8.33"


def test_aggregate_field_min_max() -> None:
    places: list[dict[str, Any]] = [
        {"rating": 9},
        {"rating": 7},
        {"rating": "8.5"},
    ]
    assert _aggregate_field("min", "rating", places) == "7"
    assert _aggregate_field("max", "rating", places) == "9"


def test_aggregate_field_numeric_ops_ignore_non_numeric() -> None:
    places: list[dict[str, Any]] = [{"rating": "n/a"}, {"rating": None}]
    assert _aggregate_field("sum", "rating", places) == ""
    assert _aggregate_field("avg", "rating", places) == ""


# ---------------------------------------------------------------------------
# _parse_csv_kwarg / _parse_aggregate_kwarg
# ---------------------------------------------------------------------------


def test_parse_csv_kwarg() -> None:
    assert _parse_csv_kwarg("tier,category") == ["tier", "category"]


def test_parse_csv_kwarg_empty() -> None:
    assert _parse_csv_kwarg("") == []


def test_parse_aggregate_kwarg() -> None:
    assert _parse_aggregate_kwarg("year:year,visits:sum") == {
        "year": "year",
        "visits": "sum",
    }


def test_parse_aggregate_kwarg_no_colon_skipped() -> None:
    assert _parse_aggregate_kwarg("badtoken") == {}


# ---------------------------------------------------------------------------
# _collapse_rows
# ---------------------------------------------------------------------------

TIERED_ROWS = [
    {"title": "A", "tier": "SSS", "rating": 10},
    {"title": "B", "tier": "SS", "rating": 9},
    {"title": "C", "tier": "SSS", "rating": 8},
]


def test_collapse_rows_no_aggregate_preserves_rows() -> None:
    result = _collapse_rows(TIERED_ROWS, ["tier"], {}, EMPTY_REF_CTX)
    titles = [r["title"] for r in result]
    assert titles == ["A", "C", "B"]  # SSS rows grouped first, then SS


def test_collapse_rows_no_aggregate_adds_places() -> None:
    result = _collapse_rows(TIERED_ROWS, ["tier"], {}, EMPTY_REF_CTX)
    for row in result:
        assert "_places" in row
        assert len(row["_places"]) == 1


def test_collapse_rows_aggregate_merges() -> None:
    rows = [
        {"anime": "X", "tier": "SSS", "year": 2020},
        {"anime": "X", "tier": "SSS", "year": 2022},
    ]
    result = _collapse_rows(rows, ["anime"], {"year": "year"}, EMPTY_REF_CTX)
    assert len(result) == 1
    assert result[0]["year"] == "2020, 2022"
    assert len(result[0]["_places"]) == 2


def test_collapse_rows_aggregate_first_nonblank_wins() -> None:
    rows = [
        {"anime": "X", "tier": "SSS", "note": ""},
        {"anime": "X", "tier": "SSS", "note": "great"},
    ]
    result = _collapse_rows(rows, ["anime"], {"year": "year"}, EMPTY_REF_CTX)
    assert result[0]["note"] == "great"


# ---------------------------------------------------------------------------
# _detect_columns
# ---------------------------------------------------------------------------


def test_detect_columns_preserves_order() -> None:
    rows = [{"b": 1, "a": 2}, {"c": 3, "b": 4}]
    assert _detect_columns(rows) == ["b", "a", "c"]


def test_detect_columns_empty() -> None:
    assert _detect_columns([]) == []


def test_detect_columns_skips_reserved() -> None:
    rows = [{"title": "A", "_places": [{}]}]
    assert _detect_columns(rows) == ["title"]


# ---------------------------------------------------------------------------
# _resolve_count_template / _resolve_group_count_template
# ---------------------------------------------------------------------------


def test_count_template_explicit_override() -> None:
    assert (
        _resolve_count_template({"TABULAR_COUNT_TEMPLATE": "共 {n} 筆"}) == "共 {n} 筆"
    )


def test_count_template_builtin_zh() -> None:
    assert (
        _resolve_count_template({"DEFAULT_LANG": "zh"}) == BUILTIN_COUNT_TEMPLATES["zh"]
    )


def test_count_template_builtin_zh_tw() -> None:
    assert (
        _resolve_count_template({"DEFAULT_LANG": "zh-TW"})
        == BUILTIN_COUNT_TEMPLATES["zh"]
    )


def test_count_template_builtin_ja() -> None:
    assert (
        _resolve_count_template({"DEFAULT_LANG": "ja"}) == BUILTIN_COUNT_TEMPLATES["ja"]
    )


def test_count_template_fallback_english() -> None:
    assert _resolve_count_template({"DEFAULT_LANG": "en"}) == DEFAULT_COUNT_TEMPLATE


def test_count_template_no_lang() -> None:
    assert _resolve_count_template({}) == DEFAULT_COUNT_TEMPLATE


def test_group_count_template_explicit() -> None:
    assert (
        _resolve_group_count_template({"TABULAR_GROUP_COUNT_TEMPLATE": "共 {n} 筆"})
        == "共 {n} 筆"
    )


def test_group_count_template_zh() -> None:
    assert (
        _resolve_group_count_template({"DEFAULT_LANG": "zh"})
        == BUILTIN_GROUP_COUNT_TEMPLATES["zh"]
    )


def test_group_count_template_zh_tw() -> None:
    assert (
        _resolve_group_count_template({"DEFAULT_LANG": "zh-TW"})
        == BUILTIN_GROUP_COUNT_TEMPLATES["zh"]
    )


def test_group_count_template_fallback() -> None:
    assert (
        _resolve_group_count_template({"DEFAULT_LANG": "en"})
        == DEFAULT_GROUP_COUNT_TEMPLATE
    )


# ---------------------------------------------------------------------------
# _render_table_html
# ---------------------------------------------------------------------------


def _render(**kwargs: Any) -> str:
    defaults: dict[str, Any] = {
        "fields": [],
        "field_labels": {},
        "hidden": set(),
        "sort_by": None,
        "sort_order": "asc",
        "count_template": DEFAULT_COUNT_TEMPLATE,
        "group_by": [],
        "group_summary_at": [],
        "aggregate": {},
        "group_count_template": DEFAULT_GROUP_COUNT_TEMPLATE,
    }
    defaults.update(kwargs)
    return _render_table_html(SAMPLE_ROWS, **defaults)


def test_render_uses_osm_place_list_classes() -> None:
    html = _render(count_template="{n} rows")
    assert 'class="osm-place-list-wrapper"' in html
    assert 'class="osm-place-list"' in html
    assert 'class="osm-place-list-count"' in html
    assert "2 rows" in html


def test_render_basic() -> None:
    html = _render()
    assert ">title</th>" in html
    assert "<td>Book A</td>" in html


def test_render_sort_desc() -> None:
    html = _render(sort_by="rating", sort_order="desc")
    assert html.index("Book A") < html.index("Book B")


def test_render_sort_asc() -> None:
    html = _render(sort_by="rating", sort_order="asc")
    assert html.index("Book B") < html.index("Book A")


def test_render_sort_mixed_types_does_not_raise() -> None:
    rows: list[dict[str, Any]] = [
        {"title": "Int", "rank": 5},
        {"title": "Str", "rank": "abc"},
        {"title": "None", "rank": None},
    ]
    html = _render_table_html(
        rows,
        fields=["title", "rank"],
        field_labels={},
        hidden=set(),
        sort_by="rank",
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=[],
        group_summary_at=[],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
    )
    # numbers sort before dates/strings; None falls back into the string
    # bucket as ""
    assert html.index("Int") < html.index("None") < html.index("Str")


def test_render_hidden_field() -> None:
    html = _render(hidden={"year"})
    assert "<th>year</th>" not in html
    assert ">title</th>" in html


def test_render_field_labels() -> None:
    html = _render(field_labels={"rating": "Score"})
    assert ">Score</th>" in html
    assert "<th>rating</th>" not in html


def test_render_explicit_fields_ordering() -> None:
    html = _render(fields=["year", "title"])
    assert html.index(">year</th>") < html.index(">title</th>")
    assert "<th>rating</th>" not in html


def test_render_link_in_cell() -> None:
    rows = [{"title": "Foo", "review": {"text": "read", "href": "https://example.com"}}]
    html = _render_table_html(
        rows,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=[],
        group_summary_at=[],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
    )
    assert '<a href="https://example.com">read</a>' in html


def test_render_group_by_reorders_rows() -> None:
    html = _render_table_html(
        TIERED_ROWS,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=["tier"],
        group_summary_at=[],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
    )
    # A and C (SSS) should appear before B (SS)
    assert html.index(">A<") < html.index(">C<") < html.index(">B<")


def test_render_group_summary_at_emits_header_rows() -> None:
    html = _render_table_html(
        TIERED_ROWS,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=["tier"],
        group_summary_at=["tier"],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
    )
    assert 'class="osm-group-header' in html
    assert "<strong" in html
    assert "SSS" in html
    assert "SS" in html
    # tier column should not appear in table headers since it's in summary_set
    assert "<th>tier</th>" not in html


def test_render_group_summary_count() -> None:
    html = _render_table_html(
        TIERED_ROWS,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=["tier"],
        group_summary_at=["tier"],
        aggregate={},
        group_count_template="{n} rows",
    )
    assert "2 rows" in html  # SSS has 2 items
    assert "1 rows" in html  # SS has 1 item


def test_render_aggregate_collapses_rows() -> None:
    rows = [
        {"anime": "X", "tier": "SSS", "year": 2020},
        {"anime": "X", "tier": "SSS", "year": 2022},
        {"anime": "Y", "tier": "SS", "year": 2021},
    ]
    html = _render_table_html(
        rows,
        fields=[],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=["anime"],
        group_summary_at=[],
        aggregate={"year": "year"},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
    )
    assert "2020, 2022" in html
    assert html.count("<tr>") == 3  # thead row + 2 collapsed data rows (X and Y)


def test_render_group_summary_without_group_by_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        _render(group_by=[], group_summary_at=["tier"])
    assert "group_summary_at requires group_by" in caplog.text


def test_render_group_summary_not_prefix_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        _render_table_html(
            TIERED_ROWS,
            fields=[],
            field_labels={},
            hidden=set(),
            sort_by=None,
            sort_order="asc",
            count_template=DEFAULT_COUNT_TEMPLATE,
            group_by=["tier"],
            group_summary_at=["rating"],  # not a prefix of group_by
            aggregate={},
            group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
        )
    assert "must be a prefix of group_by" in caplog.text


# ---------------------------------------------------------------------------
# _process_content (integration)
# ---------------------------------------------------------------------------


class _FakeContent:
    def __init__(self, text: str) -> None:
        self._content = text


def _make_settings(**overrides: Any) -> dict[str, Any]:
    return _resolve_settings(overrides)


def test_process_content_replaces_shortcode(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "books.yaml"
    data_file.parent.mkdir()
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent("{% table data/books.yaml %}")
    _process_content(content, settings, tmp_path, {})
    assert "osm-place-list" in content._content
    assert "<td>Book A</td>" in content._content


def test_process_content_resolves_filename(tmp_path: Path) -> None:
    rows = [{"title": "Foo", "url": "{filename}posts/foo.md"}]
    data_file = tmp_path / "items.yaml"
    data_file.write_text(yaml.dump(rows), encoding="utf-8")

    url_map = {"posts/foo.md": "https://example.com/posts/foo/"}
    settings = _make_settings()
    content = _FakeContent("{% table items.yaml %}")
    _process_content(content, settings, tmp_path, url_map)
    assert "https://example.com/posts/foo/" in content._content


def test_process_content_group_by(tmp_path: Path) -> None:
    data_file = tmp_path / "tiered.yaml"
    data_file.write_text(yaml.dump(TIERED_ROWS), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent(
        '{% table tiered.yaml group_by="tier" group_summary_at="tier" %}'
    )
    _process_content(content, settings, tmp_path, {})
    assert "osm-group-header" in content._content
    assert "SSS" in content._content


def test_process_content_per_shortcode_field_labels(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "books.yaml"
    data_file.parent.mkdir()
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _make_settings(TABULAR_FIELD_LABELS={"title": "書名"})
    content = _FakeContent('{% table data/books.yaml field_labels="title:作品" %}')
    _process_content(content, settings, tmp_path, {})
    assert ">作品</th>" in content._content
    assert "<th>書名</th>" not in content._content


def test_process_content_per_shortcode_field_labels_merge(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "books.yaml"
    data_file.parent.mkdir()
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _make_settings(TABULAR_FIELD_LABELS={"rating": "評分"})
    content = _FakeContent('{% table data/books.yaml field_labels="title:作品" %}')
    _process_content(content, settings, tmp_path, {})
    assert ">作品</th>" in content._content
    assert ">評分</th>" in content._content


def test_process_content_missing_file(tmp_path: Path) -> None:
    settings = _make_settings()
    content = _FakeContent("{% table missing.yaml %}")
    _process_content(content, settings, tmp_path, {})
    assert "tabular-error" in content._content


def test_process_content_no_shortcode(tmp_path: Path) -> None:
    settings = _make_settings()
    content = _FakeContent("<p>No shortcode here.</p>")
    _process_content(content, settings, tmp_path, {})
    assert content._content == "<p>No shortcode here.</p>"


def test_process_content_empty_content(tmp_path: Path) -> None:
    settings = _make_settings()
    content = _FakeContent("")
    _process_content(content, settings, tmp_path, {})
    assert content._content == ""


def test_render_table_html_regression(file_regression: FileRegressionFixture) -> None:
    html = _render_table_html(
        SAMPLE_ROWS,
        fields=[],
        field_labels={"title": "Title", "rating": "Rating", "year": "Year"},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=[],
        group_summary_at=[],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
    )
    file_regression.check(html, extension=".html")


# ---------------------------------------------------------------------------
# shortcode pattern
# ---------------------------------------------------------------------------


def test_pattern_matches_standard() -> None:
    pattern = _make_pattern("table")
    m = pattern.search("{% table data/books.yaml %}")
    assert m is not None
    assert m.group(1).strip() == "data/books.yaml"


def test_pattern_matches_with_dash() -> None:
    _make_pattern("table")
    assert _make_pattern("table").search("{%- table data/books.yaml -%}") is not None


def test_pattern_captures_kwargs() -> None:
    pattern = _make_pattern("table")
    m = pattern.search('{% table data/books.yaml sort_by="rating" %}')
    assert m is not None
    assert 'sort_by="rating"' in m.group(1)


# ---------------------------------------------------------------------------
# date_format (TABULAR_DATE_FORMAT / date_format kwarg)
# ---------------------------------------------------------------------------


def test_format_scalar_date_with_format() -> None:
    assert _format_scalar(datetime.date(2026, 6, 2), "%b %Y") == "Jun 2026"


def test_format_scalar_datetime_with_format() -> None:
    assert (
        _format_scalar(datetime.datetime(2026, 6, 2, 9, 30), "%Y/%m/%d") == "2026/06/02"
    )


def test_format_scalar_format_ignored_for_non_dates() -> None:
    assert _format_scalar("hello", "%b %Y") == "hello"


def test_cell_value_date_format() -> None:
    assert _cell_value(datetime.date(2026, 6, 2), date_format="%b %Y") == "Jun 2026"


def test_render_date_format_applied() -> None:
    rows = [{"title": "Foo", "date": datetime.date(2026, 6, 2)}]
    html = _render_table_html(
        rows,
        fields=["title", "date"],
        field_labels={},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=[],
        group_summary_at=[],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
        date_format="%b %Y",
    )
    assert "<td>Jun 2026</td>" in html
    assert "2026-06-02" not in html


def test_resolve_settings_date_format() -> None:
    assert _resolve_settings({"TABULAR_DATE_FORMAT": "%b %Y"})["date_format"] == "%b %Y"


# ---------------------------------------------------------------------------
# aria_columns (accessible name for icon-only links)
# ---------------------------------------------------------------------------


def test_cell_value_aria_label() -> None:
    value = {"text": "📊", "href": "https://example.com"}
    html = _cell_value(value, aria_label="Slide")
    assert html == '<a href="https://example.com" aria-label="Slide">📊</a>'


def test_cell_value_no_aria_label_by_default() -> None:
    value = {"text": "📊", "href": "https://example.com"}
    assert "aria-label" not in _cell_value(value)


def test_render_aria_columns_adds_label() -> None:
    rows = [{"title": "Foo", "slide": {"text": "📊", "href": "https://example.com"}}]
    html = _render_table_html(
        rows,
        fields=["title", "slide"],
        field_labels={"slide": "Slide"},
        hidden=set(),
        sort_by=None,
        sort_order="asc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=[],
        group_summary_at=[],
        aggregate={},
        group_count_template=DEFAULT_GROUP_COUNT_TEMPLATE,
        aria_columns={"slide"},
    )
    assert 'aria-label="Slide"' in html


def test_render_th_has_scope() -> None:
    html = _render()
    assert 'scope="col"' in html


# ---------------------------------------------------------------------------
# group_by year transform (group_by="date:year")
# ---------------------------------------------------------------------------


def test_field_transform_plain() -> None:
    assert _field_transform("project") == ("project", None)


def test_field_transform_year() -> None:
    assert _field_transform("date:year") == ("date", "year")


# ---------------------------------------------------------------------------
# _get_nested (dotted field-path access)
# ---------------------------------------------------------------------------


def test_get_nested_plain_key() -> None:
    assert _get_nested({"title": "Foo"}, "title") == "Foo"


def test_get_nested_one_level() -> None:
    assert _get_nested({"venue": {"city": "台北"}}, "venue.city") == "台北"


def test_get_nested_two_levels() -> None:
    row = {"venue": {"address": {"city": "台北"}}}
    assert _get_nested(row, "venue.address.city") == "台北"


def test_get_nested_missing_intermediate_returns_none() -> None:
    assert _get_nested({"title": "Foo"}, "venue.city") is None


def test_get_nested_none_intermediate_returns_none() -> None:
    assert _get_nested({"venue": None}, "venue.city") is None


def test_get_nested_non_dict_intermediate_returns_none() -> None:
    assert _get_nested({"venue": "a string"}, "venue.city") is None


def test_get_nested_literal_dotted_key_wins_over_traversal() -> None:
    """An aggregate result stored at a literal ``row["venue.city"]`` key (see
    ``_collapse_rows``) must not be shadowed by nested traversal into a
    same-named but differently-shaped ``venue`` field.
    """
    row = {"venue.city": "literal", "venue": {"city": "nested"}}
    assert _get_nested(row, "venue.city") == "literal"


def test_get_nested_non_dict_root_returns_none() -> None:
    assert _get_nested("not a dict", "venue.city") is None


# ---------------------------------------------------------------------------
# _field_value (dotted paths + :year / :link transforms, ref-aware)
# ---------------------------------------------------------------------------


def test_field_value_plain() -> None:
    assert _field_value({"title": "Foo"}, "title", EMPTY_REF_CTX) == "Foo"


def test_field_value_dotted_path() -> None:
    row = {"venue": {"city": "台北", "name": "Zepp"}}
    assert _field_value(row, "venue.city", EMPTY_REF_CTX) == "台北"


def test_field_value_dotted_path_with_year_transform() -> None:
    """``venue.date:year`` — a dotted path combined with a transform: the
    ``:`` split happens first (``_field_transform``), then the dotted half
    is walked (``_get_nested``); the two never conflict.
    """
    row = {"venue": {"date": datetime.date(2026, 6, 2)}}
    assert _field_value(row, "venue.date:year", EMPTY_REF_CTX) == 2026


def test_field_value_ref_field_no_transform_reduces_to_text() -> None:
    record = {"id": "zepp", "name": "Zepp New Taipei", "lat": 25.0, "lon": 121.0}
    ctx = RefRenderContext(frozenset({"venue"}), "name", DEFAULT_REF_HREF_TEMPLATE)
    assert _field_value({"venue": record}, "venue", ctx) == "Zepp New Taipei"


def test_field_value_ref_field_link_transform_builds_link() -> None:
    record = {"id": "zepp", "name": "Zepp New Taipei", "lat": 25.06, "lon": 121.45}
    ctx = RefRenderContext(frozenset({"venue"}), "name", DEFAULT_REF_HREF_TEMPLATE)
    result = _field_value({"venue": record}, "venue:link", ctx)
    assert result == {
        "text": "Zepp New Taipei",
        "href": "https://www.openstreetmap.org/?mlat=25.06&mlon=121.45#map=17/25.06/121.45",
    }


def test_field_value_nested_ref_field_is_not_reduced() -> None:
    """Only the *bare* ref field name (no further dotting) triggers the
    plain-text reduction — ``venue.city`` is already a scalar leaf, so it
    passes through unchanged.
    """
    record = {"id": "zepp", "name": "Zepp New Taipei", "city": "台北"}
    ctx = RefRenderContext(frozenset({"venue"}), "name", DEFAULT_REF_HREF_TEMPLATE)
    assert _field_value({"venue": record}, "venue.city", ctx) == "台北"


def test_field_value_missing_path_returns_none() -> None:
    assert _field_value({"title": "Foo"}, "venue.city", EMPTY_REF_CTX) is None


def test_group_key_value_year() -> None:
    row = {"date": datetime.date(2026, 6, 2)}
    assert _group_key_value(row, "date:year", EMPTY_REF_CTX) == 2026


def test_group_key_value_plain() -> None:
    assert _group_key_value({"tier": "SSS"}, "tier", EMPTY_REF_CTX) == "SSS"


def test_collapse_rows_group_by_year() -> None:
    rows = [
        {"title": "A", "date": datetime.date(2026, 6, 2)},
        {"title": "B", "date": datetime.date(2025, 1, 1)},
        {"title": "C", "date": datetime.date(2026, 2, 1)},
    ]
    result = _collapse_rows(rows, ["date:year"], {}, EMPTY_REF_CTX)
    titles = [r["title"] for r in result]
    assert titles == ["A", "C", "B"]  # 2026 rows grouped first, then 2025


def test_render_group_by_year_creates_year_header() -> None:
    rows = [
        {"title": "A", "date": datetime.date(2026, 6, 2)},
        {"title": "B", "date": datetime.date(2025, 1, 1)},
    ]
    html = _render_table_html(
        rows,
        fields=["title", "date"],
        field_labels={},
        hidden=set(),
        sort_by="date",
        sort_order="desc",
        count_template=DEFAULT_COUNT_TEMPLATE,
        group_by=["date:year"],
        group_summary_at=["date:year"],
        aggregate={},
        group_count_template="",
    )
    assert "osm-group-header-title" in html
    assert ">2026</strong>" in html
    assert ">2025</strong>" in html
    # date column is independent of the derived year grouping
    assert "<td>2026-06-02</td>" in html


# ---------------------------------------------------------------------------
# _load_ref_file / _find_ref_item / _format_ref_href
# ---------------------------------------------------------------------------


def test_load_ref_file_locations_based(tmp_path: Path) -> None:
    f = tmp_path / "venues.yaml"
    f.write_text(
        yaml.dump(
            {
                "locations": [
                    {
                        "id": "zepp-new-taipei",
                        "name": "Zepp New Taipei",
                        "lat": 25.06,
                        "lon": 121.45,
                    },
                    {
                        "id": "legacy-taipei",
                        "name": "Legacy Taipei",
                        "lat": 25.05,
                        "lon": 121.53,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    cache: dict[Path, list[dict[str, Any]]] = {}
    items = _load_ref_file(f, cache)
    assert [i["id"] for i in items] == ["zepp-new-taipei", "legacy-taipei"]


def test_load_ref_file_top_level_list(tmp_path: Path) -> None:
    f = tmp_path / "venues.yaml"
    f.write_text(
        yaml.dump([{"id": "a", "name": "A", "lat": 1.0, "lon": 2.0}]),
        encoding="utf-8",
    )
    cache: dict[Path, list[dict[str, Any]]] = {}
    items = _load_ref_file(f, cache)
    assert items == [{"id": "a", "name": "A", "lat": 1.0, "lon": 2.0}]


@pytest.mark.parametrize("shape", ["locations", "keyed", "list"])
def test_ref_records_inherit_osm_defaults_and_keep_nested_items(
    tmp_path: Path, shape: str
) -> None:
    defaults = {"country": "Japan", "city": "Tokyo", "tags": ["cinema", "visited"]}
    record = {
        "id": "cinema",
        "name": "Cinema",
        "city": "Kawasaki",
        "tags": ["visited", "IMAX"],
        "items": [{"hall": "Screen 4"}, {"hall": "Screen 5"}],
    }
    data: Any
    if shape == "locations":
        data = {**defaults, "locations": [record]}
    elif shape == "keyed":
        data = {"defaults": defaults, "cinema": record}
    else:
        data = [{"defaults": defaults}, record]
    source = tmp_path / "cinemas.yaml"
    source.write_text(yaml.safe_dump(data), encoding="utf-8")
    before = source.read_text(encoding="utf-8")

    assert _load_ref_file(source, {}) == [
        {**record, "country": "Japan", "tags": ["cinema", "visited", "IMAX"]}
    ]
    assert source.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("global_ref", [False, True])
@pytest.mark.parametrize("ref_id", ["cinema", "Cinema"])
def test_keyed_records_resolve_by_id_or_name(
    tmp_path: Path, global_ref: bool, ref_id: str
) -> None:
    places = tmp_path / "places"
    places.mkdir()
    (places / "cinemas.yml").write_text(
        "cinema:\n  name: Cinema\n  lat: 1.0\n  lon: 2.0\n", encoding="utf-8"
    )
    if global_ref:
        result = _resolve_global_ref(
            ref_id,
            content_path=tmp_path,
            ref_roots=DEFAULT_REF_ROOTS,
            cache={},
            index_cache={},
        )
    else:
        result = _resolve_path_ref(
            f"places/cinemas.yml#{ref_id}", content_path=tmp_path, cache={}
        )
    assert result == {"id": "cinema", "name": "Cinema", "lat": 1.0, "lon": 2.0}


def test_keyed_record_preserves_explicit_id(tmp_path: Path) -> None:
    source = tmp_path / "cinemas.yaml"
    source.write_text("key:\n  id: explicit\n  name: Cinema\n", encoding="utf-8")
    assert _load_ref_file(source, {}) == [{"id": "explicit", "name": "Cinema"}]


@pytest.mark.parametrize("tags", ["custom text", [{"name": "structured tag"}]])
def test_ref_records_keep_generic_tags_without_file_defaults(
    tmp_path: Path, tags: Any
) -> None:
    source = tmp_path / "records.yaml"
    records = [{"id": "record", "tags": tags}]
    source.write_text(yaml.safe_dump(records), encoding="utf-8")
    assert _load_ref_file(source, {}) == records


def test_load_ref_file_malformed_raises(tmp_path: Path) -> None:
    f = tmp_path / "venues.yaml"
    f.write_text("not: [valid, yaml: :", encoding="utf-8")
    cache: dict[Path, list[dict[str, Any]]] = {}
    with pytest.raises(yaml.YAMLError):
        _load_ref_file(f, cache)


def test_load_ref_file_wrong_top_level_shape_raises(tmp_path: Path) -> None:
    f = tmp_path / "venues.yaml"
    f.write_text(yaml.dump("just a string"), encoding="utf-8")
    cache: dict[Path, list[dict[str, Any]]] = {}
    with pytest.raises(TypeError):
        _load_ref_file(f, cache)


def test_load_ref_file_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "venues.yaml"
    f.write_text(yaml.dump([{"id": "a", "name": "A"}]), encoding="utf-8")
    cache: dict[Path, list[dict[str, Any]]] = {}

    calls = {"n": 0}
    original_read_text = Path.read_text

    def counting_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == f:
            calls["n"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    _load_ref_file(f, cache)
    _load_ref_file(f, cache)
    _load_ref_file(f, cache)
    assert calls["n"] == 1


def test_find_ref_item_by_id() -> None:
    items = [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}]
    assert _find_ref_item(items, "b") == {"id": "b", "name": "Beta"}


def test_find_ref_item_falls_back_to_name() -> None:
    items = [{"name": "Alpha"}, {"name": "Beta"}]
    assert _find_ref_item(items, "Beta") == {"name": "Beta"}


def test_find_ref_item_not_found_returns_none() -> None:
    items = [{"id": "a", "name": "Alpha"}]
    assert _find_ref_item(items, "missing") is None


def test_format_ref_href_fills_placeholders() -> None:
    result = _format_ref_href("https://x/{lat}/{lon}", {"lat": 25.06, "lon": 121.45})
    assert result == "https://x/25.06/121.45"


def test_format_ref_href_missing_key_is_empty() -> None:
    result = _format_ref_href("https://x/{lat}/{lon}", {"lat": 25.06})
    assert result == "https://x/25.06/"


# ---------------------------------------------------------------------------
# _resolve_path_ref / _resolve_global_ref / global index / _resolve_ref_value
# / _resolve_ref_rows
# ---------------------------------------------------------------------------


def _write_taiwan_venues(tmp_path: Path) -> Path:
    venues_dir = tmp_path / "places" / "venues"
    venues_dir.mkdir(parents=True)
    f = venues_dir / "taiwan.yaml"
    f.write_text(
        yaml.dump(
            {
                "locations": [
                    {
                        "id": "zepp-new-taipei",
                        "name": "Zepp New Taipei",
                        "lat": 25.059661,
                        "lon": 121.449499,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


ZEPP_RECORD = {
    "id": "zepp-new-taipei",
    "name": "Zepp New Taipei",
    "lat": 25.059661,
    "lon": 121.449499,
}


# --- <path>#<id> form ----------------------------------------------------


def test_resolve_path_ref_normal(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    result = _resolve_path_ref(
        "places/venues/taiwan.yaml#zepp-new-taipei",
        content_path=content_path,
        cache={},
    )
    assert result == ZEPP_RECORD


def test_resolve_path_ref_file_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(TabularRefError, match="not found"):
        _resolve_path_ref(
            "places/venues/missing.yaml#zepp-new-taipei",
            content_path=tmp_path,
            cache={},
        )


def test_resolve_path_ref_id_not_found_raises(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    with pytest.raises(TabularRefError, match="not found"):
        _resolve_path_ref(
            "places/venues/taiwan.yaml#no-such-id",
            content_path=content_path,
            cache={},
        )


def test_resolve_path_ref_malformed_yaml_raises(tmp_path: Path) -> None:
    venues_dir = tmp_path / "places" / "venues"
    venues_dir.mkdir(parents=True)
    (venues_dir / "taiwan.yaml").write_text("not: [valid, yaml: :", encoding="utf-8")
    with pytest.raises(TabularRefError, match="failed to load"):
        _resolve_path_ref(
            "places/venues/taiwan.yaml#zepp-new-taipei",
            content_path=tmp_path,
            cache={},
        )


# --- bare <id> global form -------------------------------------------------


def test_resolve_global_ref_hits_by_id(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    result = _resolve_global_ref(
        "zepp-new-taipei",
        content_path=content_path,
        ref_roots=DEFAULT_REF_ROOTS,
        cache={},
        index_cache={},
    )
    assert result == ZEPP_RECORD


def test_resolve_global_ref_falls_back_to_name(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    result = _resolve_global_ref(
        "Zepp New Taipei",
        content_path=content_path,
        ref_roots=DEFAULT_REF_ROOTS,
        cache={},
        index_cache={},
    )
    assert result == ZEPP_RECORD


def test_resolve_global_ref_not_found_raises(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    with pytest.raises(TabularRefError, match="not found"):
        _resolve_global_ref(
            "nope",
            content_path=content_path,
            ref_roots=DEFAULT_REF_ROOTS,
            cache={},
            index_cache={},
        )


def test_resolve_global_ref_ambiguous_id_raises_with_all_candidates(
    tmp_path: Path,
) -> None:
    venues_dir = tmp_path / "places" / "venues"
    venues_dir.mkdir(parents=True)
    (venues_dir / "taiwan.yaml").write_text(
        yaml.dump([{"id": "moondog", "name": "Moondog Taipei"}]), encoding="utf-8"
    )
    (venues_dir / "japan.yaml").write_text(
        yaml.dump([{"id": "moondog", "name": "Moondog Osaka"}]), encoding="utf-8"
    )
    with pytest.raises(TabularRefError) as exc_info:
        _resolve_global_ref(
            "moondog",
            content_path=tmp_path,
            ref_roots=DEFAULT_REF_ROOTS,
            cache={},
            index_cache={},
        )
    message = str(exc_info.value)
    assert "ambiguous" in message
    assert str(venues_dir / "taiwan.yaml") in message
    assert str(venues_dir / "japan.yaml") in message


def test_build_global_ref_index_indexes_by_id_and_name(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    by_id, by_name = _build_global_ref_index(content_path, DEFAULT_REF_ROOTS, {})
    assert [item for _, item in by_id["zepp-new-taipei"]] == [ZEPP_RECORD]
    assert [item for _, item in by_name["Zepp New Taipei"]] == [ZEPP_RECORD]


def test_global_ref_discovery_skips_osm_metadata_before_reading(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    places = content_path / "places"
    for name in ("_schema.yaml", "_common.yml", "venues/_private.yaml"):
        (places / name).write_text("not: [valid, yaml: :", encoding="utf-8")
    # Even valid records in a private file are not global reference candidates.
    private = places / "_records.yml"
    private.write_text("- id: private\n  name: Private\n", encoding="utf-8")
    (places / "directory.yaml").mkdir()

    by_id, by_name = _build_global_ref_index(content_path, DEFAULT_REF_ROOTS, {})

    assert set(by_id) == {"zepp-new-taipei"}
    assert set(by_name) == {"Zepp New Taipei"}
    assert not caplog.records
    assert _resolve_path_ref(
        "places/_records.yml#private", content_path=content_path, cache={}
    ) == {"id": "private", "name": "Private"}


@pytest.mark.parametrize("bad_data", ["not: [valid, yaml: :", "record: invalid"])
def test_global_ref_discovery_still_warns_for_invalid_data_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, bad_data: str
) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    broken = content_path / "places" / "broken.yaml"
    broken.write_text(bad_data, encoding="utf-8")

    by_id, _ = _build_global_ref_index(content_path, DEFAULT_REF_ROOTS, {})

    assert set(by_id) == {"zepp-new-taipei"}
    assert "skipping unreadable" in caplog.text
    assert str(broken) in caplog.text
    with pytest.raises(TabularRefError, match="failed to load"):
        _resolve_path_ref(
            "places/broken.yaml#record", content_path=content_path, cache={}
        )


def test_get_global_ref_index_builds_only_once(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    index_cache: dict[str, Any] = {}
    first = _get_global_ref_index(content_path, DEFAULT_REF_ROOTS, {}, index_cache)
    second = _get_global_ref_index(content_path, DEFAULT_REF_ROOTS, {}, index_cache)
    assert first is second  # memoized: second call reuses the built index


def test_get_global_ref_index_reused_across_many_lookups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whole ``_resolve_ref_rows`` call over many rows builds the index once."""
    import pelican.plugins.tabular.tabular as _mod

    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"venue_ref": "zepp-new-taipei"} for _ in range(5)]
    index_cache: dict[str, Any] = {}
    calls: list[int] = []
    real_build = _mod._build_global_ref_index

    def _counting_build(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(_mod, "_build_global_ref_index", _counting_build)
    _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache=index_cache,
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=[],
    )
    assert len(calls) == 1


# --- _resolve_ref_value: dispatch + strict/non-strict ----------------------


def test_resolve_ref_value_path_form(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    result = _resolve_ref_value(
        "places/venues/taiwan.yaml#zepp-new-taipei",
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        field_name="venue_ref",
        row_index=0,
        source_file=tmp_path / "data" / "concerts.yaml",
    )
    assert result == ZEPP_RECORD


def test_resolve_ref_value_global_id_form(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    result = _resolve_ref_value(
        "zepp-new-taipei",
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        field_name="venue_ref",
        row_index=0,
        source_file=tmp_path / "data" / "concerts.yaml",
    )
    assert result == ZEPP_RECORD


def test_resolve_ref_value_strict_raises_with_locator(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    source_file = tmp_path / "data" / "concerts.yaml"
    with pytest.raises(TabularRefError) as exc_info:
        _resolve_ref_value(
            "places/venues/taiwan.yaml#no-such-id",
            content_path=content_path,
            cache={},
            ref_roots=DEFAULT_REF_ROOTS,
            index_cache={},
            strict=True,
            field_name="venue_ref",
            row_index=2,
            source_file=source_file,
        )
    message = str(exc_info.value)
    assert "venue_ref" in message
    assert "row 2" in message
    assert str(source_file) in message
    assert "no-such-id" in message


def test_resolve_ref_value_non_strict_degrades_to_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    content_path = _write_taiwan_venues(tmp_path)
    result = _resolve_ref_value(
        "places/venues/taiwan.yaml#no-such-id",
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=False,
        field_name="venue_ref",
        row_index=0,
        source_file=tmp_path / "data" / "concerts.yaml",
    )
    assert result == "places/venues/taiwan.yaml#no-such-id"
    assert "not found" in caplog.text


# --- _resolve_ref_rows -------------------------------------------------------


def test_resolve_ref_rows_replaces_field_name_with_full_record(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"title": "悟", "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"}]
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=[],
    )
    assert result == [{"title": "悟", "venue": ZEPP_RECORD}]
    assert ref_fields == frozenset({"venue"})


def test_resolve_ref_rows_strict_failure_does_not_raise_and_is_collected(
    tmp_path: Path,
) -> None:
    """The whole point of the fix: a strict-mode failure inside
    ``_resolve_ref_rows`` must NOT raise (that would only take down the one
    page being processed — see the module comment above ``_REF_SUFFIX``). It
    degrades the cell to the raw ref string and appends a locator-bearing
    message to ``errors`` instead.
    """
    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"title": "悟", "venue_ref": "places/venues/taiwan.yaml#no-such-id"}]
    errors: list[str] = []
    source_file = tmp_path / "data" / "concerts.yaml"
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=source_file,
        errors=errors,
    )
    assert result == [{"title": "悟", "venue": "places/venues/taiwan.yaml#no-such-id"}]
    assert ref_fields == frozenset({"venue"})
    assert len(errors) == 1
    assert "no-such-id" in errors[0]
    assert "venue_ref" in errors[0]
    assert str(source_file) in errors[0]


def test_resolve_ref_rows_collects_every_bad_ref_not_just_the_first(
    tmp_path: Path,
) -> None:
    """Two bad refs in the same file both surface in one pass — the reader
    doesn't have to fix one, rebuild, and only then discover the next.
    """
    content_path = _write_taiwan_venues(tmp_path)
    rows = [
        {"title": "A", "venue_ref": "places/venues/taiwan.yaml#no-such-id-1"},
        {"title": "B", "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"},
        {"title": "C", "venue_ref": "places/venues/taiwan.yaml#no-such-id-2"},
    ]
    errors: list[str] = []
    result, _ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=errors,
    )
    # all three rows still processed — the good one resolves normally
    assert result[1]["venue"] == ZEPP_RECORD
    assert len(errors) == 2
    assert any("no-such-id-1" in e for e in errors)
    assert any("no-such-id-2" in e for e in errors)


def test_resolve_ref_rows_non_strict_failure_not_collected(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"venue_ref": "places/venues/taiwan.yaml#no-such-id"}]
    errors: list[str] = []
    _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=False,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=errors,
    )
    assert errors == []
    assert "not found" in caplog.text


# --- collision: both <name> and <name>_ref present on the same row ---------


def test_resolve_ref_rows_collision_strict_collects_error_keeps_original(
    tmp_path: Path,
) -> None:
    """`venue` and `venue_ref` both present: resolving the ref would
    silently overwrite hand-authored data. In strict mode that's collected
    into `errors` (like any other ref failure) — but the original `venue`
    value must survive untouched either way (see next test for non-strict).
    """
    content_path = _write_taiwan_venues(tmp_path)
    rows = [
        {
            "title": "悟",
            "venue": "Somewhere I Wrote By Hand",
            "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei",
        }
    ]
    errors: list[str] = []
    source_file = tmp_path / "data" / "concerts.yaml"
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=source_file,
        errors=errors,
    )
    assert result == [{"title": "悟", "venue": "Somewhere I Wrote By Hand"}]
    assert ref_fields == frozenset()  # not treated as a resolved ref field
    assert len(errors) == 1
    message = errors[0]
    assert "venue" in message
    assert "venue_ref" in message
    assert "Somewhere I Wrote By Hand" in message
    assert "row 0" in message
    assert str(source_file) in message


def test_resolve_ref_rows_collision_non_strict_keeps_original_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.WARNING)
    content_path = _write_taiwan_venues(tmp_path)
    rows = [
        {
            "venue": "Somewhere I Wrote By Hand",
            "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei",
        }
    ]
    errors: list[str] = []
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=False,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=errors,
    )
    assert result == [{"venue": "Somewhere I Wrote By Hand"}]
    assert ref_fields == frozenset()
    assert errors == []  # non-strict: never fails the build
    assert "Somewhere I Wrote By Hand" in caplog.text
    assert "venue_ref" in caplog.text


def test_resolve_ref_rows_non_string_ref_value_skipped(tmp_path: Path) -> None:
    """A `<name>_ref` field whose value isn't a string (e.g. already resolved
    upstream, or just malformed data) is left alone — not treated as a ref,
    no collision check, no error.
    """
    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"venue_ref": {"already": "a dict"}}]
    errors: list[str] = []
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=errors,
    )
    assert result == [{"venue_ref": {"already": "a dict"}}]
    assert ref_fields == frozenset()
    assert errors == []


# --- configurable ref_suffix (TABULAR_REF_SUFFIX) ---------------------------


def test_resolve_ref_rows_custom_suffix_resolves(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"title": "悟", "venue__link": "places/venues/taiwan.yaml#zepp-new-taipei"}]
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=[],
        ref_suffix="__link",
    )
    assert result == [{"title": "悟", "venue": ZEPP_RECORD}]
    assert ref_fields == frozenset({"venue"})


def test_resolve_ref_rows_custom_suffix_leaves_default_suffix_field_alone(
    tmp_path: Path,
) -> None:
    """With `ref_suffix="__link"`, a field literally named `source_ref` is
    just an ordinary string field — not a ref, no resolution attempted, no
    ambiguous-id/not-found error even though its value looks nothing like a
    real id. This is the escape hatch the coordinator asked for: a string
    field that happens to end in the *default* `_ref` suffix stops being
    load-bearing once the suffix is reconfigured.
    """
    content_path = _write_taiwan_venues(tmp_path)
    rows = [{"source_ref": "ISBN 978-0-000-00000-0"}]
    errors: list[str] = []
    result, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache={},
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=errors,
        ref_suffix="__link",
    )
    assert result == [{"source_ref": "ISBN 978-0-000-00000-0"}]
    assert ref_fields == frozenset()
    assert errors == []


def test_resolve_settings_reads_custom_ref_suffix() -> None:
    settings = _resolve_settings({"TABULAR_REF_SUFFIX": "__link"})
    assert settings["ref_suffix"] == "__link"


def test_resolve_settings_ref_suffix_defaults() -> None:
    settings = _resolve_settings({})
    assert settings["ref_suffix"] == DEFAULT_REF_SUFFIX == "_ref"


def test_resolve_ref_rows_shares_cache_across_rows(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    rows = [
        {"title": "A", "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"},
        {"title": "B", "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"},
    ]
    cache: dict[Path, list[dict[str, Any]]] = {}
    _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache=cache,
        ref_roots=DEFAULT_REF_ROOTS,
        index_cache={},
        strict=True,
        source_file=tmp_path / "data" / "concerts.yaml",
        errors=[],
    )
    assert len(cache) == 1


# ---------------------------------------------------------------------------
# _process_content: end-to-end ``venue_ref`` rendering
# ---------------------------------------------------------------------------


def test_process_content_resolves_venue_ref_as_plain_text_by_default(
    tmp_path: Path,
) -> None:
    """A bare `venue` field (no `:link`) shows plain text, not a link.

    This is the semantics migration: `venue_ref` now resolves to the whole
    referenced record; how it's *displayed* is a `fields` rendering choice,
    not baked into ref resolution.
    """
    content_path = _write_taiwan_venues(tmp_path)
    data_dir = content_path / "data"
    data_dir.mkdir()
    concerts = [
        {
            "title": {"text": "藥師寺寬邦「悟」", "href": "https://example.com/goo"},
            "date": datetime.date(2024, 10, 25),
            "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei",
        }
    ]
    (data_dir / "concerts.yaml").write_text(yaml.dump(concerts), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent('{% table data/concerts.yaml fields="title,date,venue" %}')
    _process_content(content, settings, content_path, {}, content_path=content_path)

    html = content._content
    assert "<td>Zepp New Taipei</td>" in html
    assert "openstreetmap.org" not in html
    assert "venue_ref" not in html


def test_process_content_venue_ref_link_transform_renders_link(tmp_path: Path) -> None:
    """`fields="venue:link"` opts back into the old link-cell rendering."""
    content_path = _write_taiwan_venues(tmp_path)
    data_dir = content_path / "data"
    data_dir.mkdir()
    concerts = [
        {"title": "悟", "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"}
    ]
    (data_dir / "concerts.yaml").write_text(yaml.dump(concerts), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent('{% table data/concerts.yaml fields="title,venue:link" %}')
    _process_content(content, settings, content_path, {}, content_path=content_path)

    html = content._content
    assert "Zepp New Taipei" in html
    expected_href = (
        'href="https://www.openstreetmap.org/?mlat=25.059661&mlon=121.449499'
        '#map=17/25.059661/121.449499"'
    )
    assert expected_href in html
    assert "venue_ref" not in html


def test_process_content_global_id_ref_resolves_end_to_end(tmp_path: Path) -> None:
    """``venue_ref: zepp-new-taipei`` (no ``#``) resolves via the global
    index over ``TABULAR_REF_ROOTS`` — no path to the target file needed.
    """
    content_path = _write_taiwan_venues(tmp_path)
    data_dir = content_path / "data"
    data_dir.mkdir()
    concerts = [{"title": "悟", "venue_ref": "zepp-new-taipei"}]
    (data_dir / "concerts.yaml").write_text(yaml.dump(concerts), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent('{% table data/concerts.yaml fields="title,venue" %}')
    _process_content(content, settings, content_path, {}, content_path=content_path)

    html = content._content
    assert "<td>Zepp New Taipei</td>" in html


def test_process_content_group_by_nested_ref_field(tmp_path: Path) -> None:
    """``group_by="venue.city"`` groups concerts by their venue's city — a
    property of the *referenced* record, reachable purely because a ref now
    resolves to the whole record rather than a display string.
    """
    content_path = tmp_path
    venues_dir = content_path / "places" / "venues"
    venues_dir.mkdir(parents=True)
    (venues_dir / "taiwan.yaml").write_text(
        yaml.dump(
            [
                {
                    "id": "moondog",
                    "name": "Moondog",
                    "city": "台北市",
                    "lat": 25.0,
                    "lon": 121.5,
                },
                {
                    "id": "nangang-exhibition-hall-1",
                    "name": "南港展覽館1館",
                    "city": "台北市",
                    "lat": 25.1,
                    "lon": 121.6,
                },
                {
                    "id": "dajia-riverside-park",
                    "name": "大佳河濱公園",
                    "city": "台北市",
                    "lat": 25.2,
                    "lon": 121.7,
                },
            ]
        ),
        encoding="utf-8",
    )
    data_dir = content_path / "data"
    data_dir.mkdir()
    concerts = [
        {"title": "小日向美香", "venue_ref": "moondog"},
        {"title": "ANISAMA", "venue_ref": "nangang-exhibition-hall-1"},
    ]
    (data_dir / "concerts.yaml").write_text(yaml.dump(concerts), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent(
        '{% table data/concerts.yaml fields="title,venue" '
        'group_by="venue.city" group_summary_at="venue.city" %}'
    )
    _process_content(content, settings, content_path, {}, content_path=content_path)

    html = content._content
    assert "osm-group-header" in html
    assert "台北市" in html
    assert "<td>Moondog</td>" in html
    assert "<td>南港展覽館1館</td>" in html


def test_process_content_ref_text_field_override(tmp_path: Path) -> None:
    content_path = tmp_path
    venues_dir = content_path / "places" / "venues"
    venues_dir.mkdir(parents=True)
    (venues_dir / "taiwan.yaml").write_text(
        yaml.dump(
            {
                "locations": [
                    {
                        "id": "zepp-new-taipei",
                        "name": "Zepp New Taipei",
                        "label": "北車 Zepp",
                        "lat": 25.06,
                        "lon": 121.45,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    data_dir = content_path / "data"
    data_dir.mkdir()
    rows = [{"venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"}]
    (data_dir / "concerts.yaml").write_text(yaml.dump(rows), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent('{% table data/concerts.yaml ref_text_field="label" %}')
    _process_content(content, settings, content_path, {}, content_path=content_path)
    assert "北車 Zepp" in content._content
    assert "<td>Zepp New Taipei</td>" not in content._content


def test_process_content_ref_href_template_override(tmp_path: Path) -> None:
    content_path = _write_taiwan_venues(tmp_path)
    data_dir = content_path / "data"
    data_dir.mkdir()
    rows = [{"venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"}]
    (data_dir / "concerts.yaml").write_text(yaml.dump(rows), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent(
        '{% table data/concerts.yaml fields="venue:link" '
        'ref_href_template="https://maps.example/{lat},{lon}" %}'
    )
    _process_content(content, settings, content_path, {}, content_path=content_path)
    assert 'href="https://maps.example/25.059661,121.449499"' in content._content


def test_process_content_ref_missing_target_does_not_raise_synchronously(
    tmp_path: Path,
) -> None:
    """`_process_content` must NOT raise, even in strict mode.

    Pelican's content generators wrap each page's processing in a
    try/except that logs an ERROR and *skips the page*, continuing the
    build with exit code 0 — see the module comment above `_REF_SUFFIX`.
    Raising synchronously here would silently delete the page from the
    site, not fail the build. The page must still render (degraded: the
    raw ref string stands in for the cell) and the failure must instead be
    collected into the `ref_errors` list for `_check_ref_errors` to raise
    from later, once, after every page is done.
    """
    content_path = tmp_path
    data_dir = content_path / "data"
    data_dir.mkdir()
    rows = [{"venue_ref": "places/venues/nope.yaml#some-id"}]
    (data_dir / "concerts.yaml").write_text(yaml.dump(rows), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent("{% table data/concerts.yaml %}")
    ref_errors: list[str] = []
    _process_content(
        content,
        settings,
        content_path,
        {},
        content_path=content_path,
        ref_errors=ref_errors,
    )
    # page still rendered — not lost — with the raw ref string in the cell
    assert "places/venues/nope.yaml#some-id" in content._content
    assert "osm-place-list" in content._content
    # but the failure was collected for the finalized-time check
    assert len(ref_errors) == 1
    message = ref_errors[0]
    assert "places/venues/nope.yaml#some-id" in message
    assert "venue_ref" in message
    assert "row 0" in message


def test_process_content_collects_errors_across_multiple_shortcodes(
    tmp_path: Path,
) -> None:
    """Two separate `{% table %}` calls on one page, each with a bad ref,
    both end up in `ref_errors` — not just the first one encountered.
    """
    content_path = tmp_path
    data_dir = content_path / "data"
    data_dir.mkdir()
    (data_dir / "a.yaml").write_text(
        yaml.dump([{"venue_ref": "places/venues/nope-a.yaml#x"}]), encoding="utf-8"
    )
    (data_dir / "b.yaml").write_text(
        yaml.dump([{"venue_ref": "places/venues/nope-b.yaml#y"}]), encoding="utf-8"
    )

    settings = _make_settings()
    content = _FakeContent("{% table data/a.yaml %}\n{% table data/b.yaml %}")
    ref_errors: list[str] = []
    _process_content(
        content,
        settings,
        content_path,
        {},
        content_path=content_path,
        ref_errors=ref_errors,
    )
    assert len(ref_errors) == 2
    assert any("nope-a.yaml" in e for e in ref_errors)
    assert any("nope-b.yaml" in e for e in ref_errors)


def _collision_row_content_path(tmp_path: Path) -> Path:
    content_path = _write_taiwan_venues(tmp_path)
    data_dir = content_path / "data"
    data_dir.mkdir()
    rows = [
        {
            "title": "悟",
            "venue": "Somewhere I Wrote By Hand",
            "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei",
        }
    ]
    (data_dir / "concerts.yaml").write_text(yaml.dump(rows), encoding="utf-8")
    return content_path


def test_process_content_collision_strict_keeps_original_text_and_collects_error(
    tmp_path: Path,
) -> None:
    """End-to-end: a row with both `venue` and `venue_ref` renders the
    hand-authored `venue` text untouched, in strict mode too — the build
    still fails (via the collected error), but the page itself is correct.
    """
    content_path = _collision_row_content_path(tmp_path)
    settings = _make_settings()
    content = _FakeContent('{% table data/concerts.yaml fields="title,venue" %}')
    ref_errors: list[str] = []
    _process_content(
        content,
        settings,
        content_path,
        {},
        content_path=content_path,
        ref_errors=ref_errors,
    )
    assert "<td>Somewhere I Wrote By Hand</td>" in content._content
    assert "Zepp New Taipei" not in content._content
    assert len(ref_errors) == 1
    assert "venue" in ref_errors[0] and "venue_ref" in ref_errors[0]


def test_process_content_collision_non_strict_keeps_original_text_no_error(
    tmp_path: Path,
) -> None:
    content_path = _collision_row_content_path(tmp_path)
    settings = _make_settings(TABULAR_REF_STRICT=False)
    content = _FakeContent('{% table data/concerts.yaml fields="title,venue" %}')
    ref_errors: list[str] = []
    _process_content(
        content,
        settings,
        content_path,
        {},
        content_path=content_path,
        ref_errors=ref_errors,
    )
    assert "<td>Somewhere I Wrote By Hand</td>" in content._content
    assert "Zepp New Taipei" not in content._content
    assert ref_errors == []


# ---------------------------------------------------------------------------
# _check_ref_errors (connected to signals.finalized — see module comment
# above DEFAULT_REF_SUFFIX for why the build-failing raise has to happen
# here and not synchronously during page processing)
# ---------------------------------------------------------------------------


def test_check_ref_errors_raises_with_every_message_when_errors_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pelican.plugins.tabular.tabular as _mod

    monkeypatch.setattr(_mod, "_ref_errors", ["first error", "second error"])
    with pytest.raises(TabularRefError) as exc_info:
        _mod._check_ref_errors(None)
    message = str(exc_info.value)
    assert "first error" in message
    assert "second error" in message
    assert "2" in message  # error count


def test_check_ref_errors_noop_when_no_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pelican.plugins.tabular.tabular as _mod

    monkeypatch.setattr(_mod, "_ref_errors", [])
    _mod._check_ref_errors(None)  # must not raise


def test_register_connects_finalized_to_check_ref_errors() -> None:
    import pelican.plugins.tabular.tabular as _mod
    from pelican import signals as _signals

    _mod.register()
    receivers = [r() for r in _signals.finalized.receivers.values()]
    assert _mod._check_ref_errors in receivers


def test_full_lifecycle_strict_ref_error_fails_via_finalized_signal(
    tmp_path: Path,
) -> None:
    """End-to-end simulation of the real build lifecycle: `_init` resets the
    accumulator, a page with a bad ref is processed via `_process_article`
    (which must NOT raise — the page-skip bug this whole fix addresses),
    and only the `signals.finalized`-connected `_check_ref_errors` call
    raises, with the bad ref's locator in the message.
    """
    import pelican.plugins.tabular.tabular as _mod

    content_dir = tmp_path / "content"
    data_dir = content_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "concerts.yaml").write_text(
        yaml.dump([{"venue_ref": "places/venues/nope.yaml#ghost-venue"}]),
        encoding="utf-8",
    )

    pelican_obj = MagicMock()
    pelican_obj.settings = {"PATH": str(content_dir)}
    with patch.object(_mod, "_register_markdown_extension"):
        _mod._init(pelican_obj)

    content = MagicMock()
    content.source_path = str(content_dir / "pages" / "concerts.md")
    content.url = "concerts/"
    content._content = "{% table data/concerts.yaml %}"

    # must not raise — this is the exact bug the coordinator caught: a
    # synchronous raise here only skips this one page, build stays exit 0
    _mod._process_article(content)
    assert "places/venues/nope.yaml#ghost-venue" in content._content

    with pytest.raises(TabularRefError) as exc_info:
        _mod._check_ref_errors(pelican_obj)
    message = str(exc_info.value)
    assert "ghost-venue" in message
    assert "venue_ref" in message


def test_process_content_ref_missing_target_degrades_to_raw_string_when_not_strict(
    tmp_path: Path,
) -> None:
    content_path = tmp_path
    data_dir = content_path / "data"
    data_dir.mkdir()
    rows = [{"venue_ref": "places/venues/nope.yaml#some-id"}]
    (data_dir / "concerts.yaml").write_text(yaml.dump(rows), encoding="utf-8")

    settings = _make_settings(TABULAR_REF_STRICT=False)
    content = _FakeContent("{% table data/concerts.yaml %}")
    _process_content(content, settings, content_path, {}, content_path=content_path)
    assert "places/venues/nope.yaml#some-id" in content._content


# ---------------------------------------------------------------------------
# ref_href_template fallback chain
# ---------------------------------------------------------------------------


def test_split_ref_href_templates_single() -> None:
    assert _split_ref_href_templates("https://x/{lat}/{lon}") == [
        "https://x/{lat}/{lon}"
    ]


def test_split_ref_href_templates_chain() -> None:
    raw = "https://x/{osm_type}/{osm_id}|https://x/?#map=16/{lat}/{lon}"
    assert _split_ref_href_templates(raw) == [
        "https://x/{osm_type}/{osm_id}",
        "https://x/?#map=16/{lat}/{lon}",
    ]


def test_split_ref_href_templates_drops_blank_segments() -> None:
    assert _split_ref_href_templates("https://x/{lat}|") == ["https://x/{lat}"]


def test_template_fields_extracts_placeholders() -> None:
    assert _template_fields("https://x/{osm_type}/{osm_id}") == [
        "osm_type",
        "osm_id",
    ]


def test_template_fields_no_placeholders() -> None:
    assert _template_fields("https://x/static") == []


def test_template_fields_deduplicates_repeated_placeholders() -> None:
    """An OSM marker URL repeats lat/lon — pin position and map centre."""
    assert _template_fields(
        "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
    ) == ["lat", "lon"]


def test_template_fields_preserves_first_appearance_order() -> None:
    assert _template_fields("https://x/{b}/{a}/{b}/{c}/{a}") == ["b", "a", "c"]


def test_repeated_placeholder_template_is_applicable() -> None:
    """Dedup must not change applicability for repeated placeholders."""
    template = "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
    assert _template_is_applicable(template, {"lat": 25.06, "lon": 121.45}) is True
    assert _template_is_applicable(template, {"lat": 25.06}) is False


def test_default_ref_href_template_drops_a_marker_pin() -> None:
    """The default must place a pin, not merely centre the viewport.

    A bare ``#map=`` centre leaves the reader guessing which building is
    meant; ``?mlat=&mlon=`` marks the exact place.
    """
    assert "mlat=" in DEFAULT_REF_HREF_TEMPLATE
    assert "mlon=" in DEFAULT_REF_HREF_TEMPLATE
    assert _format_ref_href(
        DEFAULT_REF_HREF_TEMPLATE, {"lat": 25.059661, "lon": 121.449499}
    ) == (
        "https://www.openstreetmap.org/?mlat=25.059661&mlon=121.449499"
        "#map=17/25.059661/121.449499"
    )


def test_template_is_applicable_all_present() -> None:
    item = {"osm_type": "node", "osm_id": 123}
    assert _template_is_applicable("https://x/{osm_type}/{osm_id}", item) is True


def test_template_is_applicable_missing_key() -> None:
    item = {"osm_type": "node"}
    assert _template_is_applicable("https://x/{osm_type}/{osm_id}", item) is False


def test_template_is_applicable_none_value() -> None:
    item = {"osm_type": "node", "osm_id": None}
    assert _template_is_applicable("https://x/{osm_type}/{osm_id}", item) is False


def test_template_is_applicable_empty_string_value() -> None:
    item = {"osm_type": "node", "osm_id": ""}
    assert _template_is_applicable("https://x/{osm_type}/{osm_id}", item) is False


def test_template_is_applicable_no_placeholders_always_true() -> None:
    assert _template_is_applicable("https://x/static", {}) is True


def test_resolve_ref_href_first_template_applicable() -> None:
    templates = [
        "https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "https://www.openstreetmap.org/?#map=16/{lat}/{lon}",
    ]
    item = {"osm_type": "node", "osm_id": 13353295908, "lat": 25.06, "lon": 121.45}
    assert (
        _resolve_ref_href(templates, item)
        == "https://www.openstreetmap.org/node/13353295908"
    )


def test_resolve_ref_href_falls_back_to_second_template() -> None:
    templates = [
        "https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "https://www.openstreetmap.org/?#map=16/{lat}/{lon}",
    ]
    item = {"lat": 25.059661, "lon": 121.449499}
    assert (
        _resolve_ref_href(templates, item)
        == "https://www.openstreetmap.org/?#map=16/25.059661/121.449499"
    )


def test_resolve_ref_href_no_template_applicable_returns_empty() -> None:
    templates = [
        "https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "https://www.openstreetmap.org/?#map=16/{lat}/{lon}",
    ]
    item = {"name": "Somewhere with no coordinates at all"}
    assert _resolve_ref_href(templates, item) == ""


def test_resolve_ref_href_single_template_backward_compatible() -> None:
    templates = ["https://www.openstreetmap.org/?#map=16/{lat}/{lon}"]
    item = {"lat": 25.06, "lon": 121.45}
    assert (
        _resolve_ref_href(templates, item)
        == "https://www.openstreetmap.org/?#map=16/25.06/121.45"
    )


def test_link_transform_chain_prefers_osm_id() -> None:
    """The fallback chain now applies at render time via the ``:link`` field
    transform, not at ref resolution — ``_resolve_ref_value`` just hands back
    the whole record; ``_field_value(..., "venue:link", ctx)`` is what builds
    the href.
    """
    record = {
        "id": "zepp-new-taipei",
        "name": "Zepp New Taipei",
        "osm_type": "node",
        "osm_id": 13353295908,
        "lat": 25.059661,
        "lon": 121.449499,
    }
    chain = (
        "https://www.openstreetmap.org/{osm_type}/{osm_id}"
        "|https://www.openstreetmap.org/?#map=16/{lat}/{lon}"
    )
    ctx = RefRenderContext(frozenset({"venue"}), DEFAULT_REF_TEXT_FIELD, chain)
    result = _field_value({"venue": record}, "venue:link", ctx)
    assert result == {
        "text": "Zepp New Taipei",
        "href": "https://www.openstreetmap.org/node/13353295908",
    }


def test_link_transform_chain_falls_back_without_osm_id() -> None:
    record = {
        "id": "linkou-gymnasium",
        "name": "林口體育館",
        "lat": 25.0695,
        "lon": 121.3647,
    }
    chain = (
        "https://www.openstreetmap.org/{osm_type}/{osm_id}"
        "|https://www.openstreetmap.org/?#map=16/{lat}/{lon}"
    )
    ctx = RefRenderContext(frozenset({"venue"}), DEFAULT_REF_TEXT_FIELD, chain)
    result = _field_value({"venue": record}, "venue:link", ctx)
    assert result == {
        "text": "林口體育館",
        "href": "https://www.openstreetmap.org/?#map=16/25.0695/121.3647",
    }


def test_link_transform_chain_all_inapplicable_yields_plain_text() -> None:
    record = {"id": "no-coords", "name": "No Coords Venue"}
    chain = (
        "https://www.openstreetmap.org/{osm_type}/{osm_id}"
        "|https://www.openstreetmap.org/?#map=16/{lat}/{lon}"
    )
    ctx = RefRenderContext(frozenset({"venue"}), DEFAULT_REF_TEXT_FIELD, chain)
    result = _field_value({"venue": record}, "venue:link", ctx)
    assert result == "No Coords Venue"


def test_process_content_ref_href_chain_end_to_end(tmp_path: Path) -> None:
    content_path = tmp_path
    venues_dir = content_path / "places" / "venues"
    venues_dir.mkdir(parents=True)
    (venues_dir / "taiwan.yaml").write_text(
        yaml.dump(
            {
                "locations": [
                    {
                        "id": "zepp-new-taipei",
                        "name": "Zepp New Taipei",
                        "osm_type": "node",
                        "osm_id": 13353295908,
                        "lat": 25.059661,
                        "lon": 121.449499,
                    },
                    {
                        "id": "linkou-gymnasium",
                        "name": "林口體育館",
                        "lat": 25.0695,
                        "lon": 121.3647,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    data_dir = content_path / "data"
    data_dir.mkdir()
    rows = [
        {"title": "A", "venue_ref": "places/venues/taiwan.yaml#zepp-new-taipei"},
        {"title": "B", "venue_ref": "places/venues/taiwan.yaml#linkou-gymnasium"},
    ]
    (data_dir / "concerts.yaml").write_text(yaml.dump(rows), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent(
        '{% table data/concerts.yaml fields="title,venue:link" '
        'ref_href_template="https://www.openstreetmap.org/{osm_type}/{osm_id}'
        '|https://www.openstreetmap.org/?#map=16/{lat}/{lon}" %}'
    )
    _process_content(content, settings, content_path, {}, content_path=content_path)

    html = content._content
    assert 'href="https://www.openstreetmap.org/node/13353295908"' in html
    assert 'href="https://www.openstreetmap.org/?#map=16/25.0695/121.3647"' in html

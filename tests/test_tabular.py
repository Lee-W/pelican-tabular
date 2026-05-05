"""Tests for pelican-tabular plugin."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import yaml

from pelican.plugins.tabular.tabular import (
    BUILTIN_COUNT_TEMPLATES,
    BUILTIN_GROUP_COUNT_TEMPLATES,
    DEFAULT_COUNT_TEMPLATE,
    DEFAULT_GROUP_COUNT_TEMPLATE,
    _aggregate_field,
    _cell_value,
    _collapse_rows,
    _detect_columns,
    _extract_year,
    _extract_years,
    _format_scalar,
    _load_data_file,
    _make_pattern,
    _parse_aggregate_kwarg,
    _parse_csv_kwarg,
    _parse_shortcode_args,
    _process_content,
    _render_table_html,
    _resolve_count_template,
    _resolve_filename_url,
    _resolve_group_count_template,
    _resolve_rows,
    _resolve_settings,
    _resolve_value,
    _slugify,
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
        result = _aggregate_field("sum", "count", [{"count": 3}])
    assert result == ""
    assert "unknown aggregate op" in caplog.text


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
    result = _collapse_rows(TIERED_ROWS, ["tier"], {})
    titles = [r["title"] for r in result]
    assert titles == ["A", "C", "B"]  # SSS rows grouped first, then SS


def test_collapse_rows_no_aggregate_adds_places() -> None:
    result = _collapse_rows(TIERED_ROWS, ["tier"], {})
    for row in result:
        assert "_places" in row
        assert len(row["_places"]) == 1


def test_collapse_rows_aggregate_merges() -> None:
    rows = [
        {"anime": "X", "tier": "SSS", "year": 2020},
        {"anime": "X", "tier": "SSS", "year": 2022},
    ]
    result = _collapse_rows(rows, ["anime"], {"year": "year"})
    assert len(result) == 1
    assert result[0]["year"] == "2020, 2022"
    assert len(result[0]["_places"]) == 2


def test_collapse_rows_aggregate_first_nonblank_wins() -> None:
    rows = [
        {"anime": "X", "tier": "SSS", "note": ""},
        {"anime": "X", "tier": "SSS", "note": "great"},
    ]
    result = _collapse_rows(rows, ["anime"], {"year": "year"})
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


def _render(**kwargs: object) -> str:
    defaults: dict = {
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
    return _render_table_html(SAMPLE_ROWS, **defaults)  # type: ignore[arg-type]


def test_render_uses_osm_place_list_classes() -> None:
    html = _render(count_template="{n} rows")
    assert 'class="osm-place-list-wrapper"' in html
    assert 'class="osm-place-list"' in html
    assert 'class="osm-place-list-count"' in html
    assert "2 rows" in html


def test_render_basic() -> None:
    html = _render()
    assert "<th>title</th>" in html
    assert "<td>Book A</td>" in html


def test_render_sort_desc() -> None:
    html = _render(sort_by="rating", sort_order="desc")
    assert html.index("Book A") < html.index("Book B")


def test_render_sort_asc() -> None:
    html = _render(sort_by="rating", sort_order="asc")
    assert html.index("Book B") < html.index("Book A")


def test_render_hidden_field() -> None:
    html = _render(hidden={"year"})
    assert "<th>year</th>" not in html
    assert "<th>title</th>" in html


def test_render_field_labels() -> None:
    html = _render(field_labels={"rating": "Score"})
    assert "<th>Score</th>" in html
    assert "<th>rating</th>" not in html


def test_render_explicit_fields_ordering() -> None:
    html = _render(fields=["year", "title"])
    assert html.index("<th>year</th>") < html.index("<th>title</th>")
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


def _make_settings(**overrides: object) -> dict:
    return _resolve_settings({**overrides})


def test_process_content_replaces_shortcode(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "books.yaml"
    data_file.parent.mkdir()
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent("{% table data/books.yaml %}")
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert "osm-place-list" in content._content
    assert "<td>Book A</td>" in content._content


def test_process_content_resolves_filename(tmp_path: Path) -> None:
    rows = [{"title": "Foo", "url": "{filename}posts/foo.md"}]
    data_file = tmp_path / "items.yaml"
    data_file.write_text(yaml.dump(rows), encoding="utf-8")

    url_map = {"posts/foo.md": "https://example.com/posts/foo/"}
    settings = _make_settings()
    content = _FakeContent("{% table items.yaml %}")
    _process_content(content, settings, tmp_path, url_map)  # type: ignore[arg-type]
    assert "https://example.com/posts/foo/" in content._content


def test_process_content_group_by(tmp_path: Path) -> None:
    data_file = tmp_path / "tiered.yaml"
    data_file.write_text(yaml.dump(TIERED_ROWS), encoding="utf-8")

    settings = _make_settings()
    content = _FakeContent(
        '{% table tiered.yaml group_by="tier" group_summary_at="tier" %}'
    )
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert "osm-group-header" in content._content
    assert "SSS" in content._content


def test_process_content_per_shortcode_field_labels(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "books.yaml"
    data_file.parent.mkdir()
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _make_settings(TABULAR_FIELD_LABELS={"title": "書名"})
    content = _FakeContent('{% table data/books.yaml field_labels="title:作品" %}')
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert "<th>作品</th>" in content._content
    assert "<th>書名</th>" not in content._content


def test_process_content_per_shortcode_field_labels_merge(tmp_path: Path) -> None:
    data_file = tmp_path / "data" / "books.yaml"
    data_file.parent.mkdir()
    data_file.write_text(yaml.dump(SAMPLE_ROWS), encoding="utf-8")

    settings = _make_settings(TABULAR_FIELD_LABELS={"rating": "評分"})
    content = _FakeContent('{% table data/books.yaml field_labels="title:作品" %}')
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert "<th>作品</th>" in content._content
    assert "<th>評分</th>" in content._content


def test_process_content_missing_file(tmp_path: Path) -> None:
    settings = _make_settings()
    content = _FakeContent("{% table missing.yaml %}")
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert "tabular-error" in content._content


def test_process_content_no_shortcode(tmp_path: Path) -> None:
    settings = _make_settings()
    content = _FakeContent("<p>No shortcode here.</p>")
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert content._content == "<p>No shortcode here.</p>"


def test_process_content_empty_content(tmp_path: Path) -> None:
    settings = _make_settings()
    content = _FakeContent("")
    _process_content(content, settings, tmp_path, {})  # type: ignore[arg-type]
    assert content._content == ""


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

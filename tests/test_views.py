from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pelican.plugins.tabular.assets import copy_assets, register_assets
from pelican.plugins.tabular.core import cell_value, collapse_rows
from pelican.plugins.tabular.tabular import _process_content, _resolve_settings
from pelican.plugins.tabular.views import render_view, sort_value


def payload(result: str) -> dict[str, Any]:
    match = re.search(r'class="tabular-data">(.*?)</script>', result, re.S)
    assert match
    return json.loads(match[1])  # type: ignore[no-any-return]


def test_public_values_and_search_are_separate_from_display() -> None:
    data = [
        {
            "title": {"href": "/post", "text": "Story"},
            "score": "10",
            "date": datetime.date(2026, 1, 2),
            "secret": "not-for-browser",
            "note": "hidden but searchable",
            "status": "ongoing",
        }
    ]
    config = {
        "fields": ["title", "date"],
        "search_fields": ["note", "status"],
        "sort_fields": ["score", "date"],
        "filters": {"status": {"options": [{"value": "ongoing", "label": "正在看"}]}},
    }
    rendered = render_view(data, config, table_id="works")
    record = payload(rendered)["records"][0]
    assert 'href="/post"' in rendered
    assert "secret" not in rendered and "not-for-browser" not in rendered
    assert "正在看" in record["search"]
    assert record["sort"]["score"] == 10
    assert record["sort"]["date"] == datetime.date(2026, 1, 2).toordinal()
    assert record["values"]["date"] == ["2026-01-02"]


def test_markup_and_json_are_safe_for_user_text() -> None:
    evil = '</script><img src=x onerror="alert(1)">'
    rendered = render_view([{"title": evil}], {"fields": ["title"]}, table_id="safe")
    assert rendered.count("</script>") == 1
    assert "<img" not in rendered
    assert payload(rendered)["records"][0]["values"]["title"] == [evil]
    assert "href=" not in cell_value({"href": "javascript:alert(1)", "text": "link"})


@pytest.mark.parametrize(
    "config",
    [
        {"fields": "title"},
        {"display": {"title_field": "missing"}},
        {"display": {"layout": "unknown"}},
        {"display": {"meta_fields": ["missing"]}},
        {"filters": {"status": {"control": "unknown"}}},
        {"filters": {"status": {"match": "unknown"}}},
        {"filters": {"q": {}}},
        {"query_sync": "true"},
        {"query_prefix": "bad space"},
        {"sort_order": "up"},
        {"field_types": {"title": "unknown"}},
        {"presets": [{"label": "Bad", "filters": {"missing": ["x"]}}]},
        {"filters": {"status": {"options": [{"value": "a"}, {"value": "a"}]}}},
        {"filters": {"status": {"options": [{"value": "a", "tone": "bad"}]}}},
    ],
)
def test_invalid_views_fail_with_actionable_errors(config: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        render_view([{"title": "A"}], config, table_id="works")


def test_grouping_uses_shared_renderer_and_preserves_details() -> None:
    result = render_view(
        [
            {"title": "A", "format": "book"},
            {"title": "B", "format": "film"},
            {"title": "C", "format": "book"},
        ],
        {"fields": ["title"], "display": {"detail_fields": ["format"]}},
        table_id="grouped",
        group_by=["format"],
        group_summary_at=["format"],
    )
    assert 'id="grouped-group-book"' in result
    assert result.index('data-row="2"') < result.index('data-row="1"')
    assert result.count('class="tabular-detail"') == 3
    with pytest.raises(ValueError, match="aggregate"):
        render_view([], {}, table_id="works", aggregate={"score": "sum"})


def test_shared_collapse_can_preserve_consumer_union_policy() -> None:
    rows = [
        {"name": "A", "tags": ["one"], "year": 2020},
        {"name": "A", "tags": ["one", "two"], "year": 2021},
    ]
    result = collapse_rows(rows, ["name"], {"year": "year"}, union_fields=("tags",))
    assert result[0]["tags"] == ["one", "two"]
    assert result[0]["year"] == "2020, 2021"
    assert rows[0]["tags"] == ["one"]


def test_empty_data_still_has_controls_and_table_headers() -> None:
    result = render_view([], {"fields": ["title"]}, table_id="empty")
    assert "<th" in result
    assert payload(result)["records"] == []


@pytest.mark.parametrize(
    "value,kind,expected",
    [
        ("2026", "date", datetime.date(2026, 1, 1).toordinal()),
        ("2026-07", "date", datetime.date(2026, 7, 1).toordinal()),
        ("2026-02-30", "date", None),
        ("nan", "number", None),
        ("Infinity", "number", None),
        ("10.5", "number", 10.5),
    ],
)
def test_explicit_field_types(value: str, kind: str, expected: float | None) -> None:
    assert sort_value(value, kind) == expected


def test_shortcode_precedence_ids_and_prefix_collisions(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text('[{"title":"A","score":5}]')
    settings = _resolve_settings(
        {
            "TABULAR_FIELD_LABELS": {"score": "Global"},
            "TABULAR_VIEWS": {
                "works": {
                    "fields": ["title"],
                    "query_sync": True,
                    "field_labels": {"score": "View"},
                }
            },
        }
    )
    content = MagicMock()
    content._content = (
        '{% table data.json view="works" id="works" '
        'fields="score" field_labels="score:Local" %}'
        '{% table data.json view="works" id="works" %}'
    )
    _process_content(content, settings, tmp_path, {})
    assert ">Local</th>" in content._content
    assert "duplicate table id" in content._content
    settings["views"]["works"]["query_prefix"] = ""
    content._content = (
        '{% table data.json view="works" id="one" %}'
        '{% table data.json view="works" id="two" %}'
    )
    _process_content(content, settings, tmp_path, {})
    assert "duplicate query prefix" in content._content


def test_empty_shortcode_grouping_overrides_view(tmp_path: Path) -> None:
    (tmp_path / "data.json").write_text('[{"title":"A","format":"book"}]')
    settings = _resolve_settings(
        {
            "TABULAR_VIEWS": {
                "works": {
                    "fields": ["title"],
                    "group_by": ["format"],
                    "group_summary_at": ["format"],
                }
            }
        }
    )
    content = MagicMock()
    content._content = (
        '{% table data.json view="works" group_by="" group_summary_at="" %}'
    )
    _process_content(content, settings, tmp_path, {})
    assert 'class="tabular-view"' in content._content
    assert "tabular-group-header" not in content._content


@pytest.mark.parametrize("siteurl", ["", "https://example.test/blog/ja/"])
def test_only_named_views_load_their_assets(tmp_path: Path, siteurl: str) -> None:
    (tmp_path / "data.json").write_text('[{"title":"A"}]')
    settings = _resolve_settings(
        {
            "SITEURL": siteurl,
            "TABULAR_VIEWS": {"works": {"fields": ["title"]}},
        }
    )
    content = MagicMock()
    content._content = "{% table data.json %}"
    _process_content(content, settings, tmp_path, {})
    assert "pelican_tabular/" not in content._content
    content._content += (
        '{% table data.json view="works" id="one" %}'
        '{% table data.json view="works" id="two" %}'
    )
    _process_content(content, settings, tmp_path, {})
    base = siteurl.rstrip("/") + "/static/pelican_tabular/"
    assert content._content.count(base + "js/tabular.js") == 1
    assert content._content.count(base + "css/tabular.css") == 1
    assert 'class="tabular-controls" data-pagefind-ignore' in content._content
    assert '<td class="tabular-title"' in content._content
    assert (
        "data-pagefind-ignore"
        not in content._content.split('<td class="tabular-title"')[1].split(">")[0]
    )


def test_asset_registration_is_idempotent_and_works_without_shortcode(
    tmp_path: Path,
) -> None:
    from pelican import signals

    register_assets()
    register_assets()
    pelican = MagicMock()
    pelican.settings = {"OUTPUT_PATH": str(tmp_path)}
    assert list(signals.finalized.receivers_for(pelican)).count(copy_assets) == 1
    copy_assets(pelican)
    assert (tmp_path / "static/pelican_tabular/js/tabular.js").exists()
    copy_assets(pelican)
    assert (tmp_path / "static/pelican_tabular/css/tabular.css").exists()

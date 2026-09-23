"""Language boundaries, projections and build isolation (not just translations)."""

from __future__ import annotations

import html
import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pelican.plugins.tabular import tabular
from pelican.plugins.tabular.i18n import (
    CATALOG,
    component_locale,
    direction,
    format_message,
    localized_text,
    match_locale,
    normalize_locale,
    normalize_search,
    project_record,
    resolve_text,
)
from pelican.plugins.tabular.views import render_view


@pytest.mark.parametrize(
    ("tag", "canonical", "catalog"),
    [
        ("zh_TW", "zh-TW", "zh-Hant"),
        ("zh-hant", "zh-Hant", "zh-Hant"),
        ("zh", "zh", "zh-Hant"),
        ("zh-HK", "zh-HK", "zh-Hant"),
        ("zh-Hans", "zh-Hans", None),
        ("zh-CN", "zh-CN", None),
        ("ja-jp", "ja-JP", "ja"),
        ("zz", "zz", None),
        ("en-US-u-nu-latn", "en-US-u-nu-latn", "en"),
    ],
)
def test_locale_matching(tag: str, canonical: str, catalog: str | None) -> None:
    assert normalize_locale(tag) == canonical
    assert match_locale(tag, CATALOG.data) == catalog


def test_explicit_script_never_falls_through_to_other_script() -> None:
    assert match_locale("sr-Latn", {"sr": "Ћирилица"}) is None
    assert match_locale("zh-Hans", {"zh": "繁體"}) is None
    assert match_locale("zh-TW", {"zh-TW": "exact", "zh": "parent"}) == "zh-TW"
    assert component_locale("ja", "zh-TW", "en") == "ja"
    assert component_locale(None, "zh-TW", "en") == "zh-TW"
    assert component_locale(None, None) == "en"
    assert direction("ar-EG") == "rtl"


def test_text_fallback_retains_language_and_empty_translation() -> None:
    assert resolve_text({"ja": ""}, "ja-JP", fallback="source") == ("", "ja")
    assert resolve_text(
        {"ja": "訳"}, "en", fallback="原文", source_lang="zh-TW", english_fallback=False
    ) == ("原文", "zh-TW")
    assert localized_text({"en": "Title"}, "zz", fallback="title") == "Title"


@pytest.mark.parametrize("value", ["", "en--US", "not a language", "ja/../en"])
def test_invalid_locale_is_diagnostic(value: str) -> None:
    with pytest.raises(ValueError, match=r"VIEW\.lang"):
        normalize_locale(value, "VIEW.lang")


@pytest.mark.parametrize("n", [0, 1, 2, 21, 100])
def test_plural_rules_and_english_fallback(n: int) -> None:
    for locale in ("en", "zh-Hans", "zz"):
        words = CATALOG.resolve(locale)
        assert format_message(words["row_count"], locale, n=n) == (
            f"{n} row" if n == 1 else f"{n} rows"
        )
    assert format_message(CATALOG.resolve("ja-JP")["row_count"], n=n) == f"{n} 件"


@pytest.mark.parametrize("locale", ["ja_JP", "ja-jp", "ja-JP"])
def test_plural_override_exports_canonical_locale(locale: str) -> None:
    override = {
        "plural": "n",
        "locale": locale,
        "forms": {"one": "{n} singular", "other": "{n} other"},
    }
    message = CATALOG.resolve("en", {"row_count": override})["row_count"]
    assert isinstance(message, dict)
    assert message["locale"] == "ja-JP"
    assert format_message(message, "en", n=1) == "1 other"
    assert override["locale"] == locale


def test_override_validation_and_non_english_plural_rules() -> None:
    message = {
        "plural": "n",
        "forms": {
            "one": "{n} один",
            "few": "{n} несколько",
            "many": "{n} много",
            "other": "{n} другое",
        },
    }
    words = CATALOG.resolve("ru", {"row_count": message})
    assert format_message(words["row_count"], "ru", n=2) == "2 несколько"
    assert CATALOG.resolve("ja", {"count": ""})["count"] == ""
    assert CATALOG.resolve("en", {"search": {"ja": "検索"}})["search"] == "Search"
    for value in (123, "{bad}", {"plural": "shown", "forms": {"one": "{shown}"}}):
        with pytest.raises(ValueError, match=r"messages\.count"):
            CATALOG.resolve("en", {"count": value})
    with pytest.raises(ValueError, match=r"field_labels\.title\.ja"):
        localized_text({"ja": 1}, "ja", path="field_labels.title")  # type: ignore[dict-item]


TRANSLATION: dict[str, Any] = {
    "field": "translations",
    "fields": ["title", "note"],
    "source_lang": "zh-TW",
    "aliases": {"ja": {"title": "title_native"}},
}
RECORD: dict[str, Any] = {
    "id": "voice",
    "title": "聲之形",
    "title_native": "聲の形",
    "category": "anime",
    "note": "來源備註",
    "score": 10,
    "translations": {"ja": {"title": "聲の形 <映画>"}},
}


def test_projection_does_not_mutate_or_publish_translation_payload() -> None:
    original = deepcopy(RECORD)
    projected = project_record(RECORD, "ja-JP", TRANSLATION)
    assert original == RECORD
    assert projected["title"] == "聲の形 <映画>"
    assert projected["note"] == "來源備註"
    assert projected["_i18n_langs"] == {"title": "ja", "note": "zh-TW"}
    assert projected["id"] == "voice" and projected["score"] == 10
    assert "translations" not in projected
    assert project_record(RECORD, "en", TRANSLATION)["title"] == "聲之形"
    assert project_record(RECORD, "ja", None) == RECORD
    with pytest.raises(ValueError, match="cannot be translated"):
        project_record(RECORD, "ja", {"fields": ["id"]})
    with pytest.raises(ValueError, match="only scalar text"):
        project_record({"score": 10}, "ja", {"fields": ["score"]})


@pytest.mark.parametrize(
    ("record", "locale", "expected"),
    [
        pytest.param({}, "ja", None, id="absent"),
        pytest.param(
            {"translations": {"ja": {"note": "注記"}}},
            "en",
            None,
            id="unmatched-translation",
        ),
        pytest.param(
            {"translations": {"ja": {"note": "注記"}}},
            "ja-JP",
            "注記",
            id="compatible-translation",
        ),
        pytest.param(
            {"translations": {"ja": {"note": ""}}},
            "ja",
            "",
            id="empty-translation",
        ),
        pytest.param({"note_ja": "注記"}, "ja-JP", "注記", id="compatible-alias"),
        pytest.param({"note_ja": ""}, "ja", None, id="empty-alias"),
        pytest.param({"note": ""}, "en", "", id="empty-source"),
    ],
)
def test_projection_preserves_absent_fields(
    record: dict[str, Any], locale: str, expected: str | None
) -> None:
    original = deepcopy(record)
    projected = project_record(
        record,
        locale,
        {"fields": ["note"], "aliases": {"ja": {"note": "note_ja"}}},
    )
    if expected is None:
        assert "note" not in projected
        assert "note" not in projected["_i18n_langs"]
        assert "note" not in projected["_i18n_source"]
    else:
        assert projected["note"] == expected
    assert record == original


def test_translated_html_and_canonical_filters_are_ready_without_js() -> None:
    config = {
        "translations": TRANSLATION,
        "fields": ["title", "note", "category"],
        "field_labels": {"title": {"zh-TW": "作品名稱", "ja": "作品名 <&>"}},
        "search_fields": ["title", "title_native"],
        "filters": {
            "category": {
                "options": [
                    {
                        "value": "anime",
                        "label": {"ja": "アニメ", "zh": "動畫"},
                        "description": {"ja": "説明"},
                    }
                ]
            }
        },
        "presets": [{"label": {"ja": "動画"}, "filters": {"category": ["anime"]}}],
    }
    rendered = render_view([RECORD], config, table_id="ja", lang="ja-JP")
    assert 'lang="ja-JP"' in rendered
    assert 'lang="zh-TW">來源備註' in rendered
    assert 'lang="ja">聲の形 &lt;映画&gt;' in rendered
    assert "作品名 &lt;&amp;&gt;" in rendered and "動画" in rendered
    assert 'data-value="anime"' in rendered and "アニメ" in rendered
    payload = json.loads(
        rendered.split('class="tabular-data">')[1].split("</script>")[0]
    )
    assert payload["records"][0]["values"]["category"] == ["anime"]
    assert "translations" not in payload["records"][0]["values"]
    assert "聲の形" in payload["records"][0]["search"]
    assert "聲之形" not in payload["records"][0]["search"]


def test_content_and_explicit_component_languages(tmp_path: Path) -> None:
    (tmp_path / "rows.json").write_text(json.dumps([{"title": "X"}]))
    settings = tabular._resolve_settings(
        {
            "DEFAULT_LANG": "zh-TW",
            "TABULAR_VIEWS": {"ja": {"lang": "ja"}},
            "TABULAR_FIELD_LABELS": {"title": {"ja": "作品", "en": "Title"}},
        }
    )
    content = SimpleNamespace(
        lang="en",
        _content=(
            '{% table rows.json %}{% table rows.json lang="ja" %}'
            '{% table rows.json view="ja" %}'
            '{% table rows.json view="ja" lang="zh-Hans" %}'
        ),
    )
    tabular._process_content(content, settings, tmp_path, {})
    assert "1 row" in content._content and "1 件" in content._content
    assert 'lang="zh-Hans"' in content._content and "Search" in content._content
    payloads = [
        json.loads(html.unescape(s))
        for s in re.findall(r'data-i18n="([^"]+)"', content._content)
    ]
    assert [p["locale"] for p in payloads] == ["en", "ja"]


def test_context_survives_another_build_initializing(tmp_path: Path) -> None:
    builds = []
    for locale in ("ja", "en"):
        root = tmp_path / locale
        root.mkdir()
        (root / "rows.json").write_text(json.dumps([{"title": locale}]))
        build = SimpleNamespace(settings={"PATH": str(root), "DEFAULT_LANG": locale})
        tabular._init(build)
        builds.append(build)
    for build in builds:
        content = SimpleNamespace(
            settings=build.settings, _content="{% table rows.json %}"
        )
        tabular._process_article(content)
        assert f'lang="{build.settings["DEFAULT_LANG"]}"' in content._content
        assert f"<td>{build.settings['DEFAULT_LANG']}</td>" in content._content


def test_bad_template_fails_at_finalization(tmp_path: Path) -> None:
    (tmp_path / "rows.json").write_text('[{"title":"x"}]')
    build = SimpleNamespace(
        settings={"PATH": str(tmp_path), "TABULAR_COUNT_TEMPLATE": "{wrong}"}
    )
    tabular._init(build)
    content = SimpleNamespace(settings=build.settings, _content="{% table rows.json %}")
    tabular._process_article(content)
    with pytest.raises(tabular.TabularRefError, match="TABULAR_COUNT_TEMPLATE"):
        tabular._check_ref_errors(build)


def test_search_normalization_is_width_insensitive_but_not_transliteration() -> None:
    assert normalize_search("\uff21\uff22\uff23 ｶﾀｶﾅ E\u0301") == "abc カタカナ é"
    assert normalize_search("繁體") != normalize_search("繁体")


def test_references_are_localized_after_lookup_without_mutating_cache(
    tmp_path: Path,
) -> None:
    (tmp_path / "rows.json").write_text('[{"venue_ref":"places.yaml#station"}]')
    (tmp_path / "places.yaml").write_text(
        "- id: station\n  name: 東京車站\n  lat: 35\n  lon: 139\n"
        "  translations:\n    ja:\n      name: 東京駅\n"
    )
    settings = tabular._resolve_settings(
        {
            "TABULAR_REF_TRANSLATIONS": {"fields": ["name"], "source_lang": "zh-TW"},
        }
    )
    cache: dict[Path, list[dict[str, Any]]] = {}
    for locale, expected in [("ja", "東京駅"), ("en", "東京車站")]:
        content = SimpleNamespace(
            lang=locale,
            _content=('{% table rows.json fields="venue:link,venue.name" %}'),
        )
        tabular._process_content(content, settings, tmp_path, {}, ref_cache=cache)
        assert expected in content._content
        assert "mlat=35&mlon=139" in html.unescape(content._content)
        assert "translations" not in content._content
    assert cache[tmp_path / "places.yaml"][0]["name"] == "東京車站"


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"TABULAR_MESSAGES": {"row_count": "<b>{n}</b>"}}, "&lt;b&gt;1&lt;/b&gt;"),
        ({"TABULAR_COUNT_TEMPLATE": "<b>{n}</b>"}, "<b>1</b>"),
    ],
)
def test_catalog_text_and_legacy_html_templates(
    tmp_path: Path, overrides: dict[str, Any], expected: str
) -> None:
    (tmp_path / "rows.json").write_text('[{"title":"X","group":"A"}]')
    content = SimpleNamespace(_content="{% table rows.json %}")
    tabular._process_content(
        content, tabular._resolve_settings(overrides), tmp_path, {}
    )
    assert f'class="osm-place-list-count">{expected}</div>' in content._content

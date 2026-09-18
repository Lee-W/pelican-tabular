"""Build integration and performance fixtures using the real public renderers.

Pass --osm-source PATH to also exercise a working OSM checkout and its assets.
The default uses a versioned OSM markup fixture, so normal CI needs no sibling.
"""

from __future__ import annotations

import argparse
import html
import json
import runpy
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--osm-source", type=Path)
args = parser.parse_args()
if args.osm_source:
    sys.path.insert(0, str(args.osm_source.resolve() / "src"))

from pelican.plugins.tabular.assets import bundle_legacy_assets  # noqa: E402
from pelican.plugins.tabular.tabular import (  # noqa: E402
    _process_content,
    _resolve_settings,
)
from pelican.plugins.tabular.views import render_view  # noqa: E402

out = ROOT / "examples/database/output"
out.mkdir(parents=True, exist_ok=True)
settings = runpy.run_path(str(ROOT / "examples/database/pelicanconf.py"))
config = settings["TABULAR_VIEWS"]["works"]
rows = yaml.safe_load((ROOT / "examples/database/content/data/works.yaml").read_text())
fixture = ROOT / "tests/fixtures/osm-list.html"
extra = ""
if args.osm_source:
    sys.path.insert(0, str(args.osm_source.resolve() / "src"))
    from pelican.plugins.osm.osm import _copy_static, _render_place_list_html

    places = [
        {
            "name": "North Cafe",
            "city": "Taipei",
            "tags": ["cafe", "quiet"],
            "lat": 25.03,
            "lon": 121.56,
            "images": ["sample.svg"],
        },
        {"name": "South Cafe", "city": "Taipei", "tags": ["cafe"]},
        {"name": "City Library", "city": "Tainan", "tags": ["quiet"]},
    ]
    osm_html = _render_place_list_html(
        places,
        [],
        {},
        group_by=["city"],
        group_summary_at=["city"],
        group_count_template="2026: <b>{n}</b> places",
    )
    _copy_static(SimpleNamespace(settings={"OUTPUT_PATH": str(out)}))
    extra = (
        '<link rel="stylesheet" href="static/pelican_osm/css/osm-map.css">'
        '<script src="static/pelican_osm/js/osm-map.js" defer></script>'
    )
else:
    osm_html = fixture.read_text()
    # Exercise the old asset URLs in standalone CI too. The real OSM adapter
    # (including lightboxes) is tested with --osm-source in the paired job.
    legacy_assets = out / "static/pelican_osm"
    (legacy_assets / "js").mkdir(parents=True, exist_ok=True)
    (legacy_assets / "css").mkdir(parents=True, exist_ok=True)
    script = legacy_assets / "js/osm-map.js"
    stylesheet = legacy_assets / "css/osm-map.css"
    script.write_text("/* Standalone fixture: no OSM adapter. */\n")
    stylesheet.write_text("/* Standalone fixture: table styles only. */\n")
    bundle_legacy_assets(script, stylesheet)
head = (
    '<!doctype html><html lang="zh-TW"><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<link rel="stylesheet" href="static/pelican_tabular/css/tabular.css">'
    '<script src="static/pelican_tabular/js/tabular.js" defer></script>'
)
views = render_view(rows, config, table_id="works", lang="zh")
views += render_view(
    rows,
    config,
    table_id="other",
    lang="zh",
    group_by=["format"],
    group_summary_at=["format"],
)
(out / "integration.html").write_text(
    head + extra + "<body>" + views + osm_html + "</body></html>"
)
(out / "sample.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
    '<rect width="80" height="80" fill="skyblue"/></svg>'
)

# Existing themes load only OSM URLs. A named view injects its own optional
# assets through the real shortcode processor, including subsite prefixes.
shutil.copyfile(ROOT / "tests/fixtures/attila/article.css", out / "attila.css")
compat_data = [
    {
        "title": "Story A",
        "tier": "S",
        "date": "2026-01-01",
        "event": "Talk A",
        "reviews": {"text": "Review", "href": "/review.html"},
    },
    {"title": "Story B", "tier": "A", "date": "2025-01-01", "event": "Talk B"},
]
(out / "compat-data.json").write_text(json.dumps(compat_data))
for subsite in ("", "/ja"):
    if subsite:
        (out / "ja").mkdir(exist_ok=True)
        shutil.copytree(out / "static", out / "ja/static", dirs_exist_ok=True)
    for mode in ("legacy", "modern", "mixed"):
        content = SimpleNamespace(_content="")
        settings = _resolve_settings(
            {
                "SITEURL": subsite,
                "DEFAULT_LANG": "ja" if subsite else "zh-TW",
                "TABULAR_COUNT_TEMPLATE": "",
                "TABULAR_GROUP_COUNT_TEMPLATE": "",
                "TABULAR_VIEWS": {"works": config},
            }
        )
        if mode != "modern":
            content._content = (
                '<div class="compat-cv">{% table compat-data.json '
                'fields="date,event,title" sort_by="date" sort_order="desc" '
                'group_by="date:year" group_summary_at="date:year" '
                'date_format="%m/%d" %}</div>'
                '<div class="compat-ranking">{% table compat-data.json '
                'fields="title,reviews" group_by="tier" '
                'group_summary_at="tier" %}</div>'
            )
        if mode != "legacy":
            content._content += (
                '{% table ../content/data/works.yaml view="works" id="works" %}'
            )
        _process_content(content, settings, out, {})
        old_assets = (
            f'<link rel="stylesheet" href="{subsite}'
            '/static/pelican_osm/css/osm-map.css">'
            f'<script src="{subsite}/static/pelican_osm/js/osm-map.js" defer></script>'
            if mode != "modern"
            else ""
        )
        for brand in ("main", "travlog"):
            path = out / subsite.lstrip("/") / f"compat-{brand}-{mode}.html"
            path.write_text(
                '<!doctype html><html lang="zh-tw"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<link rel="stylesheet" href="/attila.css">'
                + old_assets
                + f'<body class="site-{brand}"><main class="post-content">'
                + content._content
                + (osm_html if mode != "modern" else "")
                + "</main></body></html>"
            )
for size in (1000, 5000):
    data = [
        {
            "title": f"Work {i}",
            "status": "ongoing" if i % 2 else "completed",
            "rating": i % 6,
        }
        for i in range(size)
    ]
    content = render_view(
        data,
        {"fields": ["title", "rating"], "filters": {"status": {}}, "query_sync": True},
        table_id="perf",
    )
    (out / f"performance-{size}.html").write_text(
        head + "<body>" + content + "</body></html>"
    )
print(
    json.dumps(
        {
            "output": str(out),
            "osm_source": str(args.osm_source),
            "fixture_title": html.escape("OSM + tabular"),
        },
        ensure_ascii=False,
    )
)

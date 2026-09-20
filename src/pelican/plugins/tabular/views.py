"""Build-time validation and accessible, progressively enhanced database views."""

from __future__ import annotations

import datetime
import html
import json
import logging
import math
import re
from typing import Any

from .core import (
    cell_value,
    collapse_rows,
    extract_year,
    format_scalar,
    group_key_value,
)
from .rendering import render_table_body

log = logging.getLogger(__name__)
TONES = {"neutral", "blue", "green", "amber", "rose", "violet"}
TRANSLATIONS = {
    "en": {
        "search": "Search",
        "filters": "Filters",
        "clear": "Clear filters",
        "clear_search": "Clear search",
        "all": "Any",
        "from": "From",
        "to": "To",
        "sort": "Sort by",
        "direction": "Reverse sort direction",
        "count": "{shown} / {total} rows",
        "empty": "No matching entries.",
        "details": "Details",
        "range_error": "Start year must not exceed end year.",
        "updated": "Last updated",
        "legend": "Guide",
        "group": "rows",
    },
    "zh": {
        "search": "搜尋",
        "filters": "篩選",
        "clear": "清除選取",
        "clear_search": "清除搜尋",
        "all": "不限",
        "from": "起",
        "to": "迄",
        "sort": "排序",
        "direction": "切換排序方向",
        "count": "顯示 {shown} / {total} 筆",
        "empty": "沒有符合條件的資料。",
        "details": "詳細資料",
        "range_error": "起始年份不能晚於結束年份。",
        "updated": "最後更新",
        "legend": "說明",
        "group": "筆",
    },
    "ja": {
        "search": "検索",
        "filters": "絞り込み",
        "clear": "条件をクリア",
        "clear_search": "検索をクリア",
        "all": "すべて",
        "from": "開始",
        "to": "終了",
        "sort": "並び順",
        "direction": "並び順を反転",
        "count": "{total} 件中 {shown} 件",
        "empty": "該当するデータはありません。",
        "details": "詳細",
        "range_error": "開始年は終了年以前にしてください。",
        "updated": "最終更新",
        "legend": "説明",
        "group": "件",
    },
}


def text(value: Any) -> str:
    """A stable public value, separate from markup and localized labels."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return text(
            value.get("text")
            or value.get("label")
            or value.get("href")
            or value.get("url")
        )
    if isinstance(value, list):
        return " ".join(text(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return format_scalar(value)


def values(value: Any) -> list[str]:
    return [text(v) for v in value] if isinstance(value, list) else [text(value)]


def safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(v, str) or not v for v in value
    ):
        raise ValueError(f"{name} must be a list of non-empty field names")
    return list(dict.fromkeys(value))


def mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name} must be a mapping")
    return value


def sort_value(value: Any, kind: str) -> str | float | None:
    raw = text(value).strip()
    if not raw:
        return None
    if kind == "number":
        try:
            number = float(raw)
            return number if math.isfinite(number) else None
        except ValueError:
            return None
    if kind == "date":
        # ISO dates, year-month and bare years share one deterministic order.
        try:
            if re.fullmatch(r"\d{4}", raw):
                raw += "-01-01"
            elif re.fullmatch(r"\d{4}-\d{2}", raw):
                raw += "-01"
            date = datetime.datetime.fromisoformat(raw)
            if date.tzinfo is not None:
                date = date.astimezone(datetime.UTC)
            seconds = date.hour * 3600 + date.minute * 60 + date.second
            return date.toordinal() + (seconds + date.microsecond / 1_000_000) / 86400
        except ValueError:
            return None
    return raw.casefold()


def render_view(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    table_id: str,
    lang: str = "en",
    group_by: list[str] | None = None,
    group_summary_at: list[str] | None = None,
    aggregate: dict[str, str] | None = None,
) -> str:
    """Render a complete database without requiring Pelican initialization."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", table_id):
        raise ValueError(
            "view id must start with a letter and use letters, digits, _ or -"
        )
    if aggregate:
        raise ValueError(
            "interactive views do not support aggregate; use a plain table"
        )
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("table data must contain records")
    words = {
        **TRANSLATIONS.get(lang.lower().split("-")[0], TRANSLATIONS["en"]),
        **mapping(config.get("messages", {}), "messages"),
    }
    if any(not isinstance(v, str) for v in words.values()):
        raise ValueError("messages must contain strings")
    labels = mapping(config.get("field_labels", {}), "field_labels")
    known = list(dict.fromkeys(k for row in rows for k in row if not k.startswith("_")))
    fields = string_list(config.get("fields", known), "fields")
    hidden = set(string_list(config.get("hidden", []), "hidden"))
    fields = [f for f in fields if f not in hidden]
    if not fields:
        raise ValueError("a view needs at least one visible field")
    display = mapping(config.get("display", {}), "display")
    if display.get("layout", "responsive") not in ("responsive", "table"):
        raise ValueError("display.layout must be responsive or table")
    filters_expanded = display.get("filters_expanded", "auto")
    if not isinstance(filters_expanded, bool) and filters_expanded != "auto":
        raise ValueError("display.filters_expanded must be auto, true or false")
    title = display.get("title_field", fields[0])
    if title not in fields:
        raise ValueError("display.title_field must be a visible field")
    meta = string_list(display.get("meta_fields", fields[1:]), "meta_fields")
    if set(meta) - set(fields):
        raise ValueError("meta_fields must be visible fields")
    details = string_list(display.get("detail_fields", []), "detail_fields")
    search = string_list(config.get("search_fields", fields), "search_fields")
    sort_fields = string_list(config.get("sort_fields", fields), "sort_fields")
    initial_sort = config.get("sort_by") or ""
    if initial_sort and initial_sort not in sort_fields:
        sort_fields.append(initial_sort)
    direction = config.get("sort_order", "asc")
    if direction not in ("asc", "desc"):
        raise ValueError("sort_order must be asc or desc")
    group_by = group_by or []
    summaries = group_summary_at or []
    if summaries and (not group_by or group_by[: len(summaries)] != summaries):
        raise ValueError("group_summary_at must be a prefix of group_by")
    filters = mapping(config.get("filters", {}), "filters")
    field_types = mapping(config.get("field_types", {}), "field_types")
    if any(t not in ("text", "number", "date") for t in field_types.values()):
        raise ValueError("field_types must use text, number or date")
    query_sync = config.get("query_sync", False)
    if not isinstance(query_sync, bool):
        raise ValueError("query_sync must be true or false")
    query_prefix = config.get("query_prefix", table_id)
    if not isinstance(query_prefix, str) or (
        query_prefix and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", query_prefix)
    ):
        raise ValueError("query_prefix must be empty or a valid id")
    reserved = {"q", "sort", "order"}
    query_keys = set(reserved)
    options: dict[str, list[dict[str, str]]] = {}
    filter_specs: dict[str, dict[str, Any]] = {}
    for field, raw in filters.items():
        spec = mapping(raw, f"filters.{field}")
        control = spec.get("control", "chips")
        match = spec.get("match", "any")
        if control not in ("chips", "year_range") or match not in ("any", "all"):
            raise ValueError(f"invalid filter control/match for {field}")
        keys = [field] if control == "chips" else [f"{field}.from", f"{field}.to"]
        if any(k in query_keys for k in keys):
            raise ValueError(f"filter {field} conflicts with another query parameter")
        query_keys.update(keys)
        available = list(
            dict.fromkeys(v for row in rows for v in values(row.get(field)))
        )
        if control == "year_range":
            years = sorted(
                {
                    y
                    for row in rows
                    for v in values(row.get(field))
                    if (y := extract_year(v)) is not None
                }
            )
            filter_specs[field] = {"control": control, "years": years}
            continue
        raw_options = spec.get(
            "options", [{"value": v, "label": v or "—"} for v in available]
        )
        if not isinstance(raw_options, list):
            raise ValueError(f"options for {field} must be a list")
        parsed = []
        for opt in raw_options:
            opt = mapping(opt, f"options for {field}")
            if "value" not in opt or isinstance(opt["value"], (dict, list)):
                raise ValueError(f"option for {field} needs a scalar value")
            tone = opt.get("tone", "neutral")
            if tone not in TONES:
                raise ValueError(f"unsupported badge tone: {tone}")
            parsed.append(
                {
                    "value": text(opt["value"]),
                    "label": text(opt.get("label", opt["value"])) or "—",
                    "tone": tone,
                    "description": text(opt.get("description")),
                }
            )
        if len({o["value"] for o in parsed}) != len(parsed):
            raise ValueError(f"duplicate option value for {field}")
        missing = set(available) - {o["value"] for o in parsed}
        if "options" in spec and missing:
            log.warning(
                "pelican-tabular: values not listed in %s options: %s",
                field,
                ", ".join(sorted(missing)),
            )
        options[field] = parsed
        filter_specs[field] = {
            "control": control,
            "match": match,
            "values": [o["value"] for o in parsed],
        }
    presets = config.get("presets", [])
    if not isinstance(presets, list):
        raise ValueError("presets must be a list")
    for preset in presets:
        preset = mapping(preset, "preset")
        if not isinstance(preset.get("label"), str):
            raise ValueError("preset requires a label")
        for f, selected in mapping(preset.get("filters"), "preset.filters").items():
            if (
                f not in options
                or not isinstance(selected, list)
                or any(text(v) not in filter_specs[f]["values"] for v in selected)
            ):
                raise ValueError("presets must select existing chip filter values")
    selected_fields = set(fields + details + search + sort_fields + list(filters))
    types = {}
    for f in sort_fields:
        nonempty = [r.get(f) for r in rows if text(r.get(f)).strip()]
        inferred = "text"
        if nonempty and all(sort_value(v, "number") is not None for v in nonempty):
            inferred = "number"
        elif nonempty and all(sort_value(v, "date") is not None for v in nonempty):
            inferred = "date"
        types[f] = field_types.get(f, inferred)
    indexed = [{**row, "_tabular_index": i} for i, row in enumerate(rows)]
    if initial_sort:
        valid = [
            row
            for row in indexed
            if sort_value(row.get(initial_sort), types[initial_sort]) is not None
        ]
        missing_rows = [
            row
            for row in indexed
            if sort_value(row.get(initial_sort), types[initial_sort]) is None
        ]
        indexed = (
            sorted(
                valid,
                key=lambda row: (
                    sort_value(row.get(initial_sort), types[initial_sort]) or 0
                ),
                reverse=direction == "desc",
            )
            + missing_rows
        )
    if group_by:
        indexed = collapse_rows(indexed, group_by, {})
    records = []
    for row in indexed:
        public = {f: values(row.get(f)) for f in selected_fields}
        searchable = []
        for f in search:
            searchable.extend(public[f])
            searchable.extend(
                o["label"] for o in options.get(f, []) if o["value"] in public[f]
            )
        records.append(
            {
                "id": str(row["_tabular_index"]),
                "values": public,
                "search": " ".join(searchable).lower(),
                "group": [text(group_key_value(row, f)) for f in group_by],
                "sort": {f: sort_value(row.get(f), types[f]) for f in sort_fields},
            }
        )
    payload = {
        "records": records,
        "filters": filter_specs,
        "presets": [
            {"filters": {f: [text(v) for v in vs] for f, vs in p["filters"].items()}}
            for p in presets
        ],
        "sortFields": sort_fields,
        "sort": initial_sort,
        "order": direction,
        "querySync": query_sync,
        "queryPrefix": query_prefix,
        "filtersExpanded": filters_expanded,
        "words": words,
    }

    def esc(v: Any) -> str:
        return html.escape(str(v), quote=True)

    def label(f: str) -> str:
        return esc(labels.get(f, f))

    def button(caption: str, attrs: str = "") -> str:
        return f'<button type="button" {attrs}>{caption}</button>'

    def render_value(field: str, value: Any) -> str:
        if field not in options:
            return cell_value(value, date_format=config.get("date_format", "")) or "—"
        badges = []
        for raw in values(value):
            opt = next(
                (o for o in options[field] if o["value"] == raw),
                {"label": raw or "—", "tone": "neutral"},
            )
            badges.append(
                f'<span class="tabular-badge tabular-badge--{opt["tone"]}">'
                f"{esc(opt['label'])}</span>"
            )
        return '<span class="tabular-badges">' + "".join(badges) + "</span>"

    parts = [
        f'<section class="tabular-view" id="{table_id}" lang="{esc(lang)}"'
        f' data-layout="{esc(display.get("layout", "responsive"))}">',
        '<div class="tabular-controls" data-pagefind-ignore hidden>',
        '<div class="tabular-search-bar">',
        f'<label for="{table_id}-search">{esc(words["search"])}</label>',
        f'<input id="{table_id}-search" type="search" data-search'
        f' placeholder="{esc(words["search"])}" autocomplete="off">',
        button(esc(words["clear_search"]), "data-clear-search"),
        "</div>",
        '<div class="tabular-toolbar tabular-filter-actions">',
        button(
            f"{esc(words['filters'])} <span data-filter-count>0</span>",
            f'data-filter-toggle aria-expanded="false"'
            f' aria-controls="{table_id}-filters"',
        ),
        button(esc(words["clear"]), "data-clear"),
        "</div>",
        f'<div id="{table_id}-filters" class="tabular-filters" hidden>',
    ]
    for f, spec in filter_specs.items():
        parts.append(f'<fieldset data-filter="{esc(f)}"><legend>{label(f)}</legend>')
        if spec["control"] == "chips":
            parts.append(button(esc(words["all"]), 'data-any aria-pressed="true"'))
            for o in options[f]:
                parts.append(
                    button(
                        esc(o["label"]),
                        f'data-value="{esc(o["value"])}" aria-pressed="false"',
                    )
                )
        else:
            for endpoint in ("from", "to"):
                parts.append(
                    f"<label>{esc(words[endpoint])}"
                    f'<select data-range="{endpoint}"'
                    f' aria-label="{label(f)} {esc(words[endpoint])}">'
                    f'<option value="">{esc(words["all"])}</option>'
                )
                parts.extend(f'<option value="{y}">{y}</option>' for y in spec["years"])
                parts.append("</select></label>")
        parts.append("</fieldset>")
    parts.extend(
        [
            "</div>",
            '<p class="tabular-error" role="alert" data-error hidden></p>',
            '<div class="tabular-toolbar tabular-sort-controls">',
            f"<label>{esc(words['sort'])} "
            f'<select data-sort aria-label="{esc(words["sort"])}">',
            '<option value="">—</option>',
        ]
    )
    parts.extend(f'<option value="{esc(f)}">{label(f)}</option>' for f in sort_fields)
    parts.extend(
        [
            "</select></label>",
            button("↑", f'data-direction aria-label="{esc(words["direction"])}"'),
            "</div>",
            '<div class="tabular-presets">',
        ]
    )
    for i, preset in enumerate(presets):
        parts.append(
            button(esc(preset["label"]), f'data-preset="{i}" aria-pressed="false"')
        )
    parts.extend(
        [
            "</div></div>",
            '<div class="tabular-result-bar" data-pagefind-ignore>',
            '<p data-count role="status" aria-live="polite">'
            + esc(
                words["count"]
                .replace("{shown}", str(len(rows)))
                .replace("{total}", str(len(rows)))
            )
            + "</p>",
        ]
    )
    if config.get("updated_at"):
        parts.append(
            f"<p>{esc(words['updated'])} <time>{esc(config['updated_at'])}</time></p>"
        )
    parts.append("</div>")
    legend_fields = string_list(display.get("legend_fields", []), "legend_fields")
    if legend_fields:
        parts.append('<div class="tabular-legends">')
    for f in legend_fields:
        parts.append(
            f'<details class="tabular-legend" data-pagefind-ignore>'
            f"<summary>{label(f)} · "
            f"{esc(words['legend'])}</summary>"
        )
        for o in options.get(f, []):
            parts.append(
                f"<p>{esc(o['label'])} — {esc(o['description'] or o['label'])}</p>"
            )
        parts.append("</details>")
    if legend_fields:
        parts.append("</div>")
    parts.append(
        '<div class="tabular-table-scroll"><table class="tabular-table"><thead><tr>'
    )
    for f in fields:
        parts.append(
            f'<th scope="col" id="{table_id}-col-{fields.index(f)}"'
            f' data-column="{esc(f)}">{label(f)}</th>'
        )
    parts.append("</tr></thead><tbody>")

    def render_row(row: dict[str, Any]) -> str:
        rid = str(row["_tabular_index"])
        cells = [f'<tr class="tabular-row" data-row="{rid}">']
        for f in fields:
            css = (
                "tabular-title"
                if f == title
                else "tabular-meta"
                if f in meta
                else "tabular-desktop"
            )
            cells.append(
                f'<td class="{css}" data-field="{esc(f)}" data-label="{label(f)}" '
                f'headers="{table_id}-col-{fields.index(f)}">'
            )
            if f == title and details:
                cells.append(
                    button(
                        "+",
                        f'data-expand="{rid}" data-pagefind-ignore aria-expanded="true"'
                        f' aria-controls="{table_id}-detail-{rid}"'
                        f' aria-label="{esc(words["details"])}: '
                        f'{esc(text(row.get(title)))}"',
                    )
                )
            cells.extend([render_value(f, row.get(f)), "</td>"])
        cells.append("</tr>")
        if details:
            cells.append(
                f'<tr class="tabular-detail" data-detail="{rid}" '
                f'id="{table_id}-detail-{rid}">'
                f'<td colspan="{len(fields)}"><dl>'
            )
            for f in details:
                cells.append(
                    f"<div><dt>{label(f)}</dt>"
                    f"<dd>{render_value(f, row.get(f))}</dd></div>"
                )
            cells.append("</dl></td></tr>")
        return "".join(cells)

    parts.append(
        render_table_body(
            indexed,
            column_count=len(fields),
            render_row=render_row,
            group_summary_at=summaries,
            css_prefix="tabular",
            id_prefix=table_id + "-group-",
            group_count_template="{n} " + words["group"],
        )
    )
    parts.extend(
        [
            "</tbody></table></div>",
            f'<p class="tabular-empty" data-empty hidden>{esc(words["empty"])}</p>',
            '<script type="application/json" class="tabular-data">'
            + safe_json(payload)
            + "</script>",
            "</section>",
        ]
    )
    return "\n".join(parts)

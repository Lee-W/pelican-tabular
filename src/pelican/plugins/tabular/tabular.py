"""pelican-tabular plugin: embed data tables via {% table %} shortcode."""

from __future__ import annotations

import csv
import datetime
import json
import logging
import re
import shlex
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

import yaml
from pelican import signals
from pelican.contents import Article, Page

try:
    import markdown as _markdown

    _HAS_MARKDOWN = True
except ImportError:
    _markdown = None  # type: ignore[assignment]
    _HAS_MARKDOWN = False

log = logging.getLogger(__name__)

DEFAULT_SHORTCODE = "table"
DEFAULT_COUNT_TEMPLATE = "{n} rows"
BUILTIN_COUNT_TEMPLATES: dict[str, str] = {
    "zh": "{n} 筆資料",
    "ja": "{n} 件",
}
DEFAULT_GROUP_COUNT_TEMPLATE = "{n} rows"
BUILTIN_GROUP_COUNT_TEMPLATES: dict[str, str] = {
    "zh": "{n} 筆",
    "ja": "{n} 件",
}

# Internal field added by _collapse_rows; never shown as a data column.
_RESERVED = frozenset(["_places"])


# --- settings ----------------------------------------------------------------


def _resolve_count_template(pelican_settings: dict[str, Any]) -> str:
    if "TABULAR_COUNT_TEMPLATE" in pelican_settings:
        return pelican_settings["TABULAR_COUNT_TEMPLATE"]
    lang = pelican_settings.get("DEFAULT_LANG", "en").lower()
    return BUILTIN_COUNT_TEMPLATES.get(
        lang, BUILTIN_COUNT_TEMPLATES.get(lang.split("-")[0], DEFAULT_COUNT_TEMPLATE)
    )


def _resolve_group_count_template(pelican_settings: dict[str, Any]) -> str:
    if "TABULAR_GROUP_COUNT_TEMPLATE" in pelican_settings:
        return pelican_settings["TABULAR_GROUP_COUNT_TEMPLATE"]
    lang = pelican_settings.get("DEFAULT_LANG", "en").lower()
    primary = lang.split("-")[0]
    for key in (lang, primary):
        if key in BUILTIN_GROUP_COUNT_TEMPLATES:
            return BUILTIN_GROUP_COUNT_TEMPLATES[key]
    return DEFAULT_GROUP_COUNT_TEMPLATE


def _resolve_settings(pelican_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "shortcode": pelican_settings.get("TABULAR_SHORTCODE", DEFAULT_SHORTCODE),
        "fields": pelican_settings.get("TABULAR_FIELDS", []),
        "field_labels": pelican_settings.get("TABULAR_FIELD_LABELS", {}),
        "count_template": _resolve_count_template(pelican_settings),
        "group_count_template": _resolve_group_count_template(pelican_settings),
        "siteurl": pelican_settings.get("SITEURL", "").rstrip("/"),
    }


# --- data loading ------------------------------------------------------------


def _load_data_file(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    elif suffix == ".csv":
        reader = csv.DictReader(StringIO(text))
        data = list(reader)
    else:
        raise ValueError(f"Unsupported data file format: {path.suffix!r}")
    if not isinstance(data, list):
        raise TypeError(
            f"Expected a list of records in {path}, got {type(data).__name__}"
        )
    return data


# --- scalar helpers (ported from pelican-osm) --------------------------------


def _slugify(value: str) -> str:
    """Slug for an HTML id. Keeps letter chars (incl. CJK) and digits."""
    s = re.sub(r"\s+", "-", str(value).strip())
    out = [ch for ch in s if ch == "-" or ch.isalnum()]
    return "".join(out).lower() or "group"


def _format_scalar(value: Any) -> str:
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return str(value)


def _extract_year(value: Any) -> int | None:
    if isinstance(value, datetime.datetime):
        return value.year
    if isinstance(value, datetime.date):
        return value.year
    if isinstance(value, int):
        return value if 1000 <= value <= 9999 else None
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    if isinstance(value, list):
        for item in value:
            year = _extract_year(item)
            if year is not None:
                return year
    return None


def _extract_years(value: Any) -> list[int]:
    if isinstance(value, list):
        years: list[int] = []
        for item in value:
            year = _extract_year(item)
            if year is not None:
                years.append(year)
        return years
    year = _extract_year(value)
    return [year] if year is not None else []


def _aggregate_field(op: str, field: str, places: list[dict[str, Any]]) -> Any:
    if op == "year":
        seen: set[int] = set()
        ordered: list[int] = []
        for p in places:
            for year in _extract_years(p.get(field)):
                if year not in seen:
                    seen.add(year)
                    ordered.append(year)
        ordered.sort()
        return ", ".join(str(y) for y in ordered)
    log.warning("pelican-tabular: unknown aggregate op %r for field %r", op, field)
    return ""


# --- kwarg parsers -----------------------------------------------------------


def _parse_csv_kwarg(raw: str) -> list[str]:
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_aggregate_kwarg(raw: str) -> dict[str, str]:
    spec: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        field, _, op = part.partition(":")
        spec[field.strip()] = op.strip()
    return spec


# --- {filename} resolution ---------------------------------------------------


def _resolve_filename_url(url: str, article_url_map: dict[str, str]) -> str:
    """Resolve a ``{filename}path/to/post.md`` reference to an absolute URL.

    Preserves ``#fragment`` suffixes. Returns the input unchanged if it does
    not start with ``{filename}``.
    """
    if not url.startswith("{filename}"):
        return url
    path_part = url[len("{filename}") :].lstrip("/")
    fragment = ""
    if "#" in path_part:
        path_part, fragment = path_part.split("#", 1)
        fragment = "#" + fragment
    resolved = article_url_map.get(path_part)
    if resolved is None:
        log.warning("pelican-tabular: could not resolve {filename} URL: %s", url)
        return url
    return resolved + fragment


def _resolve_value(value: Any, article_url_map: dict[str, str]) -> Any:
    """Recursively resolve ``{filename}`` references in any YAML value."""
    if isinstance(value, str):
        return _resolve_filename_url(value, article_url_map)
    if isinstance(value, dict):
        return {k: _resolve_value(v, article_url_map) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, article_url_map) for item in value]
    return value


def _resolve_rows(
    rows: list[dict[str, Any]], article_url_map: dict[str, str]
) -> list[dict[str, Any]]:
    return [
        {k: _resolve_value(v, article_url_map) for k, v in row.items()} for row in rows
    ]


# --- grouping / collapsing (ported from pelican-osm) ------------------------


def _collapse_rows(
    rows: list[dict[str, Any]],
    group_by: list[str],
    aggregate: dict[str, str],
) -> list[dict[str, Any]]:
    """Group rows by ``group_by`` fields.

    No-aggregate mode: rows are reordered so that rows sharing a group-key
    tuple are contiguous, preserving first-appearance order. Each row gets
    ``_places: [self]`` so summary header count math works.

    Aggregate mode: rows sharing a group key are collapsed into one merged
    row. ``aggregate`` maps field names to ops (currently only ``year``).
    For non-aggregate fields, the first non-empty value wins.
    """
    order: list[tuple] = []
    if not aggregate:
        buckets: dict[tuple, list[dict[str, Any]]] = {}
        for row in rows:
            key = tuple(row.get(g, "") for g in group_by)
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(row)
        return [{**r, "_places": [r]} for key in order for r in buckets[key]]

    collapsed: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(g, "") for g in group_by)
        if key not in collapsed:
            collapsed[key] = {**row, "_places": [row]}
            order.append(key)
            continue
        existing = collapsed[key]
        existing["_places"].append(row)
        for k, v in row.items():
            if k in aggregate:
                continue
            if not existing.get(k) and v:
                existing[k] = v

    result: list[dict[str, Any]] = []
    for key in order:
        row = collapsed[key]
        for field, op in aggregate.items():
            row[field] = _aggregate_field(op, field, row["_places"])
        result.append(row)
    return result


# --- shortcode argument parsing ----------------------------------------------


def _parse_shortcode_args(raw: str) -> tuple[str, dict[str, str]]:
    """Return (file_path, kwargs) from the shortcode body."""
    tokens = shlex.split(raw.strip())
    if not tokens:
        raise ValueError("{% table %} shortcode requires a file path argument")
    file_path = tokens[0]
    kwargs: dict[str, str] = {}
    for token in tokens[1:]:
        if "=" in token:
            key, _, val = token.partition("=")
            kwargs[key.strip()] = val.strip().strip('"').strip("'")
    return file_path, kwargs


# --- HTML rendering ----------------------------------------------------------


def _detect_columns(rows: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for row in rows:
        for k in row:
            if k not in _RESERVED:
                seen[k] = None
    return list(seen)


def _cell_value(value: Any) -> str:
    """Render a cell value as HTML.

    Supports plain scalars, ``{text, href}`` link dicts, and lists of either.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        href = value.get("href") or value.get("url", "")
        text = value.get("text") or value.get("label") or href
        return f'<a href="{href}">{text}</a>' if href else str(text)
    if isinstance(value, list):
        if len(value) > 1:
            items = "".join(f"<li>{_cell_value(item)}</li>" for item in value)
            return f'<ul style="margin:0;padding-left:1.2em">{items}</ul>'
        return _cell_value(value[0]) if value else ""
    return _format_scalar(value)


def _render_table_html(
    rows: list[dict[str, Any]],
    *,
    fields: list[str],
    field_labels: dict[str, str],
    hidden: set[str],
    sort_by: str | None,
    sort_order: str,
    count_template: str,
    group_by: list[str],
    group_summary_at: list[str],
    aggregate: dict[str, str],
    group_count_template: str,
) -> str:
    if sort_by:
        reverse = sort_order.lower() == "desc"
        rows = sorted(rows, key=lambda r: r.get(sort_by) or "", reverse=reverse)

    if group_by:
        if group_summary_at and group_by[: len(group_summary_at)] != group_summary_at:
            log.warning(
                "pelican-tabular: group_summary_at must be a prefix of group_by; ignoring"
            )
            group_summary_at = []
        rows = _collapse_rows(rows, group_by, aggregate)
    else:
        rows = [{**r, "_places": [r]} for r in rows]
        if group_summary_at:
            log.warning("pelican-tabular: group_summary_at requires group_by; ignoring")
            group_summary_at = []

    summary_set = set(group_summary_at)
    all_keys = fields if fields else _detect_columns(rows)
    columns = [
        (k, field_labels.get(k, k))
        for k in all_keys
        if k not in hidden and k not in summary_set
    ]
    if not columns:
        return ""

    col_count = len(columns)
    count_text = count_template.replace("{n}", str(len(rows)))

    # Use pelican-osm's place-list classes so osm-map.js handles interactive
    # sorting and styling automatically.
    parts: list[str] = ['<div class="osm-place-list-wrapper">']
    parts.append('<table class="osm-place-list">')
    parts.append("<thead><tr>")
    for _, label in columns:
        parts.append(f"<th>{label}</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")

    if group_summary_at:
        # Pre-compute place counts at every prefix depth so each header can
        # display its own subtotal regardless of how many rows it spans.
        prefix_counts: dict[tuple, int] = defaultdict(int)
        for row in rows:
            n = len(row.get("_places") or [row])
            key = tuple(row.get(f, "") for f in group_summary_at)
            for d in range(len(key)):
                prefix_counts[key[: d + 1]] += n

        used_ids: set[str] = set()

        def _anchor_id(prefix: tuple) -> str:
            base = "osm-group--" + "--".join(_slugify(v) for v in prefix)
            anchor = base
            i = 2
            while anchor in used_ids:
                anchor = f"{base}-{i}"
                i += 1
            used_ids.add(anchor)
            return anchor

        prev_key: tuple = ()
        for row in rows:
            cur_key = tuple(row.get(f, "") for f in group_summary_at)
            for depth, val in enumerate(cur_key):
                prefix = cur_key[: depth + 1]
                prev_prefix = (
                    prev_key[: depth + 1] if len(prev_key) >= depth + 1 else None
                )
                if prefix == prev_prefix:
                    continue
                count_html = ""
                if group_count_template:
                    n_group = prefix_counts[prefix]
                    count_html = (
                        f'<span class="osm-group-count">'
                        f"{group_count_template.replace('{n}', str(n_group))}"
                        f"</span>"
                    )
                anchor_id = _anchor_id(prefix)
                parts.append(
                    f'<tr class="osm-group-header osm-group-header--depth-{depth}"'
                    f' data-depth="{depth}" id="{anchor_id}">'
                    f'<td colspan="{col_count}">'
                    f'<span class="osm-group-header-toggle" aria-hidden="true">▾</span>'
                    f'<strong class="osm-group-header-title">{val}</strong>'
                    f"{count_html}"
                    f"</td></tr>"
                )
            prev_key = cur_key
            parts.append("<tr>")
            for key, _ in columns:
                parts.append(f"<td>{_cell_value(row.get(key))}</td>")
            parts.append("</tr>")
    else:
        for row in rows:
            parts.append("<tr>")
            for key, _ in columns:
                parts.append(f"<td>{_cell_value(row.get(key))}</td>")
            parts.append("</tr>")

    parts.append("</tbody></table>")
    parts.append("</div>")
    # Count div is outside the wrapper so osm-map.js's wrapper.querySelector()
    # cannot find and overwrite it — we pre-fill it server-side instead.
    parts.append(f'<div class="osm-place-list-count">{count_text}</div>')
    return "\n".join(parts)


# --- shortcode substitution --------------------------------------------------


def _make_pattern(shortcode: str) -> re.Pattern[str]:
    return re.compile(
        r"\{%-?\s+" + re.escape(shortcode) + r"\s+(.*?)-?\s*%\}",
        re.DOTALL,
    )


def _replace_match(
    match: re.Match[str],
    *,
    data_root: Path,
    settings: dict[str, Any],
    article_url_map: dict[str, str],
) -> str:
    raw = match.group(1)
    try:
        file_path, kwargs = _parse_shortcode_args(raw)
    except ValueError as exc:
        log.error("pelican-tabular: %s", exc)
        return f'<p class="tabular-error">{exc}</p>'

    full_path = data_root / file_path
    if not full_path.exists():
        log.error("pelican-tabular: data file not found: %s", full_path)
        return f'<p class="tabular-error">Data file not found: {file_path}</p>'

    try:
        rows = _load_data_file(full_path)
    except Exception as exc:
        log.error("pelican-tabular: failed to load %s: %s", full_path, exc)
        return f'<p class="tabular-error">Failed to load {file_path}: {exc}</p>'

    rows = _resolve_rows(rows, article_url_map)

    hidden_raw = kwargs.get("hidden", "")
    hidden = {h.strip() for h in hidden_raw.split(",") if h.strip()}

    fields_raw = kwargs.get("fields", "")
    fields = [f.strip() for f in fields_raw.split(",") if f.strip()] or list(
        settings["fields"]
    )

    sort_by = kwargs.get("sort_by")
    sort_order = kwargs.get("sort_order", "asc")

    group_by = _parse_csv_kwarg(kwargs.get("group_by", ""))
    group_summary_at = _parse_csv_kwarg(kwargs.get("group_summary_at", ""))
    aggregate = _parse_aggregate_kwarg(kwargs.get("aggregate", ""))
    per_labels = _parse_aggregate_kwarg(kwargs.get("field_labels", ""))
    merged_labels = {**settings["field_labels"], **per_labels}

    return _render_table_html(
        rows,
        fields=fields,
        field_labels=merged_labels,
        hidden=hidden,
        sort_by=sort_by,
        sort_order=sort_order,
        count_template=settings["count_template"],
        group_by=group_by,
        group_summary_at=group_summary_at,
        aggregate=aggregate,
        group_count_template=settings["group_count_template"],
    )


def _process_content(
    content: Article | Page,
    settings: dict[str, Any],
    data_root: Path,
    article_url_map: dict[str, str],
) -> None:
    if not content._content:
        return
    pattern = _make_pattern(settings["shortcode"])
    if not pattern.search(content._content):
        return
    content._content = pattern.sub(
        lambda m: _replace_match(
            m, data_root=data_root, settings=settings, article_url_map=article_url_map
        ),
        content._content,
    )


# --- Markdown shortcode protection -------------------------------------------

if _HAS_MARKDOWN:
    from markdown.extensions import Extension
    from markdown.preprocessors import Preprocessor

    _SHORTCODE_RE = re.compile(r"\{%-?\s+\w[\w_-]*\b.*?-?\s*%\}", re.DOTALL)

    class _ShortcodePreprocessor(Preprocessor):
        def run(self, lines: list[str]) -> list[str]:
            text = "\n".join(lines)
            text = _SHORTCODE_RE.sub(
                lambda m: self.md.htmlStash.store(m.group(0)), text
            )
            return text.split("\n")

    class _ShortcodePreserveExtension(Extension):
        def extendMarkdown(self, md: Any) -> None:
            # Priority 25: after normalize_whitespace (30), which strips STX/ETX
            # control chars that htmlStash placeholders rely on, and before
            # html_block (20) so shortcodes are stashed before block processing.
            md.preprocessors.register(
                _ShortcodePreprocessor(md), "tabular_shortcode_preserve", 25
            )

    def _register_markdown_extension(pelican: Any) -> None:
        md_cfg = pelican.settings.setdefault("MARKDOWN", {})
        extensions = md_cfg.setdefault("extensions", [])
        if not any(isinstance(e, _ShortcodePreserveExtension) for e in extensions):
            extensions.append(_ShortcodePreserveExtension())

else:

    def _register_markdown_extension(pelican: Any) -> None:  # type: ignore[misc]
        pass


# --- plugin lifecycle --------------------------------------------------------

_settings: dict[str, Any] | None = None
_data_root: Path | None = None
_content_path: Path | None = None
_article_url_map: dict[str, str] = {}


def _init(pelican: Any) -> None:
    global _settings, _data_root, _content_path, _article_url_map
    _settings = _resolve_settings(pelican.settings)
    _article_url_map = {}

    raw_path = pelican.settings.get("PATH", "content")
    content_path = Path(raw_path)
    if not content_path.is_absolute():
        conf_file = pelican.settings.get("pelicanconf")
        if conf_file:
            content_path = Path(conf_file).parent / raw_path
        content_path = content_path.resolve()
    _content_path = content_path
    _data_root = content_path

    _register_markdown_extension(pelican)


def _process_article(content: Article | Page) -> None:
    if _settings is None or _data_root is None or _content_path is None:
        return

    # Build URL map incrementally so shortcodes can resolve {filename} references
    # to articles processed earlier in the same build.
    src = getattr(content, "source_path", None)
    url = getattr(content, "url", None)
    if src and url:
        abs_url = _settings["siteurl"] + "/" + url.lstrip("/")
        _article_url_map[src] = abs_url
        try:
            rel = Path(src).relative_to(_content_path)
            _article_url_map[str(rel)] = abs_url
        except ValueError:
            pass

    _process_content(content, _settings, _data_root, _article_url_map)


def register() -> None:
    signals.initialized.connect(_init)
    signals.content_object_init.connect(_process_article)

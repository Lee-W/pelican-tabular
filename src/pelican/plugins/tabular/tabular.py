"""pelican-tabular plugin: embed data tables via {% table %} shortcode."""

from __future__ import annotations

import csv
import datetime
import html
import json
import logging
import re
import shlex
import string
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from pelican.contents import Article, Page

from pelican import signals

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
        return str(pelican_settings["TABULAR_COUNT_TEMPLATE"])
    lang = pelican_settings.get("DEFAULT_LANG", "en").lower()
    return BUILTIN_COUNT_TEMPLATES.get(
        lang, BUILTIN_COUNT_TEMPLATES.get(lang.split("-")[0], DEFAULT_COUNT_TEMPLATE)
    )


def _resolve_group_count_template(pelican_settings: dict[str, Any]) -> str:
    if "TABULAR_GROUP_COUNT_TEMPLATE" in pelican_settings:
        return str(pelican_settings["TABULAR_GROUP_COUNT_TEMPLATE"])
    lang = pelican_settings.get("DEFAULT_LANG", "en").lower()
    primary = lang.split("-")[0]
    for key in (lang, primary):
        if key in BUILTIN_GROUP_COUNT_TEMPLATES:
            return BUILTIN_GROUP_COUNT_TEMPLATES[key]
    return DEFAULT_GROUP_COUNT_TEMPLATE


DEFAULT_REF_TEXT_FIELD = "name"
# Marker form (``?mlat=&mlon=``) rather than a bare ``#map=`` centre: the
# former drops a pin on the place, the latter only centres the viewport and
# leaves the reader guessing which building is meant.
DEFAULT_REF_HREF_TEMPLATE = (
    "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
)


def _resolve_settings(pelican_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "shortcode": pelican_settings.get("TABULAR_SHORTCODE", DEFAULT_SHORTCODE),
        "fields": pelican_settings.get("TABULAR_FIELDS", []),
        "field_labels": pelican_settings.get("TABULAR_FIELD_LABELS", {}),
        "count_template": _resolve_count_template(pelican_settings),
        "group_count_template": _resolve_group_count_template(pelican_settings),
        "date_format": pelican_settings.get("TABULAR_DATE_FORMAT", ""),
        "siteurl": pelican_settings.get("SITEURL", "").rstrip("/"),
        "ref_text_field": pelican_settings.get(
            "TABULAR_REF_TEXT_FIELD", DEFAULT_REF_TEXT_FIELD
        ),
        "ref_href_template": pelican_settings.get(
            "TABULAR_REF_HREF_TEMPLATE", DEFAULT_REF_HREF_TEMPLATE
        ),
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


def _format_scalar(value: Any, date_format: str = "") -> str:
    if isinstance(value, (datetime.date, datetime.datetime)):
        if date_format:
            return value.strftime(date_format)
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


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(round(value, 2))


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
    if op == "count":
        return sum(1 for p in places if p.get(field) not in (None, ""))
    if op in ("sum", "avg", "min", "max"):
        raw = (_numeric_value(p.get(field)) for p in places)
        values = [v for v in raw if v is not None]
        if not values:
            return ""
        if op == "sum":
            return _format_number(sum(values))
        if op == "avg":
            return _format_number(sum(values) / len(values))
        if op == "min":
            return _format_number(min(values))
        return _format_number(max(values))
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


# --- cross-file references (``<field>_ref``) ---------------------------------
#
# A field named ``<name>_ref`` with a string value ``"<path>#<id>"`` lets a
# data row point at a single record in another YAML file instead of
# duplicating that record's data locally. ``<path>`` is resolved relative to
# Pelican's content root (``_content_path`` in ``_init``, threaded through as
# ``content_path`` below) — not the (possibly different) ``TABULAR_DATA_ROOT``
# that the row's own file was loaded from. This keeps the reference portable:
# it reads the same regardless of which data root the referencing table uses.
#
# The referenced file may be either pelican-osm's locations-based shape
# (a ``locations:`` list of dicts, each optionally carrying an ``id``) or a
# bare top-level list of dicts. ``<id>`` is matched against each candidate's
# ``id`` field first, falling back to its ``name`` field, mirroring
# pelican-osm's own ``#fragment`` lookup semantics so authors only need to
# learn one convention.
#
# Resolution never fails the build: a missing file, an unresolvable id, or a
# malformed YAML document all degrade to showing the raw ``"<path>#<id>"``
# string (with a ``log.warning``) rather than raising.
#
# ``ref_href_template``/``TABULAR_REF_HREF_TEMPLATE`` may hold a ``|``-
# separated chain of templates rather than a single one — real place data is
# often inconsistent about which fields it has (e.g. some records carry a
# stable OSM node id, older ones only have raw lat/lon). Templates are tried
# in order; the first one whose placeholders are *all* present and non-empty
# in the resolved record wins. This is deliberate: silently filling a missing
# placeholder with "" (as a plain ``str.format_map`` would) produces a
# malformed-but-plausible-looking URL, which is worse than falling through to
# a template that actually fits the data. ``|`` was chosen as the separator
# because it practically never appears literally in a URL template (and
# would be percent-encoded as ``%7C`` if it legitimately needed to).

_REF_SUFFIX = "_ref"
_REF_HREF_TEMPLATE_SEP = "|"


def _load_ref_file(
    path: Path, cache: dict[Path, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Load a ref-target YAML file, memoized in ``cache`` for this build.

    Supports pelican-osm's locations-based shape (``{"locations": [...]}``)
    and a bare top-level list of dicts.
    """
    resolved = path.resolve()
    if resolved in cache:
        return cache[resolved]

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    if isinstance(data, dict) and "locations" in data:
        items = data.get("locations") or []
        if not isinstance(items, list):
            raise TypeError(f"'locations' in {path} is not a list")
    elif isinstance(data, list):
        items = data
    else:
        raise TypeError(
            f"Expected a list or a 'locations:' mapping in {path}, "
            f"got {type(data).__name__}"
        )

    result = [item for item in items if isinstance(item, dict)]
    cache[resolved] = result
    return result


def _find_ref_item(items: list[dict[str, Any]], ref_id: str) -> dict[str, Any] | None:
    for item in items:
        if str(item.get("id", "")) == ref_id:
            return item
    for item in items:
        if str(item.get("name", "")) == ref_id:
            return item
    return None


def _format_ref_href(template: str, item: dict[str, Any]) -> str:
    """``str.format_map`` against ``item``, treating missing keys as ''.

    Missing/unset keys degrade to an empty string instead of raising, so an
    href template referencing a field the target happens to lack (e.g. no
    ``lon``) yields a harmless empty href rather than crashing the build.
    Callers that need to *avoid* ever emitting such a partially-filled href
    should check ``_template_is_applicable`` first (``_resolve_ref_href``
    does this for the whole fallback chain).
    """

    class _SafeDict(dict[str, Any]):
        def __missing__(self, key: str) -> str:
            return ""

    return template.format_map(_SafeDict(item))


def _split_ref_href_templates(raw: str) -> list[str]:
    """Split a ``ref_href_template`` value into its fallback chain.

    Templates are separated by ``|`` (see the module comment above
    ``_REF_SUFFIX`` for why). Blank segments (e.g. a trailing separator) are
    dropped. A single template with no ``|`` yields a one-element list, so
    the existing single-template call sites keep working unchanged.
    """
    return [t for t in raw.split(_REF_HREF_TEMPLATE_SEP) if t.strip()]


def _template_fields(template: str) -> list[str]:
    """Return the distinct ``{placeholder}`` field names in ``template``.

    Deduplicated, first-appearance order preserved. A template may legitimately
    repeat a placeholder — an OpenStreetMap marker URL uses ``{lat}``/``{lon}``
    twice, once for the pin and once for the map centre — and the applicability
    check would otherwise test the same field several times per template.
    """
    return list(
        dict.fromkeys(
            field_name
            for _, field_name, _, _ in string.Formatter().parse(template)
            if field_name
        )
    )


def _template_is_applicable(template: str, item: dict[str, Any]) -> bool:
    """True if every placeholder in ``template`` is present and non-empty."""
    for field in _template_fields(template):
        value = item.get(field)
        if value is None or value == "":
            return False
    return True


def _resolve_ref_href(templates: list[str], item: dict[str, Any]) -> str:
    """Try each template in order; return the first fully-applicable one.

    Returns ``""`` if no template's placeholders are all satisfied — callers
    treat that as "render plain text, no link" rather than emitting a
    malformed href with empty placeholder gaps.
    """
    for template in templates:
        if _template_is_applicable(template, item):
            return _format_ref_href(template, item)
    return ""


def _resolve_ref_value(
    raw_ref: str,
    *,
    content_path: Path,
    cache: dict[Path, list[dict[str, Any]]],
    text_field: str,
    href_template: str,
    field_name: str,
    row_index: int,
) -> Any:
    if "#" not in raw_ref:
        log.warning(
            "pelican-tabular: ref %r in field %r (row %d) is missing "
            "'#<id>'; showing raw value",
            raw_ref,
            field_name,
            row_index,
        )
        return raw_ref

    rel_path, _, ref_id = raw_ref.partition("#")
    target_path = content_path / rel_path

    if not target_path.exists():
        log.warning(
            "pelican-tabular: ref target file not found: %s "
            "(from %r in field %r, row %d)",
            target_path,
            raw_ref,
            field_name,
            row_index,
        )
        return raw_ref

    try:
        items = _load_ref_file(target_path, cache)
    except Exception as exc:
        log.warning(
            "pelican-tabular: failed to load ref target %s "
            "(from %r in field %r, row %d): %s",
            target_path,
            raw_ref,
            field_name,
            row_index,
            exc,
        )
        return raw_ref

    item = _find_ref_item(items, ref_id)
    if item is None:
        log.warning(
            "pelican-tabular: ref id %r not found in %s (field %r, row %d)",
            ref_id,
            target_path,
            field_name,
            row_index,
        )
        return raw_ref

    text = item.get(text_field, item.get("name", ref_id))
    templates = _split_ref_href_templates(href_template)
    href = _resolve_ref_href(templates, item)
    if not href:
        return text
    return {"text": text, "href": href}


def _resolve_ref_rows(
    rows: list[dict[str, Any]],
    *,
    content_path: Path,
    cache: dict[Path, list[dict[str, Any]]],
    text_field: str,
    href_template: str,
) -> list[dict[str, Any]]:
    resolved_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        new_row = dict(row)
        for key in list(new_row.keys()):
            if not key.endswith(_REF_SUFFIX):
                continue
            value = new_row[key]
            if not isinstance(value, str):
                continue
            target_field = key[: -len(_REF_SUFFIX)]
            del new_row[key]
            new_row[target_field] = _resolve_ref_value(
                value,
                content_path=content_path,
                cache=cache,
                text_field=text_field,
                href_template=href_template,
                field_name=key,
                row_index=i,
            )
        resolved_rows.append(new_row)
    return resolved_rows


# --- grouping / collapsing (ported from pelican-osm) ------------------------


def _field_transform(token: str) -> tuple[str, str | None]:
    """Split a ``group_by`` token into ``(field, transform)``.

    A bare ``"date"`` groups by the raw value; ``"date:year"`` groups by a
    derived value. Currently the only transform is ``year`` (extracts the
    year from a date/datetime/year-like value via ``_extract_year``).
    """
    if ":" in token:
        field, _, transform = token.partition(":")
        return field.strip(), transform.strip()
    return token.strip(), None


def _group_key_value(row: dict[str, Any], token: str) -> Any:
    field, transform = _field_transform(token)
    if transform == "year":
        year = _extract_year(row.get(field))
        return year if year is not None else ""
    return row.get(field, "")


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
    order: list[tuple[str, ...]] = []
    if not aggregate:
        buckets: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in rows:
            key = tuple(_group_key_value(row, g) for g in group_by)
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(row)
        return [{**r, "_places": [r]} for key in order for r in buckets[key]]

    collapsed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(_group_key_value(row, g) for g in group_by)
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


def _cell_value(
    value: Any, *, date_format: str = "", aria_label: str | None = None
) -> str:
    """Render a cell value as HTML.

    Supports plain scalars, ``{text, href}`` link dicts, and lists of either.
    When ``aria_label`` is set, link elements get an ``aria-label`` so that
    icon-only link text (e.g. an emoji) still has an accessible name.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        href = value.get("href") or value.get("url", "")
        text = value.get("text") or value.get("label") or href
        if href:
            safe_href = quote(str(href), safe=":/?#[]@!$&'()*+,;=")
            safe_text = html.escape(str(text))
            aria = f' aria-label="{html.escape(str(aria_label))}"' if aria_label else ""
            return f'<a href="{safe_href}"{aria}>{safe_text}</a>'
        return html.escape(str(text))
    if isinstance(value, list):
        if len(value) > 1:
            items = "".join(
                "<li>"
                + _cell_value(item, date_format=date_format, aria_label=aria_label)
                + "</li>"
                for item in value
            )
            return f'<ul style="margin:0;padding-left:1.2em">{items}</ul>'
        return (
            _cell_value(value[0], date_format=date_format, aria_label=aria_label)
            if value
            else ""
        )
    return html.escape(_format_scalar(value, date_format))


def _sort_key(value: Any) -> tuple[int, Any]:
    """Bucket a cell value by comparable type so sorting never raises on a
    column with mixed types (e.g. some rows missing the field, others int
    vs str). Buckets sort numbers, then dates, then everything else
    (strings and None) so cross-type comparisons never happen.
    """
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return (1, value)
    if value is None:
        return (2, "")
    return (2, str(value))


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
    date_format: str = "",
    aria_columns: set[str] | None = None,
) -> str:
    aria_columns = aria_columns or set()
    if sort_by:
        reverse = sort_order.lower() == "desc"
        rows = sorted(rows, key=lambda r: _sort_key(r.get(sort_by)), reverse=reverse)

    if group_by:
        if group_summary_at and group_by[: len(group_summary_at)] != group_summary_at:
            log.warning(
                "pelican-tabular: group_summary_at must be a prefix of"
                " group_by; ignoring"
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

    used_ids: set[str] = set()

    def _anchor_id(prefix: str) -> str:
        anchor = prefix
        i = 2
        while anchor in used_ids:
            anchor = f"{prefix}-{i}"
            i += 1
        used_ids.add(anchor)
        return anchor

    # Use pelican-osm's place-list classes so osm-map.js handles interactive
    # sorting and styling automatically.
    parts: list[str] = ['<div class="osm-place-list-wrapper">']
    parts.append('<table class="osm-place-list">')
    parts.append("<thead><tr>")
    for _col_key, label in columns:
        col_anchor = _anchor_id("osm-col--" + _slugify(label))
        parts.append(f'<th id="{col_anchor}" scope="col">{html.escape(label)}</th>')
    parts.append("</tr></thead>")
    parts.append("<tbody>")

    if group_summary_at:
        # Pre-compute place counts at every prefix depth so each header can
        # display its own subtotal regardless of how many rows it spans.
        prefix_counts: dict[tuple[str, ...], int] = defaultdict(int)
        for row in rows:
            n = len(row.get("_places") or [row])
            key = tuple(_group_key_value(row, f) for f in group_summary_at)
            for d in range(len(key)):
                prefix_counts[key[: d + 1]] += n

        prev_key: tuple[str, ...] = ()
        for row in rows:
            cur_key = tuple(_group_key_value(row, f) for f in group_summary_at)
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
                anchor_id = _anchor_id(
                    "osm-group--" + "--".join(_slugify(v) for v in prefix)
                )
                parts.append(
                    f'<tr class="osm-group-header osm-group-header--depth-{depth}"'
                    f' data-depth="{depth}" id="{anchor_id}">'
                    f'<td colspan="{col_count}">'
                    f'<span class="osm-group-header-toggle" aria-hidden="true">▾</span>'
                    '<strong class="osm-group-header-title">'
                    f"{html.escape(str(val))}</strong>"
                    f"{count_html}"
                    f"</td></tr>"
                )
            prev_key = cur_key
            parts.append("<tr>")
            for col_key, col_label in columns:
                aria = col_label if col_key in aria_columns else None
                cell = _cell_value(
                    row.get(col_key), date_format=date_format, aria_label=aria
                )
                parts.append(f"<td>{cell}</td>")
            parts.append("</tr>")
    else:
        for row in rows:
            parts.append("<tr>")
            for col_key, col_label in columns:
                aria = col_label if col_key in aria_columns else None
                cell = _cell_value(
                    row.get(col_key), date_format=date_format, aria_label=aria
                )
                parts.append(f"<td>{cell}</td>")
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
    content_path: Path,
    settings: dict[str, Any],
    article_url_map: dict[str, str],
    ref_cache: dict[Path, list[dict[str, Any]]],
) -> str:
    raw = match.group(1)
    try:
        file_path, kwargs = _parse_shortcode_args(raw)
    except ValueError as exc:
        log.error("pelican-tabular: %s", exc)
        return f'<p class="tabular-error">{html.escape(str(exc))}</p>'

    full_path = data_root / file_path
    if not full_path.exists():
        log.error("pelican-tabular: data file not found: %s", full_path)
        escaped = html.escape(str(file_path))
        return f'<p class="tabular-error">Data file not found: {escaped}</p>'

    try:
        rows = _load_data_file(full_path)
    except Exception as exc:
        log.error("pelican-tabular: failed to load %s: %s", full_path, exc)
        esc_path = html.escape(str(file_path))
        esc_exc = html.escape(str(exc))
        return f'<p class="tabular-error">Failed to load {esc_path}: {esc_exc}</p>'

    rows = _resolve_rows(rows, article_url_map)

    ref_text_field = kwargs.get("ref_text_field") or settings["ref_text_field"]
    ref_href_template = kwargs.get("ref_href_template") or settings["ref_href_template"]
    rows = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache=ref_cache,
        text_field=ref_text_field,
        href_template=ref_href_template,
    )

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

    date_format = kwargs.get("date_format") or settings["date_format"]
    aria_columns = set(_parse_csv_kwarg(kwargs.get("aria_columns", "")))

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
        date_format=date_format,
        aria_columns=aria_columns,
    )


def _process_content(
    content: Article | Page,
    settings: dict[str, Any],
    data_root: Path,
    article_url_map: dict[str, str],
    content_path: Path | None = None,
    ref_cache: dict[Path, list[dict[str, Any]]] | None = None,
) -> None:
    if not content._content:
        return
    pattern = _make_pattern(settings["shortcode"])
    if not pattern.search(content._content):
        return
    # ``content_path`` is the basis for ``<field>_ref`` target paths; it
    # defaults to ``data_root`` (matching ``_init``'s own default) so callers
    # that don't use refs, including existing tests, need not pass it.
    resolved_content_path = content_path if content_path is not None else data_root
    resolved_ref_cache: dict[Path, list[dict[str, Any]]] = (
        ref_cache if ref_cache is not None else {}
    )
    content._content = pattern.sub(
        lambda m: _replace_match(
            m,
            data_root=data_root,
            content_path=resolved_content_path,
            settings=settings,
            article_url_map=article_url_map,
            ref_cache=resolved_ref_cache,
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

    def _register_markdown_extension(pelican: Any) -> None:
        pass


# --- plugin lifecycle --------------------------------------------------------

_settings: dict[str, Any] | None = None
_data_root: Path | None = None
_content_path: Path | None = None
_article_url_map: dict[str, str] = {}
_ref_cache: dict[Path, list[dict[str, Any]]] = {}


def _init(pelican: Any) -> None:
    global _settings, _data_root, _content_path, _article_url_map, _ref_cache
    _settings = _resolve_settings(pelican.settings)
    _article_url_map = {}
    _ref_cache = {}

    raw_path = pelican.settings.get("PATH", "content")
    content_path = Path(raw_path)
    if not content_path.is_absolute():
        conf_file = pelican.settings.get("pelicanconf")
        if conf_file:
            content_path = Path(conf_file).parent / raw_path
        content_path = content_path.resolve()
    _content_path = content_path
    raw_data_root = pelican.settings.get("TABULAR_DATA_ROOT")
    if raw_data_root:
        data_root_path = Path(raw_data_root)
        if not data_root_path.is_absolute():
            conf_file = pelican.settings.get("pelicanconf")
            if conf_file:
                data_root_path = Path(conf_file).parent / raw_data_root
            data_root_path = data_root_path.resolve()
        _data_root = data_root_path
    else:
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

    _process_content(
        content,
        _settings,
        _data_root,
        _article_url_map,
        content_path=_content_path,
        ref_cache=_ref_cache,
    )


def register() -> None:
    signals.initialized.connect(_init)
    signals.content_object_init.connect(_process_article)

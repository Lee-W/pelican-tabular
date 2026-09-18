"""Shared data operations for table consumers (independent of Pelican hooks)."""

from __future__ import annotations

import datetime
import html
import logging
import re
from typing import Any
from urllib.parse import quote, urlsplit

log = logging.getLogger(__name__)


def slugify(value: str) -> str:
    """Slug for an HTML id. Keeps letter chars (incl. CJK) and digits."""
    s = re.sub(r"\s+", "-", str(value).strip())
    out = [ch for ch in s if ch == "-" or ch.isalnum()]
    return "".join(out).lower() or "group"


def format_scalar(value: Any, date_format: str = "") -> str:
    if isinstance(value, (datetime.date, datetime.datetime)):
        if date_format:
            return value.strftime(date_format)
        return value.isoformat()
    return str(value)


def extract_year(value: Any) -> int | None:
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
            year = extract_year(item)
            if year is not None:
                return year
    return None


def extract_years(value: Any) -> list[int]:
    if isinstance(value, list):
        years: list[int] = []
        for item in value:
            year = extract_year(item)
            if year is not None:
                years.append(year)
        return years
    year = extract_year(value)
    return [year] if year is not None else []


def numeric_value(value: Any) -> float | None:
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


def format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return str(round(value, 2))


def aggregate_field(op: str, field: str, places: list[dict[str, Any]]) -> Any:
    if op == "year":
        seen: set[int] = set()
        ordered: list[int] = []
        for p in places:
            for year in extract_years(p.get(field)):
                if year not in seen:
                    seen.add(year)
                    ordered.append(year)
        ordered.sort()
        return ", ".join(str(y) for y in ordered)
    if op == "count":
        return sum(1 for p in places if p.get(field) not in (None, ""))
    if op in ("sum", "avg", "min", "max"):
        raw = (numeric_value(p.get(field)) for p in places)
        values = [v for v in raw if v is not None]
        if not values:
            return ""
        if op == "sum":
            return format_number(sum(values))
        if op == "avg":
            return format_number(sum(values) / len(values))
        if op == "min":
            return format_number(min(values))
        return format_number(max(values))
    log.warning("pelican-tabular: unknown aggregate op %r for field %r", op, field)
    return ""


def field_transform(token: str) -> tuple[str, str | None]:
    """Split a ``group_by`` token into ``(field, transform)``.

    A bare ``"date"`` groups by the raw value; ``"date:year"`` groups by a
    derived value. Currently the only transform is ``year`` (extracts the
    year from a date/datetime/year-like value via ``extract_year``).
    """
    if ":" in token:
        field, _, transform = token.partition(":")
        return field.strip(), transform.strip()
    return token.strip(), None


def group_key_value(row: dict[str, Any], token: str) -> Any:
    field, transform = field_transform(token)
    if transform == "year":
        year = extract_year(row.get(field))
        return year if year is not None else ""
    return row.get(field, "")


def collapse_rows(
    rows: list[dict[str, Any]],
    group_by: list[str],
    aggregate: dict[str, str],
    *,
    union_fields: tuple[str, ...] = (),
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
            key = tuple(group_key_value(row, g) for g in group_by)
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(row)
        return [{**r, "_places": [r]} for key in order for r in buckets[key]]

    collapsed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(group_key_value(row, g) for g in group_by)
        if key not in collapsed:
            collapsed[key] = {**row, "_places": [row]}
            order.append(key)
            continue
        existing = collapsed[key]
        existing["_places"].append(row)
        for field in union_fields:
            values = list(existing.get(field) or [])
            for item in row.get(field) or []:
                if item not in values:
                    values.append(item)
            if values:
                existing[field] = values
        for k, v in row.items():
            if k in union_fields or k in aggregate:
                continue
            if not existing.get(k) and v:
                existing[k] = v

    result: list[dict[str, Any]] = []
    for key in order:
        row = collapsed[key]
        for field, op in aggregate.items():
            row[field] = aggregate_field(op, field, row["_places"])
        result.append(row)
    return result


def cell_value(
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
        if href and urlsplit(str(href)).scheme.lower() in (
            "",
            "http",
            "https",
            "mailto",
            "tel",
        ):
            safe_href = quote(str(href), safe=":/?#[]@!$&'()*+,;=")
            safe_text = html.escape(str(text))
            aria = f' aria-label="{html.escape(str(aria_label))}"' if aria_label else ""
            return f'<a href="{safe_href}"{aria}>{safe_text}</a>'
        return html.escape(str(text))
    if isinstance(value, list):
        if len(value) > 1:
            items = "".join(
                "<li>"
                + cell_value(item, date_format=date_format, aria_label=aria_label)
                + "</li>"
                for item in value
            )
            return f'<ul style="margin:0;padding-left:1.2em">{items}</ul>'
        return (
            cell_value(value[0], date_format=date_format, aria_label=aria_label)
            if value
            else ""
        )
    return html.escape(format_scalar(value, date_format))


def sort_key(value: Any) -> tuple[int, Any]:
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

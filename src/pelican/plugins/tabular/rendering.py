"""Public HTML rendering primitives for plugins that supply their own cells.

Callbacks return trusted HTML, just like a Pelican theme. Callers must escape
user data. Group labels are escaped here; count templates are trusted settings.
"""

from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from .core import group_key_value as _default_group_key_value
from .core import slugify
from .i18n import Message, format_message

Row = dict[str, Any]


def render_table_body(
    rows: list[Row],
    *,
    column_count: int,
    render_row: Callable[[Row], str],
    group_summary_at: list[str],
    group_count_template: Message = "{n} rows",
    lang: str = "en",
    text_count: bool = False,
    group_suffix: Callable[[Row, str], str] | None = None,
    group_key_value: Callable[[Row, str], Any] | None = None,
    css_prefix: str = "osm",
    id_prefix: str = "osm-group--",
    used_ids: set[str] | None = None,
) -> str:
    """Render prepared rows and nested group headers without owning cell policy.

    Group/collapse rows with ``core.collapse_rows`` first. ``_places`` carries
    original members for aggregated counts; ordinary rows count as one.
    ``group_key_value`` defaults to ``core.group_key_value`` (flat field
    lookup); callers with richer field access (dotted paths, resolved
    references, ...) can pass their own to keep group headers consistent with
    how they resolve ``group_by``/``group_summary_at`` elsewhere.
    """
    key_of = group_key_value or _default_group_key_value
    ids = used_ids if used_ids is not None else set()
    counts: dict[tuple[Any, ...], int] = defaultdict(int)
    for row in rows:
        key = tuple(key_of(row, f) for f in group_summary_at)
        for depth in range(len(key)):
            counts[key[: depth + 1]] += len(row.get("_places") or [row])
    parts = []
    previous: tuple[Any, ...] = ()
    for row in rows:
        key = tuple(key_of(row, f) for f in group_summary_at)
        for depth, value in enumerate(key):
            prefix = key[: depth + 1]
            if previous[: depth + 1] == prefix:
                continue
            base = id_prefix + "--".join(slugify(v) for v in prefix)
            anchor = base
            index = 2
            while anchor in ids:
                anchor = f"{base}-{index}"
                index += 1
            ids.add(anchor)
            # Preserve trusted markup and literal numbers during live updates.
            template_attr = (
                ' data-count-message="'
                + html.escape(json.dumps(group_count_template), quote=True)
                + '"'
                if isinstance(group_count_template, dict) or text_count
                else (
                    ' data-count-template="'
                    + html.escape(group_count_template, quote=True)
                    + '"'
                    if re.search(r"[<\d]", group_count_template)
                    else ""
                )
            )
            count = (
                f'<span class="{css_prefix}-group-count"{template_attr}>'
                + (
                    html.escape(
                        format_message(group_count_template, lang, n=counts[prefix])
                    )
                    if isinstance(group_count_template, dict) or text_count
                    else group_count_template.replace("{n}", str(counts[prefix]))
                )
                + "</span>"
                if group_count_template
                else ""
            )
            suffix = group_suffix(row, group_summary_at[depth]) if group_suffix else ""
            parts.append(
                f'<tr class="{css_prefix}-group-header'
                f' {css_prefix}-group-header--depth-{depth}"'
                f' data-depth="{depth}" id="{html.escape(anchor, quote=True)}">'
                f'<td colspan="{column_count}">'
                f'<span class="{css_prefix}-group-header-toggle"'
                ' aria-hidden="true">▾</span>'
                f'<strong class="{css_prefix}-group-header-title">'
                f"{html.escape(str(value))}</strong>{count}{suffix}</td></tr>"
            )
        previous = key
        parts.append(render_row(row))
    return "\n".join(parts)

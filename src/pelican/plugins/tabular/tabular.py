"""pelican-tabular plugin: embed data tables via {% table %} shortcode."""

from __future__ import annotations

import csv
import json
import logging
import re
import shlex
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
DEFAULT_DATA_ROOT = "data"


# --- settings ----------------------------------------------------------------


def _resolve_settings(pelican_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "shortcode": pelican_settings.get("TABULAR_SHORTCODE", DEFAULT_SHORTCODE),
        "data_root": pelican_settings.get("TABULAR_DATA_ROOT", DEFAULT_DATA_ROOT),
        "fields": pelican_settings.get("TABULAR_FIELDS", []),
        "field_labels": pelican_settings.get("TABULAR_FIELD_LABELS", {}),
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
        raise TypeError(f"Expected a list of records in {path}, got {type(data).__name__}")
    return data


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
            seen[k] = None
    return list(seen)


def _cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _render_table_html(
    rows: list[dict[str, Any]],
    *,
    fields: list[str],
    field_labels: dict[str, str],
    hidden: set[str],
    sort_by: str | None,
    sort_order: str,
) -> str:
    if sort_by:
        reverse = sort_order.lower() == "desc"
        rows = sorted(rows, key=lambda r: r.get(sort_by) or "", reverse=reverse)

    all_keys = fields if fields else _detect_columns(rows)
    columns = [(k, field_labels.get(k, k)) for k in all_keys if k not in hidden]
    if not columns:
        return ""

    parts: list[str] = ['<table class="tabular">']
    parts.append("<thead><tr>")
    for _, label in columns:
        parts.append(f"<th>{label}</th>")
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in rows:
        parts.append("<tr>")
        for key, _ in columns:
            parts.append(f"<td>{_cell_value(row.get(key))}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
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

    hidden_raw = kwargs.get("hidden", "")
    hidden = {h.strip() for h in hidden_raw.split(",") if h.strip()}

    fields_raw = kwargs.get("fields", "")
    fields = [f.strip() for f in fields_raw.split(",") if f.strip()] or list(settings["fields"])

    sort_by = kwargs.get("sort_by")
    sort_order = kwargs.get("sort_order", "asc")

    return _render_table_html(
        rows,
        fields=fields,
        field_labels=settings["field_labels"],
        hidden=hidden,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def _process_content(
    content: Article | Page,
    settings: dict[str, Any],
    data_root: Path,
) -> None:
    pattern = _make_pattern(settings["shortcode"])
    if not pattern.search(content._content):
        return
    content._content = pattern.sub(
        lambda m: _replace_match(m, data_root=data_root, settings=settings),
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
            text = _SHORTCODE_RE.sub(lambda m: self.md.htmlStash.store(m.group(0)), text)
            return text.split("\n")

    class _ShortcodePreserveExtension(Extension):
        def extendMarkdown(self, md: Any) -> None:
            md.preprocessors.register(
                _ShortcodePreprocessor(md), "tabular_shortcode_preserve", 175
            )

    def _register_markdown_extension(pelican: Any) -> None:
        md_cfg = pelican.settings.setdefault("MARKDOWN", {})
        extensions = md_cfg.setdefault("extensions", [])
        ext = _ShortcodePreserveExtension()
        if not any(isinstance(e, _ShortcodePreserveExtension) for e in extensions):
            extensions.append(ext)

else:

    def _register_markdown_extension(pelican: Any) -> None:  # type: ignore[misc]
        pass


# --- plugin lifecycle --------------------------------------------------------

_settings: dict[str, Any] | None = None
_data_root: Path | None = None


def _init(pelican: Any) -> None:
    global _settings, _data_root
    _settings = _resolve_settings(pelican.settings)
    content_path = Path(pelican.settings.get("PATH", "content"))
    data_root_cfg = _settings["data_root"]
    _data_root = Path(data_root_cfg) if Path(data_root_cfg).is_absolute() else content_path / data_root_cfg
    _register_markdown_extension(pelican)


def _process_article(content: Article | Page) -> None:
    if _settings is None or _data_root is None:
        return
    _process_content(content, _settings, _data_root)


def register() -> None:
    signals.initialized.connect(_init)
    signals.content_object_init.connect(_process_article)

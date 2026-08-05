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
# Roots (relative to Pelican's PATH) searched for a bare ``<field>_ref: <id>``
# global-id reference. See the module comment above ``DEFAULT_REF_SUFFIX``.
DEFAULT_REF_ROOTS = ["places"]


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
        "ref_roots": list(pelican_settings.get("TABULAR_REF_ROOTS", DEFAULT_REF_ROOTS)),
        "ref_strict": bool(pelican_settings.get("TABULAR_REF_STRICT", True)),
        "ref_suffix": str(
            pelican_settings.get("TABULAR_REF_SUFFIX", DEFAULT_REF_SUFFIX)
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


def _get_nested(obj: Any, path: str) -> Any:
    """Resolve a possibly dotted field path against ``obj``.

    A literal top-level key equal to the full dotted ``path`` string wins
    first — this protects two things: legacy flat field names that happen to
    contain a literal dot, and aggregate output fields, which ``_collapse_rows``
    writes back under their dotted spec name (e.g. an ``aggregate`` spec of
    ``"venue.city:count"`` stores its result at the literal key
    ``row["venue.city"]``, not nested). Only when no literal key matches does
    the path get walked segment by segment. A ``None`` or missing value at any
    point in the walk yields ``None`` rather than raising — a table citing
    records that don't all carry the same nested shape must still render,
    just with a blank cell where the field is absent.
    """
    if not isinstance(obj, dict):
        return None
    if path in obj:
        return obj[path]
    if "." not in path:
        return obj.get(path)
    head, _, rest = path.partition(".")
    return _get_nested(obj.get(head), rest)


def _aggregate_field(op: str, field: str, places: list[dict[str, Any]]) -> Any:
    if op == "year":
        seen: set[int] = set()
        ordered: list[int] = []
        for p in places:
            for year in _extract_years(_get_nested(p, field)):
                if year not in seen:
                    seen.add(year)
                    ordered.append(year)
        ordered.sort()
        return ", ".join(str(y) for y in ordered)
    if op == "count":
        return sum(1 for p in places if _get_nested(p, field) not in (None, ""))
    if op in ("sum", "avg", "min", "max"):
        raw = (_numeric_value(_get_nested(p, field)) for p in places)
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
# A field named ``<name>_ref`` lets a data row point at a single record living
# in another YAML file, instead of duplicating that record's data locally.
# Resolution replaces ``<name>_ref`` with a ``<name>`` field holding the
# *entire* referenced record (a plain dict — every field the target has, not
# just a display string). This is deliberate: a "ref" models a relationship
# between two data rows, not a rendering choice. What that relationship looks
# like on the page — plain text, a link, grouped/aggregated by one of the
# referenced record's own fields — is a concern of ``fields``/``group_by``/
# ``aggregate`` (see ``_field_value`` below and the dotted-path / ``:link``
# transform it implements), not of ref resolution itself.
#
# Two reference forms:
#
# - ``<path>#<id>`` — resolved relative to Pelican's content root
#   (``_content_path`` in ``_init``, threaded through as ``content_path``
#   below), not the (possibly different) ``TABULAR_DATA_ROOT`` the row's own
#   file was loaded from. Use this to disambiguate when a bare id would be
#   ambiguous (see below).
# - ``<id>`` (no ``#``) — a *global* id, resolved by searching every YAML
#   file under ``TABULAR_REF_ROOTS`` (default ``["places"]``, relative to
#   Pelican's ``PATH``) for a record whose ``id`` (or, failing that, ``name``)
#   matches. This is the preferred form: it doesn't encode where the target
#   record currently lives, so reorganizing ``TABULAR_REF_ROOTS`` never
#   requires updating every row that references a moved record.
#
# In both forms, matching within a candidate file tries ``id`` first, then
# falls back to ``name``, mirroring pelican-osm's own ``#fragment`` lookup
# semantics. The referenced file may be either pelican-osm's locations-based
# shape (a ``locations:`` list of dicts) or a bare top-level list of dicts.
#
# Fail loud by default (``TABULAR_REF_STRICT`` / ``ref_strict``, default
# ``True``): a missing file, an unresolvable id, an ambiguous global id
# (matches records in more than one file), or a malformed target YAML
# document is data corruption, not a warning worth burying in a 250-article
# build log — the build should fail. Setting ``TABULAR_REF_STRICT = False``
# instead degrades these to a ``log.warning`` and leaves the raw ref string
# in the field (rendered as plain text) for builds that would rather not
# fail on one bad row.
#
# Failing the build is *not* as simple as raising synchronously out of
# ``_resolve_ref_rows``/``_replace_match``, though — Pelican's content
# generators wrap each page's processing (which is where
# ``content_object_init``, and so this plugin's ``_process_article``, runs)
# in a per-page ``try/except`` that logs an ``ERROR`` and *skips that page*,
# continuing the build with an exit code of 0. Raising there doesn't fail
# the build; it silently deletes the page from the site (worse than the old
# best-effort behaviour, since at least that left the page in place).
# `signals.finalized` fires once, at the very end of `Pelican.run()`, is not
# wrapped in any such per-page handler, and (via `main()`'s top-level
# `except Exception: sys.exit(...)`) does turn an exception into a non-zero
# process exit. So: in strict mode, a resolution failure is *collected*
# (message text, with full locator info) into the module-level
# ``_ref_errors`` list rather than raised immediately — the affected cell
# degrades to the raw ref string (same as non-strict) so the page still
# renders — and ``_check_ref_errors`` (connected to ``signals.finalized``)
# raises once, with every collected message, after all pages have been
# processed. This mirrors pelican-osm's own strict-mode schema validation
# (`_validate_yaml_files` in `pelican-osm/src/pelican/plugins/osm/osm.py`),
# which likewise accumulates errors and raises once rather than per-file.
#
# ``ref_href_template``/``TABULAR_REF_HREF_TEMPLATE`` (used only by the
# ``:link`` field transform, at render time) may hold a ``|``-separated chain
# of templates rather than a single one — real place data is often
# inconsistent about which fields it has (e.g. some records carry a stable
# OSM node id, older ones only have raw lat/lon). Templates are tried in
# order; the first one whose placeholders are *all* present and non-empty in
# the resolved record wins. This is deliberate: silently filling a missing
# placeholder with "" (as a plain ``str.format_map`` would) produces a
# malformed-but-plausible-looking URL, which is worse than falling through to
# a template that actually fits the data. ``|`` was chosen as the separator
# because it practically never appears literally in a URL template (and
# would be percent-encoded as ``%7C`` if it legitimately needed to).

DEFAULT_REF_SUFFIX = "_ref"
_REF_HREF_TEMPLATE_SEP = "|"
_REF_INDEX_CACHE_KEY = "index"


class TabularRefError(Exception):
    """A ``<field>_ref`` value could not be resolved.

    Raised when ``ref_strict`` is true (the default). Callers that want the
    old best-effort behaviour instead should catch this and degrade to
    ``log.warning`` + the raw ref string — see ``_resolve_ref_value``.
    """


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
    ``DEFAULT_REF_SUFFIX`` for why). Blank segments (e.g. a trailing separator) are
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


def _resolve_path_ref(
    raw_ref: str, *, content_path: Path, cache: dict[Path, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Resolve a ``<path>#<id>`` ref. Raises ``TabularRefError`` on any failure."""
    rel_path, _, ref_id = raw_ref.partition("#")
    target_path = content_path / rel_path

    if not target_path.exists():
        raise TabularRefError(
            f"ref target file not found: {target_path} (from {raw_ref!r})"
        )

    try:
        items = _load_ref_file(target_path, cache)
    except Exception as exc:
        raise TabularRefError(
            f"failed to load ref target {target_path} (from {raw_ref!r}): {exc}"
        ) from exc

    item = _find_ref_item(items, ref_id)
    if item is None:
        raise TabularRefError(
            f"ref id {ref_id!r} not found in {target_path} (from {raw_ref!r})"
        )
    return item


def _iter_ref_root_files(content_path: Path, ref_roots: list[str]) -> list[Path]:
    files: list[Path] = []
    for root in ref_roots:
        root_path = content_path / root
        if not root_path.is_dir():
            continue
        for pattern in ("*.yaml", "*.yml"):
            files.extend(sorted(root_path.rglob(pattern)))
    return files


# Global-id index: id/name -> [(source file, record), ...]. Built once per
# build (see ``_get_global_ref_index``'s ``index_cache`` memoization) by
# scanning every YAML file under ``TABULAR_REF_ROOTS``.
_RefIndex = dict[str, list[tuple[Path, dict[str, Any]]]]


def _build_global_ref_index(
    content_path: Path,
    ref_roots: list[str],
    cache: dict[Path, list[dict[str, Any]]],
) -> tuple[_RefIndex, _RefIndex]:
    by_id: _RefIndex = defaultdict(list)
    by_name: _RefIndex = defaultdict(list)
    for path in _iter_ref_root_files(content_path, ref_roots):
        try:
            items = _load_ref_file(path, cache)
        except Exception as exc:
            # A file under a ref root that happens to be malformed shouldn't
            # sink every global-id lookup in the build — only a ref that
            # actually resolves to (or through) it should fail loud. Skip and
            # warn; if something *does* reference a record meant to live
            # here, that lookup will (correctly) raise "not found".
            log.warning(
                "pelican-tabular: skipping unreadable TABULAR_REF_ROOTS file "
                "%s while building the global ref index: %s",
                path,
                exc,
            )
            continue
        for item in items:
            id_val = item.get("id")
            if id_val not in (None, ""):
                by_id[str(id_val)].append((path, item))
            name_val = item.get("name")
            if name_val not in (None, ""):
                by_name[str(name_val)].append((path, item))
    return by_id, by_name


def _get_global_ref_index(
    content_path: Path,
    ref_roots: list[str],
    cache: dict[Path, list[dict[str, Any]]],
    index_cache: dict[str, Any],
) -> tuple[_RefIndex, _RefIndex]:
    """Build-once, memoized-in-``index_cache`` accessor for the global index."""
    if _REF_INDEX_CACHE_KEY not in index_cache:
        index_cache[_REF_INDEX_CACHE_KEY] = _build_global_ref_index(
            content_path, ref_roots, cache
        )
    result: tuple[_RefIndex, _RefIndex] = index_cache[_REF_INDEX_CACHE_KEY]
    return result


def _resolve_global_ref(
    raw_ref: str,
    *,
    content_path: Path,
    ref_roots: list[str],
    cache: dict[Path, list[dict[str, Any]]],
    index_cache: dict[str, Any],
) -> dict[str, Any]:
    """Resolve a bare (no ``#``) global-id ref. Raises ``TabularRefError``."""
    by_id, by_name = _get_global_ref_index(content_path, ref_roots, cache, index_cache)
    candidates = by_id.get(raw_ref) or by_name.get(raw_ref)
    if not candidates:
        raise TabularRefError(
            f"global ref id {raw_ref!r} not found under TABULAR_REF_ROOTS "
            f"{ref_roots!r} (searched relative to {content_path})"
        )
    if len(candidates) > 1:
        paths = sorted({str(p) for p, _ in candidates})
        raise TabularRefError(
            f"global ref id {raw_ref!r} is ambiguous: matches records in "
            f"{len(paths)} file(s): {paths}; use the '<path>#<id>' form to "
            "disambiguate"
        )
    _, item = candidates[0]
    return item


def _resolve_ref_value(
    raw_ref: str,
    *,
    content_path: Path,
    cache: dict[Path, list[dict[str, Any]]],
    ref_roots: list[str],
    index_cache: dict[str, Any],
    strict: bool,
    field_name: str,
    row_index: int,
    source_file: Path,
) -> Any:
    """Resolve ``raw_ref`` to the *entire* referenced record (a dict).

    ``<path>#<id>`` resolves within ``target_path``; a bare ``<id>`` (no
    ``#``) resolves via the build-wide global index over ``TABULAR_REF_ROOTS``
    (see ``_resolve_global_ref``). On failure: raises ``TabularRefError`` when
    ``strict`` (the default), or logs a warning and returns the raw ref string
    unchanged (rendered as plain text) when not.
    """
    try:
        if "#" in raw_ref:
            return _resolve_path_ref(raw_ref, content_path=content_path, cache=cache)
        return _resolve_global_ref(
            raw_ref,
            content_path=content_path,
            ref_roots=ref_roots,
            cache=cache,
            index_cache=index_cache,
        )
    except TabularRefError as exc:
        message = (
            f"pelican-tabular: {exc} (field {field_name!r}, row {row_index} "
            f"of {source_file})"
        )
        if strict:
            raise TabularRefError(message) from None
        log.warning(message)
        return raw_ref


def _resolve_ref_rows(
    rows: list[dict[str, Any]],
    *,
    content_path: Path,
    cache: dict[Path, list[dict[str, Any]]],
    ref_roots: list[str],
    index_cache: dict[str, Any],
    strict: bool,
    source_file: Path,
    errors: list[str],
    ref_suffix: str = DEFAULT_REF_SUFFIX,
) -> tuple[list[dict[str, Any]], frozenset[str]]:
    """Resolve every ``<name><ref_suffix>`` field in ``rows``.

    Returns the resolved rows alongside the set of top-level field names that
    were produced by resolving a ref (e.g. ``{"venue"}`` for a row that had a
    ``venue_ref`` key). Callers thread that set through to rendering
    (``_field_value``) so a bare ``fields="venue"`` (no ``:link`` transform)
    knows to show the record's ``ref_text_field`` rather than the raw dict.

    A strict-mode (``TABULAR_REF_STRICT``) failure is *not* raised here — see
    the module comment above ``DEFAULT_REF_SUFFIX`` for why a synchronous
    raise from inside page processing can't fail the build. Instead every
    failure's message (``_resolve_ref_value`` builds it with full
    file/row/field/value locator info) is appended to ``errors``, resolution
    continues with the raw ref string standing in for the field, and the
    whole row set is always fully processed — so a data file with several bad
    refs surfaces all of them in one build, not one-at-a-time as each is
    fixed. Callers (ultimately ``_check_ref_errors``, connected to
    ``signals.finalized``) are responsible for actually failing the build
    once every page has been processed.

    A row that has *both* ``<name>`` and ``<name><ref_suffix>`` set is a
    separate failure mode from an unresolvable ref: resolving the ref would
    silently overwrite a value the author wrote down explicitly, with no
    warning. That's treated the same as any other ref failure — collected
    into ``errors`` in strict mode (build fails), logged as a warning
    otherwise — except the existing ``<name>`` value always wins and is
    never overwritten, in *either* mode: hand-authored data takes priority
    over a ref resolution regardless of how the collision is reported.
    """
    resolved_rows: list[dict[str, Any]] = []
    ref_fields: set[str] = set()
    for i, row in enumerate(rows):
        new_row = dict(row)
        for key in list(new_row.keys()):
            if not key.endswith(ref_suffix):
                continue
            value = new_row[key]
            if not isinstance(value, str):
                continue
            target_field = key[: len(key) - len(ref_suffix)]
            if target_field in new_row:
                original_value = new_row[target_field]
                message = (
                    f"pelican-tabular: field {target_field!r} already has a "
                    f"value ({original_value!r}); not overwriting it with "
                    f"the {key!r} resolution (field {key!r}, row {i} of "
                    f"{source_file})"
                )
                del new_row[key]
                if strict:
                    log.error(message)
                    errors.append(message)
                else:
                    log.warning(message)
                continue
            del new_row[key]
            try:
                resolved = _resolve_ref_value(
                    value,
                    content_path=content_path,
                    cache=cache,
                    ref_roots=ref_roots,
                    index_cache=index_cache,
                    strict=strict,
                    field_name=key,
                    row_index=i,
                    source_file=source_file,
                )
            except TabularRefError as exc:
                errors.append(str(exc))
                resolved = value
            new_row[target_field] = resolved
            ref_fields.add(target_field)
        resolved_rows.append(new_row)
    return resolved_rows, frozenset(ref_fields)


# --- field access (dotted paths, group/sort/link transforms) ----------------


def _field_transform(token: str) -> tuple[str, str | None]:
    """Split a ``field[:transform]`` token into ``(field_path, transform)``.

    A bare ``"date"`` (or ``"venue.city"``) resolves the raw value at that
    (possibly dotted) path; ``"date:year"`` derives a value from it instead.
    Transforms: ``year`` (extract the year from a date/datetime/year-like
    value via ``_extract_year``) and ``link`` (treat the resolved value as a
    ``<field>_ref``-resolved record and build a ``{text, href}`` link dict
    from it via ``ref_text_field``/``ref_href_template`` — see
    ``_field_value``). Used by ``fields``, ``group_by``, ``sort_by``, and
    ``group_summary_at``; ``field_path`` may itself contain dots (a nested
    field), which ``_get_nested`` resolves — the transform's ``:`` and the
    path's ``.`` never conflict because dots are resolved *within* the field
    half, after this split.
    """
    if ":" in token:
        field, _, transform = token.partition(":")
        return field.strip(), transform.strip()
    return token.strip(), None


class RefRenderContext:
    """Bundles the ref-rendering knobs threaded through field access.

    ``ref_fields`` is the set of top-level field names produced by resolving
    a ``<name>_ref`` (see ``_resolve_ref_rows``) — it's what lets a bare
    ``fields="venue"`` (no ``:link``) know to show ``venue``'s
    ``ref_text_field`` rather than dumping the raw resolved record. It plays
    no role for the ``:link`` transform, which works on any dict-shaped
    value regardless of provenance.
    """

    __slots__ = ("href_template", "ref_fields", "text_field")

    def __init__(
        self, ref_fields: frozenset[str], text_field: str, href_template: str
    ) -> None:
        self.ref_fields = ref_fields
        self.text_field = text_field
        self.href_template = href_template


def _ref_record_text(record: dict[str, Any], text_field: str) -> str:
    text = record.get(text_field)
    if text in (None, ""):
        text = record.get("name", "")
    return "" if text in (None, "") else str(text)


def _ref_record_link(record: dict[str, Any], ctx: RefRenderContext) -> Any:
    text = _ref_record_text(record, ctx.text_field)
    templates = _split_ref_href_templates(ctx.href_template)
    href = _resolve_ref_href(templates, record)
    return {"text": text, "href": href} if href else text


def _field_value(row: dict[str, Any], token: str, ctx: RefRenderContext) -> Any:
    """Resolve a ``field[.nested][:transform]`` token against ``row``.

    The single field-access path used uniformly by cell rendering, sorting,
    and group-key extraction, so all three see the same value for a given
    token. Dotted paths walk nested dicts (``_get_nested``); the ``:link``
    transform turns a resolved ``<field>_ref`` record into a ``{text, href}``
    link dict; with no transform, a *ref-resolved* record (``path`` is a bare
    top-level name in ``ctx.ref_fields``, not a deeper nested path into one)
    reduces to its plain-text ``ref_text_field`` rather than being handed to
    ``_cell_value`` as a raw dict — see the module comment above
    ``DEFAULT_REF_SUFFIX`` for why a ref resolves to the whole record in the first
    place.
    """
    path, transform = _field_transform(token)
    value = _get_nested(row, path)
    if transform == "year":
        return _extract_year(value)
    if transform == "link":
        return _ref_record_link(value, ctx) if isinstance(value, dict) else value
    if path in ctx.ref_fields and isinstance(value, dict):
        return _ref_record_text(value, ctx.text_field)
    return value


# --- grouping / collapsing (ported from pelican-osm) ------------------------


def _group_key_value(row: dict[str, Any], token: str, ctx: RefRenderContext) -> Any:
    value = _field_value(row, token, ctx)
    return "" if value is None else value


def _collapse_rows(
    rows: list[dict[str, Any]],
    group_by: list[str],
    aggregate: dict[str, str],
    ctx: RefRenderContext,
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
            key = tuple(_group_key_value(row, g, ctx) for g in group_by)
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(row)
        return [{**r, "_places": [r]} for key in order for r in buckets[key]]

    collapsed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(_group_key_value(row, g, ctx) for g in group_by)
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
    ref_ctx: RefRenderContext | None = None,
) -> str:
    aria_columns = aria_columns or set()
    ref_ctx = ref_ctx or RefRenderContext(
        frozenset(), DEFAULT_REF_TEXT_FIELD, DEFAULT_REF_HREF_TEMPLATE
    )
    if sort_by:
        reverse = sort_order.lower() == "desc"
        rows = sorted(
            rows,
            key=lambda r: _sort_key(_field_value(r, sort_by, ref_ctx)),
            reverse=reverse,
        )

    if group_by:
        if group_summary_at and group_by[: len(group_summary_at)] != group_summary_at:
            log.warning(
                "pelican-tabular: group_summary_at must be a prefix of"
                " group_by; ignoring"
            )
            group_summary_at = []
        rows = _collapse_rows(rows, group_by, aggregate, ref_ctx)
    else:
        rows = [{**r, "_places": [r]} for r in rows]
        if group_summary_at:
            log.warning("pelican-tabular: group_summary_at requires group_by; ignoring")
            group_summary_at = []

    summary_set = set(group_summary_at)
    all_tokens = fields if fields else _detect_columns(rows)
    # Each column keeps its full token (e.g. ``"venue:link"``) for value
    # resolution, but ``field_labels``/``hidden``/``group_summary_at``/
    # ``aria_columns`` all key off the bare field path (``"venue"``) — the
    # transform is a rendering-mode suffix, not part of "which field is
    # this", so `field_labels="venue:場館"` labels the column regardless of
    # whether it's displayed as `venue` or `venue:link`.
    columns = []
    for token in all_tokens:
        path, _transform = _field_transform(token)
        if path in hidden or path in summary_set:
            continue
        columns.append((token, path, field_labels.get(path, path)))
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
    for _token, _path, label in columns:
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
            key = tuple(_group_key_value(row, f, ref_ctx) for f in group_summary_at)
            for d in range(len(key)):
                prefix_counts[key[: d + 1]] += n

        prev_key: tuple[str, ...] = ()
        for row in rows:
            cur_key = tuple(_group_key_value(row, f, ref_ctx) for f in group_summary_at)
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
            for token, path, label in columns:
                aria = label if path in aria_columns else None
                cell = _cell_value(
                    _field_value(row, token, ref_ctx),
                    date_format=date_format,
                    aria_label=aria,
                )
                parts.append(f"<td>{cell}</td>")
            parts.append("</tr>")
    else:
        for row in rows:
            parts.append("<tr>")
            for token, path, label in columns:
                aria = label if path in aria_columns else None
                cell = _cell_value(
                    _field_value(row, token, ref_ctx),
                    date_format=date_format,
                    aria_label=aria,
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
    ref_index_cache: dict[str, Any],
    ref_errors: list[str],
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

    # `<field>_ref` resolution never raises out of here — a strict-mode
    # failure would only take down this one page (Pelican swallows
    # exceptions raised while processing a page), not fail the build. Its
    # message is instead appended to `ref_errors`, which `_check_ref_errors`
    # (connected to `signals.finalized`) raises from once, after every page
    # has been processed — see the module comment above `DEFAULT_REF_SUFFIX`.
    rows, ref_fields = _resolve_ref_rows(
        rows,
        content_path=content_path,
        cache=ref_cache,
        ref_roots=settings["ref_roots"],
        index_cache=ref_index_cache,
        strict=settings["ref_strict"],
        source_file=full_path,
        errors=ref_errors,
        ref_suffix=settings["ref_suffix"],
    )
    ref_text_field = kwargs.get("ref_text_field") or settings["ref_text_field"]
    ref_href_template = kwargs.get("ref_href_template") or settings["ref_href_template"]
    ref_ctx = RefRenderContext(ref_fields, ref_text_field, ref_href_template)

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
        ref_ctx=ref_ctx,
    )


def _process_content(
    content: Article | Page,
    settings: dict[str, Any],
    data_root: Path,
    article_url_map: dict[str, str],
    content_path: Path | None = None,
    ref_cache: dict[Path, list[dict[str, Any]]] | None = None,
    ref_index_cache: dict[str, Any] | None = None,
    ref_errors: list[str] | None = None,
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
    resolved_ref_index_cache: dict[str, Any] = (
        ref_index_cache if ref_index_cache is not None else {}
    )
    # Defaults to a fresh list (not shared across calls) for callers that
    # don't care about accumulating errors across a whole build — real usage
    # via ``_process_article`` always passes the persistent module-level
    # ``_ref_errors`` list explicitly so it accumulates across every page.
    resolved_ref_errors: list[str] = ref_errors if ref_errors is not None else []
    content._content = pattern.sub(
        lambda m: _replace_match(
            m,
            data_root=data_root,
            content_path=resolved_content_path,
            settings=settings,
            article_url_map=article_url_map,
            ref_cache=resolved_ref_cache,
            ref_index_cache=resolved_ref_index_cache,
            ref_errors=resolved_ref_errors,
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
# Memoizes the global-id index (see ``_get_global_ref_index``) so it's built
# at most once per build regardless of how many shortcodes/rows use a bare
# global-id ref.
_ref_index_cache: dict[str, Any] = {}
# Accumulates strict-mode ``<field>_ref`` failure messages across every page
# processed in the build. ``_check_ref_errors`` (connected to
# ``signals.finalized``) raises from this once, after all pages are done —
# see the module comment above ``DEFAULT_REF_SUFFIX`` for why raising synchronously
# during page processing can't fail the build.
_ref_errors: list[str] = []


def _init(pelican: Any) -> None:
    global _settings, _data_root, _content_path, _article_url_map
    global _ref_cache, _ref_index_cache, _ref_errors
    _settings = _resolve_settings(pelican.settings)
    _article_url_map = {}
    _ref_cache = {}
    _ref_index_cache = {}
    _ref_errors = []

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
        ref_index_cache=_ref_index_cache,
        ref_errors=_ref_errors,
    )


def _check_ref_errors(pelican: Any) -> None:
    """Fail the build if any strict-mode ``<field>_ref`` failed to resolve.

    Connected to ``signals.finalized``, which fires once at the very end of
    ``Pelican.run()`` and — unlike the per-page exception handling content
    generation wraps ``_process_article`` in — is not swallowed: an
    exception here reaches ``main()``'s top-level ``except Exception:
    sys.exit(...)`` and turns into a non-zero process exit. See the module
    comment above ``DEFAULT_REF_SUFFIX``.
    """
    del pelican  # unused; signature matches what blinker's Signal.send passes
    if not _ref_errors:
        return
    joined = "\n".join(f"  - {message}" for message in _ref_errors)
    raise TabularRefError(
        f"pelican-tabular: {len(_ref_errors)} ref error(s); failing the build:\n"
        f"{joined}"
    )


def register() -> None:
    signals.initialized.connect(_init)
    signals.content_object_init.connect(_process_article)
    signals.finalized.connect(_check_ref_errors)

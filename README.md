# pelican-tabular

Pelican plugin to embed data tables in Markdown articles via a `{% table %}` shortcode.

## Installation

```
uv add pelican-tabular
```

Add to `pelicanconf.py`:

```python
PLUGINS = ["pelican.plugins.tabular"]
```

## Usage

```
{% table data/books.yaml %}
{% table data/books.yaml fields="title,rating,year" %}
{% table data/books.yaml sort_by="rating" sort_order="desc" %}
{% table data/books.yaml hidden="internal_id" %}
{% table data/books.yaml group_by="genre" group_summary_at="genre" %}
{% table data/books.yaml group_by="author,year" aggregate="year:year" field_labels="year:Publication Year" %}
{% table data/books.yaml sort_by="date" date_format="%b %Y" %}
{% table data/books.yaml group_by="date:year" group_summary_at="date:year" %}
{% table data/books.yaml aria_columns="slide,recording" %}
{% table data/concerts.yaml fields="title,venue" %}       {# venue_ref → plain text #}
{% table data/concerts.yaml fields="title,venue:link" %}  {# venue_ref → link #}
{% table data/concerts.yaml group_by="venue.city" %}      {# group by a field of the referenced record #}
```

### Shortcode parameters

| Parameter | Description |
|-----------|-------------|
| *(first positional)* | Path to data file, relative to `TABULAR_DATA_ROOT` |
| `fields` | Comma-separated list of fields to display (overrides `TABULAR_FIELDS`). Each entry may be a dotted path into a nested field (`venue.city`) and/or carry a `:transform` suffix (`venue:link`, `date:year`) — see [Field paths and transforms](#field-paths-and-transforms) |
| `hidden` | Comma-separated list of fields to exclude from output |
| `sort_by` | Field key to sort rows by (dotted paths supported) |
| `sort_order` | `asc` (default) or `desc` |
| `group_by` | Comma-separated fields to group rows by. Dotted paths are supported (`venue.city`), and a field may use a `field:transform` form to group by a derived value (currently supports `year`, e.g. `date:year`) |
| `group_summary_at` | Fields at which to render a collapsible group-header row with row count; must be a prefix of `group_by` (dotted paths and transforms allowed, e.g. `date:year`) |
| `aggregate` | Comma-separated `field:op` pairs for collapsed groups (currently supports `year`, `count`, `sum`, `avg`, `min`, `max`); `field` may be a dotted path (`venue.city:count`) |
| `field_labels` | Per-shortcode label overrides, formatted as `field:Label,field2:Label 2`. Keys are the bare field path — `venue:場館` labels the column whether it's displayed as `venue` or `venue:link` |
| `date_format` | `strftime` pattern applied to date/datetime cells, e.g. `%b %Y` → `Jun 2026` (overrides `TABULAR_DATE_FORMAT`). Sorting still uses the underlying date |
| `aria_columns` | Comma-separated columns whose links should get an `aria-label` taken from the column header, giving icon-only link text (e.g. an emoji) an accessible name |
| `ref_text_field` | Field (within the referenced record) used as link text for `<field>_ref` columns, both for the plain-text default and for `:link` cells (overrides `TABULAR_REF_TEXT_FIELD`, default `name`) |
| `ref_href_template` | `str.format`-style template(s) used to build the link href for a `:link`-transformed `<field>_ref` column; `\|`-separate multiple templates for a fallback chain (overrides `TABULAR_REF_HREF_TEMPLATE`, default `https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}`) |

## Data formats

Supports YAML (list of dicts), JSON arrays, and CSV.

```yaml
# data/books.yaml
- title: The Left Hand of Darkness
  author: Ursula K. Le Guin
  year: 1969
  rating: 5
- title: Piranesi
  author: Susanna Clarke
  year: 2020
  rating: 5
```

### Cell value types

| Type | Example | Rendered as |
|------|---------|-------------|
| Scalar | `"Ursula K. Le Guin"` | Plain text |
| Date | `2020-01-15` | ISO string |
| Link dict | `{href: "https://…", text: "Homepage"}` | `<a href="…">Homepage</a>` |
| List | `["tag1", "tag2"]` | Unordered list |

Link dicts also accept `url` as an alias for `href`, and `label` as an alias for `text`.

### `{filename}` links

Link `href` values support Pelican's `{filename}` syntax to cross-reference other articles:

```yaml
- title: My Post
  link: {href: "{filename}posts/my-post.md", text: "Read more"}
```

### Cross-file references (`<field>_ref`)

A field named `<name>_ref` lets a row point at a single record living in
*another* YAML file, instead of duplicating that record's data (and letting
the two copies drift apart). This is meant for the common case of a data
table repeatedly citing the same handful of places/people/things that
already have their own authoritative file elsewhere in `content/` — e.g. a
concert log citing venues that are also rendered on a map by
[pelican-osm](https://github.com/Lee-W/pelican-osm).

Resolving `<name>_ref` replaces it with a `<name>` field holding **the whole
referenced record** — every field the target has, not just a display
string. A ref models a relationship between two rows of data; what that
relationship looks like on the page (plain text, a link, grouped by one of
the referenced record's own fields, …) is up to `fields`/`group_by`, not
baked into the ref itself.

```yaml
# content/places/venues/taiwan.yaml (pelican-osm locations-based shape)
locations:
  - id: zepp-new-taipei
    name: Zepp New Taipei
    city: 新北市
    lat: 25.059661
    lon: 121.449499
```

```yaml
# content/data/concerts.yaml
- title: {text: "藥師寺寬邦「悟」", href: "https://example.com/goo"}
  date: 2024-10-25
  venue_ref: zepp-new-taipei
```

```
{% table data/concerts.yaml fields="title,date,venue" %}
```

renders a `venue` column (the `_ref` suffix is stripped) whose cell is the
referenced record's `name` — `Zepp New Taipei` — as plain text. Want a link
instead? Add the `:link` transform: `fields="title,date,venue:link"` (see
[Field paths and transforms](#field-paths-and-transforms)). Want the venue's
city? `fields="title,venue.city"`, or `group_by="venue.city"` to group
concerts by which city they were in — `fields`, `group_by`, `sort_by`, etc.
all see the *entire* resolved `venue` record, not just `venue_ref`.

#### Reference forms: global id vs. `<path>#<id>`

- **Global id** (`venue_ref: zepp-new-taipei`, shown above) — searches every
  YAML file under `TABULAR_REF_ROOTS` (default `["places"]`, relative to
  Pelican's `PATH`) for a record whose `id` (or, failing that, `name`)
  matches. This is the form to reach for by default: it doesn't encode
  *where* the target record currently lives, so moving/renaming files under
  `TABULAR_REF_ROOTS` never requires touching every row that cites them.
- **`<path>#<id>`** (`venue_ref: places/venues/taiwan.yaml#zepp-new-taipei`)
  — `<path>` is resolved relative to Pelican's content root (the `PATH`
  setting), not `TABULAR_DATA_ROOT` (which is where the *referencing* file
  was loaded from — these are often different roots, e.g. `TABULAR_DATA_ROOT`
  pointed at `content/data` while venues live under `content/places/`). Use
  this form to disambiguate when a global id would match more than one
  record (see **Fail loud** below), or to point at a file outside
  `TABULAR_REF_ROOTS` entirely.

In both forms, matching within a candidate file tries `id` first, then falls
back to `name` — mirroring pelican-osm's own `#fragment` lookup, so there's
one convention to learn across both plugins. The target file may be
pelican-osm's locations-based shape (`locations: [...]`, shown above) or a
bare top-level YAML list of dicts.

#### Fail loud

A ref that doesn't resolve — target file not found, id not found, or a
global id that matches records in **more than one** file under
`TABULAR_REF_ROOTS` — **fails the build** by default
(`TABULAR_REF_STRICT = True`). A ref pointing at nothing is data corruption,
not something worth burying as a `log.warning` line in a 250-article build
log.

**This happens once, at the end of the build, not per-page.** Pelican wraps
each page's processing in a try/except that logs an `ERROR` and *skips that
one page* on any exception, continuing the rest of the build with exit code
`0` — raising immediately when a bad ref is found would only delete that
page from the site, silently, while everything else (including the CI
step) reports success. So instead: every `<field>_ref` failure encountered
while processing any page is collected (with full locator info) as pages
are generated, and once the whole build reaches Pelican's `finalized` stage,
a single exception is raised **listing every failure found**, across every
page, in one shot — not just the first one, so fixing a data file with
several bad refs doesn't take several build-fix-rebuild cycles:

```
pelican-tabular: 2 ref error(s); failing the build:
  - pelican-tabular: global ref id 'moondog' is ambiguous: matches records in
2 file(s): ['content/places/venues/japan.yaml',
'content/places/venues/taiwan.yaml']; use the '<path>#<id>' form to
disambiguate (field 'venue_ref', row 3 of content/data/concerts.yaml)
  - pelican-tabular: ref id 'nangang-exhibiton-hall-1' not found under
TABULAR_REF_ROOTS ['places'] (searched relative to content) (field
'venue_ref', row 7 of content/data/concerts.yaml)
```

Because this raises at the very end, the build's output directory may
still contain pages generated *before* the failure was surfaced (with the
offending cell showing the raw, unresolved ref string) — the exit code is
what a CI/deploy step should gate on, not the presence of `output/`.

Set `TABULAR_REF_STRICT = False` (globally only — there's no per-shortcode
override) to degrade every failure to a `log.warning` instead, leaving the
raw ref string in the field (rendered as plain text) and never failing the
build, for setups that would rather not fail outright on one bad row.

Each target file is read at most once per build, and the global-id index
(built by scanning `TABULAR_REF_ROOTS`) is built at most once regardless of
how many `<field>_ref` values use the global-id form.

#### Overriding the text/link: `ref_text_field` / `ref_href_template`

By default, the plain-text rendering and the `:link` transform's link text
both use the target record's `name` field, and `:link`'s href is built from
`lat`/`lon` in OpenStreetMap's URL format — this matches what real place
data already looks like, so the common case (a table citing pelican-osm
place records) needs no configuration. Override per-shortcode with
`ref_text_field` and `ref_href_template`, or globally with
`TABULAR_REF_TEXT_FIELD` / `TABULAR_REF_HREF_TEMPLATE`:

```
{% table data/concerts.yaml fields="title,venue:link" ref_text_field="label" ref_href_template="https://maps.example/{lat},{lon}" %}
```

`ref_href_template` is a `str.format` template evaluated against the
resolved record's fields, used only by the `:link` transform. Both settings
apply to every ref-resolved field in a given shortcode call — this plugin
does not support per-column overrides in a single invocation. If a table
cites two different kinds of referenced records that need different
text/href rules, split it into two `{% table %}` calls (one per data file)
rather than mixing ref types in one row shape.

##### Fallback chain: mixed data quality across records

Real place data is rarely uniform. Some records may have a stable identifier
(e.g. an OSM node id, once you've looked one up by hand) while older or
less-curated records only have raw coordinates. `ref_href_template` accepts
multiple templates separated by `|`, tried in order — the **first template
whose placeholders are all present and non-empty in the resolved record**
wins:

```
{% table data/concerts.yaml fields="title,venue:link" ref_href_template="https://www.openstreetmap.org/{osm_type}/{osm_id}|https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}" %}
```

Here, a venue record with `osm_type`/`osm_id` set links straight to that OSM
element; a venue with only `lat`/`lon` falls back to the coordinate-based
map link; a template is only considered applicable when *every* placeholder
it references resolves to a real, non-empty value — a template is never
partially filled with blanks. If a record satisfies none of the templates in
the chain, the cell falls back further still: no link is rendered at all,
just the plain text (never a malformed href like
`https://www.openstreetmap.org//`). `|` was chosen as the separator because
it essentially never appears literally inside a URL template (browsers and
YAML both treat it as unremarkable text, but it's not a URL-safe character
you'd expect in a real template — a template that genuinely needs a literal
`|` would percent-encode it as `%7C`). A single template with no `|` behaves
exactly as before.

#### Migrating from the pre-0.6 link-only behaviour

Before this plugin resolved `<name>_ref` to the whole record, `fields="venue"`
always rendered a link (or nothing, if the record had no usable coordinates)
— that was the *only* way to display a ref field. If you're upgrading:

- `fields="venue"` now renders **plain text** (the record's `ref_text_field`).
  Add `:link` — `fields="venue:link"` — to keep the old link rendering.
- Nothing else about existing `<path>#<id>` refs needs to change; that form
  still works exactly as before.

### Field paths and transforms

Anywhere a field name is accepted — `fields`, `group_by`, `sort_by`,
`group_summary_at`, `field_labels`, `aggregate` — it may be:

- **A dotted path** into a nested field, e.g. `venue.city` (most useful
  against a resolved `<field>_ref`, but works against any nested YAML data).
  A missing or `null` value anywhere along the path renders as a blank cell
  rather than erroring.
- **Suffixed with `:transform`**, e.g. `date:year` or `venue:link` — and the
  two compose: `venue.date:year` walks the dotted path first, then applies
  the transform to what it finds there.

| Transform | Effect |
|-----------|--------|
| `year` | Extract the year from a date/datetime/year-like value (used by `group_by`/`aggregate`, e.g. `date:year`) |
| `link` | Treat the value as a resolved `<field>_ref` record and build a `{text, href}` link from it via `ref_text_field`/`ref_href_template` (see [Cross-file references](#cross-file-references-field_ref)) |

`field_labels` and `hidden` key off the **bare path** (no `:transform`
suffix) — `field_labels="venue:場館"` labels the column whether it's shown as
`venue` or `venue:link`, since the transform is a rendering choice, not a
different field.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `TABULAR_SHORTCODE` | `"table"` | Shortcode name |
| `TABULAR_DATA_ROOT` | *(Pelican `PATH`)* | Root directory for data files; absolute or relative to `pelicanconf.py` |
| `TABULAR_FIELDS` | `[]` | Default field list (empty = auto-detect from data) |
| `TABULAR_FIELD_LABELS` | `{}` | Global map of field key → display label |
| `TABULAR_COUNT_TEMPLATE` | `"{n} rows"` | Row-count string below the table; `{n}` is replaced with the count |
| `TABULAR_GROUP_COUNT_TEMPLATE` | `"{n} rows"` | Count string inside group-header rows |
| `TABULAR_DATE_FORMAT` | `""` | Global `strftime` pattern for date/datetime cells (empty = ISO format). Per-shortcode `date_format` overrides it |
| `TABULAR_REF_TEXT_FIELD` | `"name"` | Field used as link/plain-text source when resolving `<field>_ref` columns; see [Cross-file references](#cross-file-references-field_ref) |
| `TABULAR_REF_HREF_TEMPLATE` | `"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"` | `str.format` template(s) used by the `:link` transform; see [Fallback chain](#fallback-chain-mixed-data-quality-across-records) for the `\|`-separated multi-template form |
| `TABULAR_REF_ROOTS` | `["places"]` | Directories (relative to Pelican's `PATH`) searched for a bare global-id `<field>_ref` |
| `TABULAR_REF_STRICT` | `True` | If `True`, an unresolvable `<field>_ref` raises and fails the build; if `False`, it degrades to a `log.warning` and the raw ref string. See [Fail loud](#fail-loud) |

`TABULAR_COUNT_TEMPLATE` and `TABULAR_GROUP_COUNT_TEMPLATE` have built-in defaults for `zh` (`{n} 筆資料` / `{n} 筆`) and `ja` (`{n} 件`), derived from Pelican's `DEFAULT_LANG` setting.

## Grouping

`group_by` reorders rows so that rows sharing the same key values are contiguous. `group_summary_at` adds a collapsible header row above each group that shows the group value and a row count.

```
{% table data/books.yaml group_by="genre,author" group_summary_at="genre" %}
```

This renders a genre-level header row for each genre, with all books listed beneath it. The header is collapsible via [pelican-osm](https://github.com/Lee-W/pelican-osm)'s `osm-map.js` — see [CSS / JS](#css--js) below.

### Derived group keys

A `group_by` (and `group_summary_at`) field may use a `field:transform` form to group by a value derived from the field rather than its raw value. The only transform currently supported is `year`, which extracts the year from a date/datetime:

```
{% table data/talks.yaml sort_by="date" sort_order="desc" group_by="date:year" group_summary_at="date:year" %}
```

This groups rows under a collapsible header per year while keeping the original `date` column intact. Sorting still operates on the underlying date.

### Aggregation

When `aggregate` is set, rows sharing a `group_by` key are collapsed into a single row. Currently supported operations:

| Op | Description |
|----|-------------|
| `year` | Collect all unique years from the field across grouped rows, sorted ascending, joined with `, ` |
| `count` | Number of grouped rows with a non-empty value for the field |
| `sum` | Sum of the field's numeric values (non-numeric/missing values are skipped) |
| `avg` | Mean of the field's numeric values, rounded to 2 decimal places |
| `min` / `max` | Smallest / largest of the field's numeric values |

`sum`/`avg`/`min`/`max` coerce numeric-looking strings (e.g. `"8.5"`) but skip anything that can't be parsed as a number; if no value in the group is numeric, the aggregated cell is empty.

```
{% table data/books.yaml group_by="author" aggregate="year:year" %}
{% table data/books.yaml group_by="genre" aggregate="rating:avg,pages:sum" %}
```

## Column anchors

Every `<th>` element has an `id` attribute derived from the column label (e.g., `id="osm-col--title"`). These can be used as fragment links within the page. IDs are unique within a table; duplicate slugs get a numeric suffix (`-2`, `-3`, …).

## CSS / JS

The generated HTML uses the same class names as [pelican-osm](https://github.com/Lee-W/pelican-osm) (`osm-place-list`, `osm-group-*`) so the two plugins share CSS and the `osm-map.js` interactive sorting and group-toggle behaviour.

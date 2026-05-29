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
{% table data/books.yaml group_by="author,year" aggregate="year:year" field_labels="year=Publication Year" %}
```

### Shortcode parameters

| Parameter | Description |
|-----------|-------------|
| *(first positional)* | Path to data file, relative to `TABULAR_DATA_ROOT` |
| `fields` | Comma-separated list of fields to display (overrides `TABULAR_FIELDS`) |
| `hidden` | Comma-separated list of fields to exclude from output |
| `sort_by` | Field key to sort rows by |
| `sort_order` | `asc` (default) or `desc` |
| `group_by` | Comma-separated fields to group rows by |
| `group_summary_at` | Fields at which to render a collapsible group-header row with row count; must be a prefix of `group_by` |
| `aggregate` | Comma-separated `field:op` pairs for collapsed groups (currently supports `year`) |
| `field_labels` | Per-shortcode label overrides, formatted as `field=Label,field2=Label 2` |

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

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `TABULAR_SHORTCODE` | `"table"` | Shortcode name |
| `TABULAR_DATA_ROOT` | *(Pelican `PATH`)* | Root directory for data files; absolute or relative to `pelicanconf.py` |
| `TABULAR_FIELDS` | `[]` | Default field list (empty = auto-detect from data) |
| `TABULAR_FIELD_LABELS` | `{}` | Global map of field key → display label |
| `TABULAR_COUNT_TEMPLATE` | `"{n} rows"` | Row-count string below the table; `{n}` is replaced with the count |
| `TABULAR_GROUP_COUNT_TEMPLATE` | `"{n} rows"` | Count string inside group-header rows |

`TABULAR_COUNT_TEMPLATE` and `TABULAR_GROUP_COUNT_TEMPLATE` have built-in defaults for `zh` (`{n} 筆資料` / `{n} 筆`) and `ja` (`{n} 件`), derived from Pelican's `DEFAULT_LANG` setting.

## Grouping

`group_by` reorders rows so that rows sharing the same key values are contiguous. `group_summary_at` adds a collapsible header row above each group that shows the group value and a row count.

```
{% table data/books.yaml group_by="genre,author" group_summary_at="genre" %}
```

This renders a genre-level header row for each genre, with all books listed beneath it. The header is collapsible via the bundled `osm-map.js` JS.

### Aggregation

When `aggregate` is set, rows sharing a `group_by` key are collapsed into a single row. Currently supported operations:

| Op | Description |
|----|-------------|
| `year` | Collect all unique years from the field across grouped rows, sorted ascending, joined with `, ` |

```
{% table data/books.yaml group_by="author" aggregate="year:year" %}
```

## Column anchors

Every `<th>` element has an `id` attribute derived from the column label (e.g., `id="osm-col--title"`). These can be used as fragment links within the page. IDs are unique within a table; duplicate slugs get a numeric suffix (`-2`, `-3`, …).

## CSS / JS

The generated HTML uses the same class names as [pelican-osm](https://github.com/Lee-W/pelican-osm) (`osm-place-list`, `osm-group-*`) so the two plugins share CSS and the `osm-map.js` interactive sorting and group-toggle behaviour.

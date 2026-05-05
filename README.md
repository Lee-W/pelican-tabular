# pelican-tabular

Pelican plugin to embed data tables in Markdown articles via a `{% table %}` shortcode.

## Usage

```
{% table data/books.yaml %}
{% table data/books.yaml sort_by="rating" sort_order="desc" %}
{% table data/books.yaml hidden="year" fields="title,rating" %}
```

## Settings

| Setting | Default | Description |
|---|---|---|
| `TABULAR_SHORTCODE` | `"table"` | Shortcode name |
| `TABULAR_DATA_ROOT` | `"data"` | Data directory, relative to Pelican `PATH` |
| `TABULAR_FIELDS` | `[]` | Default field list (empty = auto-detect) |
| `TABULAR_FIELD_LABELS` | `{}` | Map of field key → display label |

## Data formats

Supports YAML (list of dicts), CSV, and JSON arrays.

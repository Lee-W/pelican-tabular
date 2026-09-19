## 0.7.0 (2026-09-19)

### Feat

- add optional searchable database views

## 0.6.0 (2026-09-18)

### Feat

- resolve refs to whole records without overwriting fields
- resolve cross-file references in data rows

### Fix

- drop a marker pin in the default ref href template

## 0.5.0 (2026-07-13)

### Feat

- expand aggregate to count/sum/avg/min/max

### Fix

- resolve mypy duplicate-module crash from py.typed
- normalize sort_by key type to avoid TypeError on mixed columns

## 0.4.0 (2026-06-08)

### Feat

- add date_format, year group transform, and aria_columns

## 0.3.1 (2026-05-29)

### Fix

- remove spurious duplicate-column warning in _detect_columns

## 0.3.0 (2026-05-29)

### Feat

- **tabular**: add column anchors, HTML escaping, and data root setting

### Fix

- **config**: correct [tool.pytest.ini_options] table name

## 0.2.1 (2026-05-06)

### Fix

- mypy issue

## 0.2.0 (2026-05-05)

### Feat

- add group_by, group_summary_at, sort, aggregate, and per-shortcode field_labels
- initial pelican-tabular plugin

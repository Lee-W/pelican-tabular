# Releasing the database presentation update

This update builds on tabular 0.7.0 and OSM 0.16.1. It changes only tabular's
optional database view, not the shared table engine, legacy stylesheet or OSM
adapter. **Only tabular needs a new release for this change.** OSM 0.16.1 already
accepts `pelican-tabular>=0.7.0`; upgrading its dependency also installs the new
view assets. There is no temporary sibling source override to remove.

## Package first

1. Run the Python, JavaScript and browser checks documented in the README,
   including `scripts/build_browser_fixtures.py --osm-source ../pelican-osm`
   when the OSM checkout is available. Run `uv build` to check packaging.
2. Keep the development version at the latest released version. This repository
   automatically bumps its version, updates the changelog and creates a tag
   after a push to `main`; the tag triggers PyPI publication. The configurable
   display behavior is a feature, so retain its feature classification when
   preparing the release commit.
3. Merge/push the reviewed change when ready to release. Wait for the PyPI
   workflow to succeed before upgrading either blog. A local build or passing
   tests do not mean the package has been published.

If a future update also changes OSM, publish tabular first, then update OSM's
minimum requirement and registry lock, test it against the published package,
and publish OSM. Do not release a lockfile pointing to a local checkout.

## Upgrade each blog

From each blog repository, after publication:

```sh
uv lock --upgrade-package pelican-tabular --upgrade-package pelican-osm
uv sync --locked
uv run inv build --build-pagefind
```

Inspect the lockfile to confirm the intended published versions were selected.
Ordinary tables and OSM lists retain their existing markup, behavior and styles;
installing the new version does not opt those pages into database views.

For entertainment-blog's ranking page, remove the temporary shared presentation
overrides only after the new package is installed:

- Remove the page script that initializes filter expansion, and its template
  script tag. The view now defaults to desktop open / mobile closed itself.
- Remove duplicate search/toolbar/filter/result/legend/button typography rules,
  generic table spacing, mobile labels and review-list indentation fixes from
  the page stylesheet. These now belong to `.tabular-view`.
- Keep the page heading, navigation, author notes and Tier explanation styles,
  page widths/margins, chosen column proportions, category/Tier badge styling
  and the ranking's specific mobile arrangement. Use `td[data-field="..."]`
  for field-specific rules instead of positional column selectors.
- Keep field labels, categories, tiers, review links and search fields in the
  blog's configuration/data. Dataset translation and bilingual subtitles are
  outside this update.

The default can be made explicit, or overridden per named view:

```python
"display": {
    "layout": "responsive",
    "filters_expanded": "auto",  # True / False for a fixed initial state
    "title_field": "title",
    "meta_fields": ["category", "tier", "reviews"],
}
```

`auto` opens above 680px. After the reader manually toggles the panel, searching,
sorting and resizing preserve that choice until reload. Check both language
pages at desktop and mobile widths after removing the overrides, including
manual toggles, search, sorting, review links and the no-JavaScript fallback.
Keep main-blog's existing shortcodes unless explicitly adopting a named view.

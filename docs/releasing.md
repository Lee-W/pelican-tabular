# Release and adoption notes

## Release order for i18n

- Tabular 0.7.0 introduced the shared table core and optional database views.
- OSM 0.16.1 uses that core and requires `pelican-tabular>=0.7.0`.
- Tabular 0.8.0 published the database presentation improvements, including
  typography, mobile field labels and responsive filter expansion. Both blogs
  now use the published package; entertainment-blog has adopted the view on
  its existing ranking pages.
- Tabular **0.8.1** added ID-keyed OSM reference data, file defaults and exclusion
  of private YAML metadata from global reference discovery. See the
  [verification record](verification.md).
- Component localization and optional data translations are described in the
  [i18n usage guide](i18n.md).

**Publish tabular before the corresponding OSM i18n update.** The OSM update
uses the new `pelican.plugins.tabular.i18n` API. After tabular is published,
raise OSM's minimum dependency, regenerate its registry lockfile and test
against the published package before releasing OSM.

## Package first

1. Run `uv run poe lint` and `uv run poe cover`. For changes to shared rendering
   or assets, also run the JavaScript/browser checks in the README, including
   `uv run python scripts/build_browser_fixtures.py --osm-source ../pelican-osm`
   when the OSM checkout is available. Run `uv build` to check packaging.
2. Keep the development version at the latest released version. On a push to
   `main`, the repository's Commitizen workflow derives a version bump from
   conventional commits, updates the changelog and creates a tag; that tag
   triggers PyPI publication. Classify the i18n feature as `feat`.
   Documentation-only commits do not by themselves imply a new package version.
   `uv run cz bump --get-next --yes` checks the next version without changing
   files. Preserve the conventional commits when merging, or give the squash
   commit a `feat:` subject so the feature bump is detected.
3. Merge/push the reviewed change when ready to release. Wait for the PyPI
   workflow to succeed before upgrading either blog. A local build or passing
   tests do not mean the package has been published.

If a future OSM update needs a new tabular API, publish tabular first, then
update OSM's minimum requirement and registry lock, test against the published
package, and publish OSM. Do not release a lockfile pointing to a local checkout.

## Upgrade each blog after publication

To upgrade tabular, run from each blog repository:

```sh
uv lock --upgrade-package pelican-tabular
uv sync --locked
uv run inv build --build-pagefind
```

For a coordinated release of both packages, also pass
`--upgrade-package pelican-osm` to `uv lock`. Inspect the lockfile to confirm
which published versions were selected. If the site's configuration or data
now requires a newer feature/fix, raise its minimum dependency in
`pyproject.toml` as well.

Check build diagnostics, reference links and each language's ranking pages.
For i18n adoption, also verify translated labels/data, maps and photo lightboxes.

## Adopting the presentation changes from 0.8.0

These notes apply to sites upgrading from older versions or still carrying
view overrides. Entertainment-blog has already completed this step.
Ordinary tables and OSM lists retain their existing presentation; installing
the package does not opt those pages into database views.

- Remove a site script whose only purpose is initial filter expansion, and its
  template script tag. The view defaults to desktop open / mobile closed.
- Remove duplicate generic typography, spacing and mobile-label fixes now
  supplied by `.tabular-view`.
- Keep page headings, author notes, Tier explanations, page widths, chosen
  column proportions and dataset-specific badge/mobile styles. Use
  `td[data-field="..."]` for field rules instead of positional selectors.
- Keep field labels, categories, tiers, review links and search fields in the
  site's configuration/data. Sites supply translations and explicitly enable
  the [data translation settings](i18n.md#optional-record-translations).

Within a named view, configure the initial filter state as follows:

```python
TABULAR_VIEWS = {
    "works": {
        "fields": ["title", "category", "tier", "reviews"],
        "display": {
            "layout": "responsive",
            "filters_expanded": "auto",  # True / False for a fixed initial state
            "title_field": "title",
            "meta_fields": ["category", "tier", "reviews"],
        },
    }
}
```

`auto` opens above 680px. After the reader manually toggles the panel, searching,
sorting and resizing preserve that choice until reload. Check desktop/mobile,
manual toggles, search, sorting, review links and the no-JavaScript fallback.
Keep main-blog's existing shortcodes unless explicitly adopting a named view.

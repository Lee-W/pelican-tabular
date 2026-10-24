# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

All tasks run via `uv` + `poe` (poethepoet). Tasks are defined in `pyproject.toml` under `[tool.poe.tasks]`.

```bash
uv run poe format         # ruff check --fix && ruff format
uv run poe lint           # ruff check && mypy
uv run poe test           # pytest -n auto --dist=loadfile
uv run poe cover          # test + coverage report
uv run poe check-commit   # commitizen check on commits since origin/main
uv run poe all            # format → lint → check-commit → cover
uv run poe ci             # check-commit → prek run --all-files → cover
uv run poe setup-pre-commit  # install pre-commit hooks via prek
```

Releases: `cz bump` updates the version in `pyproject.toml` and regenerates `CHANGELOG.md` from conventional-commit history. Don't hand-edit `CHANGELOG.md` — it's regenerated.

## Architecture

The plugin lives in `src/pelican/plugins/tabular/` and renders `{% table %}` shortcodes. `tabular.py` is the Pelican entry point (`register()` connects `initialized`, `content_object_init`, `finalized`; shortcode parsing and table HTML). `core.py` holds Pelican-independent data operations that other plugins can reuse; `rendering.py` is the public HTML rendering primitives for consumers supplying their own cells; `views.py` does build-time validation and the progressively enhanced database views; `assets.py` registers/copies the bundled `static/` CSS/JS; `i18n.py` localizes components and translated record text from `messages.json`.

## Conventions

- **Conventional commits** are required — `cz check` runs in pre-commit (and via `poe check-commit`).
- **Type checking**: mypy runs `strict` on `src` and `tests`; `pelican.*` is untyped and skipped.
- **Pre-commit**: `prek` is the runner. Hooks live in `.pre-commit-config.yaml`.
- The `browser` CI job (Playwright, `npm test`) is separate from the Python toolchain.

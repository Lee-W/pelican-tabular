"""Shared asset registration, also usable when only a consuming plugin is enabled."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from pelican import signals

STATIC = Path(__file__).parent / "static"


def bundle_legacy_assets(script: Path, stylesheet: Path) -> None:
    """Include the shared engine at a consumer's existing generated asset URLs.

    Call after copying the consumer's original assets. No database controls are
    included. The engine guard also permits loading an optional view bundle.
    """
    script.write_text(
        (STATIC / "js/tabular-core.js").read_text(encoding="utf-8")
        + "\n;\n"
        + script.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    stylesheet.write_text(
        stylesheet.read_text(encoding="utf-8")
        + "\n"
        + (STATIC / "css/tabular-legacy.css").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def copy_assets(pelican: Any) -> None:
    target = (
        Path(pelican.settings.get("OUTPUT_PATH", "output")) / "static/pelican_tabular"
    )
    shutil.copytree(STATIC, target, dirs_exist_ok=True)
    (target / "js/tabular.js").write_text(
        "\n;\n".join(
            (STATIC / "js" / name).read_text(encoding="utf-8")
            for name in ("tabular-core.js", "tabular-views.js")
        ),
        encoding="utf-8",
    )


def register_assets() -> None:
    """Connect once: Pelican's signal deduplicates this stable receiver."""
    signals.finalized.connect(copy_assets)

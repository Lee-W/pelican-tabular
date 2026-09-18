from .assets import register_assets
from .core import collapse_rows
from .rendering import render_table_body
from .tabular import _render_table_html as render_table
from .tabular import register

__all__ = [
    "collapse_rows",
    "register",
    "register_assets",
    "render_table",
    "render_table_body",
]

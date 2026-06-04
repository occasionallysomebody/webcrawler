"""Sphinx configuration for the webcrawler project documentation.

The documentation is designed for new contributors, so autodoc is configured to
show private helpers, undocumented members, and type hints. Private helpers are
included intentionally: this codebase is a staged data pipeline, and debugging a
run often requires understanding the small helper functions that turn raw crawl
artifacts into auditable records.
"""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

project = "Webcrawler"
author = "Webcrawler contributors"
copyright = "2026, Webcrawler contributors"
release = "0.1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "alabaster"
html_static_path = ["_static"]

autodoc_default_options = {
    "members": True,
    "private-members": True,
    "special-members": "__init__, __post_init__",
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_member_order = "bysource"
autosummary_generate = True

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = True
napoleon_include_special_with_doc = True
napoleon_use_param = True
napoleon_use_rtype = True

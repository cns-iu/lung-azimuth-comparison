"""Static-site generator for the HRA lung annotation comparison.

The package is driven by a single orchestrator, :mod:`build` at the repo root.
It resolves a manifest of *views* arranged in a dependency forest, merges each
view's design config down its ``extends`` chain, composes its data on top of a
canonical reference tree, normalizes the payload, and emits a static site under
``docs/`` suitable for GitHub Pages.

Modules
-------
ontology
    Shared identifier and delimiter helpers.
reference_tree
    Parse a CTann-style CSV into the canonical reference tree (a data root).
layout
    Shared layout constants for the column/row tree diagram.
overlays
    Read per-view overlay values keyed by ontology node id.
normalize
    Compress a resolved payload into compact, deduplicated JSON.
cascade
    Deep-merge design config down an ``extends`` chain.
manifest
    Load ``site.json``, build the view DAG, and topologically sort it.
render
    Emit the shell page and per-view pages from templates + assets.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0"

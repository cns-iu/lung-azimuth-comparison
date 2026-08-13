"""Reference supertree view — the base data root.

Its payload is simply the canonical tree (already parsed and cached in the
context by the orchestrator) run through normalization. No overlay is applied;
downstream views compose their overlays on top of this same tree.
"""

from __future__ import annotations

from typing import Any

from ..normalize import normalize_payload
from . import BuildContext


def build_payload(view: Any, context: BuildContext) -> dict[str, Any]:
    tree = context.trees[view.id]
    return normalize_payload(tree.nodes, tree.edges, tree.summary)

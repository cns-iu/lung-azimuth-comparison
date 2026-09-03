"""Reference supertree view — the base data root.

The payload is the canonical tree (already parsed and cached in the context by
the orchestrator) plus a per-node record of *which sources contribute it*.
Downstream views compose their overlays on top of this same tree.

Source slots
------------
Every node is drawn as a fixed-width stacked bar with one slot per included
source, in the order declared by ``sources.palette`` in the view config. A slot
is filled when that source names the cell type anywhere in its hierarchy paths
(including as an ancestor), blank otherwise.

Membership is stored as a **bitmask** rather than a list of names: with 10
sources it is a single integer per node instead of an array of strings, and the
front-end decodes it with a shift and a mask. ``srcCount`` is carried alongside
so Cytoscape selectors can use it without popcounting in a style expression.
"""

from __future__ import annotations

import copy
from typing import Any

from ..normalize import normalize_payload
from . import BuildContext


def build_payload(view: Any, context: BuildContext) -> dict[str, Any]:
    tree = context.trees[view.id]
    palette = (view.raw.get("sources", {}) or {}).get("palette", [])

    # Slot index per source name, casefolded so config and CSV spellings agree.
    slot_of = {
        (entry.get("source") or "").casefold(): index
        for index, entry in enumerate(palette)
    }

    nodes: list[dict[str, Any]] = []
    for src in tree.nodes:
        node = copy.deepcopy(src)
        data = node["data"]

        mask = 0
        for name in data.get("sources", []):
            slot = slot_of.get((name or "").casefold())
            if slot is not None:
                mask |= 1 << slot

        data["styleData"] = {"srcMask": mask, "srcCount": bin(mask).count("1")}
        nodes.append(node)

    summary = dict(tree.summary)
    summary["palette"] = palette
    summary["slotCount"] = len(palette)

    return normalize_payload(nodes, tree.edges, summary)

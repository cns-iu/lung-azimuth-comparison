"""Reference supertree view colored by contributing source.

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
from ..overlays import read_crosswalk_terms
from . import BuildContext


def build_payload(view: Any, context: BuildContext) -> dict[str, Any]:
    tree = context.trees[view.id]
    palette = (view.raw.get("sources", {}) or {}).get("palette", [])

    # Each tool's own dictionary of cell types it can report. The slot bars are
    # built from this rather than from the tree's paths.
    pattern = (view.raw.get("overlay", {}) or {}).get("crosswalks")
    if not pattern:
        raise ValueError(
            f"View '{view.id}' needs overlay.crosswalks to fill its source slots."
        )
    paths = sorted(context.root.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No crosswalk files matched {pattern!r}")
    vocabulary = read_crosswalk_terms(paths)

    # Walk the tree deepest-first, carrying up the set of tools that appear
    # anywhere below each node. A tool is on a node's frontier when it lists
    # the cell type but nothing beneath it, so "macrophage" keeps only the
    # tools that have no macrophage subtype of their own.
    children = {
        n["data"]["id"]: list(n["data"].get("childIds", [])) for n in tree.nodes
    }
    below: dict[str, set[str]] = {}

    def tools_below(node_id: str) -> set[str]:
        """Tools listing anything strictly beneath ``node_id``."""
        cached = below.get(node_id)
        if cached is not None:
            return cached
        found: set[str] = set()
        # Iterative, because the deepest lineage here is 12 levels but the
        # recursion would be re-entered once per node.
        stack = list(children.get(node_id, ()))
        while stack:
            child = stack.pop()
            found |= vocabulary.get(child, set())
            stack.extend(children.get(child, ()))
        below[node_id] = found
        return found

    frontier = {
        node_id: vocabulary.get(node_id, set()) - tools_below(node_id)
        for node_id in children
    }

    # Slot index per source name, casefolded so config and CSV spellings agree.
    slot_of = {
        (entry.get("source") or "").casefold(): index
        for index, entry in enumerate(palette)
    }

    nodes: list[dict[str, Any]] = []
    for src in tree.nodes:
        node = copy.deepcopy(src)
        data = node["data"]

        # A slot is filled where that tool *stops*: the cell type is in its
        # crosswalk and nothing more specific beneath it is. So the bar reads
        # as each tool's granularity frontier — the most specific call it can
        # make in this lineage — rather than its whole vocabulary.
        mask = 0
        for name in frontier.get(data["id"], ()):
            slot = slot_of.get((name or "").casefold())
            if slot is not None:
                mask |= 1 << slot

        data["styleData"] = {"srcMask": mask, "srcCount": bin(mask).count("1")}
        nodes.append(node)

    summary = dict(tree.summary)
    summary["palette"] = palette
    summary["crosswalkFileCount"] = len(paths)

    # The table reports each crosswalk's total contribution: every cell type it
    # lists that the supertree also contains. That is deliberately NOT what the
    # bars show — a slot is filled only on the frontier — so the view header
    # spells out the difference.
    in_tree = {n["data"]["id"] for n in nodes}
    vocab_counts: dict[str, int] = {}
    for node_id, names in vocabulary.items():
        if node_id in in_tree:
            for name in names:
                vocab_counts[name] = vocab_counts.get(name, 0) + 1
    summary["sourceInventory"] = [
        {**entry, "vocabCount": vocab_counts.get(entry["source"], 0)}
        for entry in summary.get("sourceInventory", [])
    ]
    summary["vocabularyNodeCount"] = sum(
        1 for n in nodes if (n["data"].get("styleData") or {}).get("srcCount")
    )
    summary["slotCount"] = len(palette)

    return normalize_payload(nodes, tree.edges, summary)

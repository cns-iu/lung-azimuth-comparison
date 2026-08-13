"""Population overlay view — HRApop lung Azimuth vs Pan-human Azimuth.

Composes the shared reference tree (cached by the orchestrator) with the HRApop
overlay keyed by ontology id. Each node is recolored by tool provenance
(shared / azimuth-only / pan-only / neutral) and annotated with per-tool
metadata and subtree tallies. Streamlined: the original per-node AS x sex
comparison tables are omitted.
"""

from __future__ import annotations

import copy
from typing import Any

from ..normalize import normalize_payload
from ..overlays import read_hrapop
from . import BuildContext


def _descendant_index(tree) -> dict[str, set[str]]:
    """Memoized set of descendants (inclusive) per node, from full adjacency."""
    children = {n["data"]["id"]: list(n["data"].get("childIds", [])) for n in tree.nodes}
    cache: dict[str, set[str]] = {}

    def collect(node_id: str, stack: set[str]) -> set[str]:
        if node_id in cache:
            return cache[node_id]
        if node_id in stack:  # defensive against cycles
            return {node_id}
        stack.add(node_id)
        acc = {node_id}
        for child in children.get(node_id, []):
            acc |= collect(child, stack)
        stack.discard(node_id)
        cache[node_id] = acc
        return acc

    for node in tree.nodes:
        collect(node["data"]["id"], set())
    return cache


def build_payload(view: Any, context: BuildContext) -> dict[str, Any]:
    base_id = view.base[0]
    tree = context.trees[base_id]

    ov = view.overlay
    hra = read_hrapop(
        context.root / ov["hrapop"],
        organ=ov.get("organ", "lung"),
        lung_tool=ov.get("lungTool", "azimuth"),
        pan_tool=ov.get("panTool", "pan-human-azimuth"),
        modality=ov.get("modality", "sc_transcriptomics"),
    )

    lung_ids, pan_ids = hra.lung_ids, hra.pan_ids
    union_ids = lung_ids | pan_ids
    subtree = _descendant_index(tree)

    nodes: list[dict[str, Any]] = []
    lung_only = pan_only = shared = 0
    for src in tree.nodes:
        node = copy.deepcopy(src)
        node_id = node["data"]["id"]
        in_lung = node_id in lung_ids
        in_pan = node_id in pan_ids
        if in_lung and in_pan:
            status = "shared"; shared += 1
        elif in_lung:
            status = "lung_only"; lung_only += 1
        elif in_pan:
            status = "pan_only"; pan_only += 1
        else:
            status = "neutral"

        desc = subtree.get(node_id, {node_id})
        lung_sub = desc & lung_ids
        pan_sub = desc & pan_ids

        node["data"]["terminalStatus"] = status
        node["data"]["overlay"] = {
            "inLung": in_lung,
            "inPan": in_pan,
            "isLeaf": node["data"].get("childCount", 0) == 0,
            "descendantCount": len(desc) - 1,
            "subtreeLungCount": len(lung_sub),
            "subtreePanCount": len(pan_sub),
            "subtreeSharedCount": len(lung_sub & pan_sub),
            "subtreeDifferenceCount": len(lung_sub ^ pan_sub),
            "lungMeta": hra.meta_for("lung", node_id),
            "panMeta": hra.meta_for("pan", node_id),
        }
        nodes.append(node)

    unmapped = sorted(union_ids - set(tree.index))
    summary = {
        "inputFile": hra.input_file,
        "rowCount": hra.filtered_row_count,
        "nodeCount": len(nodes),
        "edgeCount": len(tree.edges),
        "rootCount": tree.summary.get("rootCount", 1),
        "lungCount": len(lung_ids),
        "panCount": len(pan_ids),
        "sharedCount": len(lung_ids & pan_ids),
        "lungOnlyCount": len(lung_ids - pan_ids),
        "panOnlyCount": len(pan_ids - lung_ids),
        "mappedComparisonCount": len(union_ids & set(tree.index)),
        "unmappedComparisonCount": len(unmapped),
    }

    return normalize_payload(nodes, tree.edges, summary)

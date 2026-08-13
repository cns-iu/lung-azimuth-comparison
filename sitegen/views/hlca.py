"""HLCA exact-node comparison view.

Composes the shared reference tree with the HLCA comparison CSV.

The view is *filter-scoped*: node fill answers "which method assigns this exact
CLID **under the current sex / author-label selection**", so the graph recolours
as the filters change. That means the per-row comparison data has to travel to
the browser rather than being pre-aggregated away, so the payload carries a
compact ``filterIndex``: three string tables plus one integer row per mapped
comparison record.

Two facts are static and stay on the node:

``isComparison``
    the CLID occurs somewhere in the full paired-partition comparison. Drawn as
    a green ring, deliberately independent of the filters, so a node can show
    "part of the comparison globally, but empty in your current scope".
"""

from __future__ import annotations

import copy
from typing import Any

from ..normalize import normalize_payload
from ..overlays import read_comparison
from . import BuildContext


def build_payload(view: Any, context: BuildContext) -> dict[str, Any]:
    tree = context.trees[view.base[0]]
    overlay = read_comparison(context.root / view.overlay["comparison"])
    aggregates = overlay.aggregates
    tree_ids = set(tree.index)

    # --- compact index the front-end filters against -------------------------
    sexes: list[str] = []
    labels: list[str] = []
    clids: list[str] = []
    sex_ix: dict[str, int] = {}
    label_ix: dict[str, int] = {}
    clid_ix: dict[str, int] = {}

    def intern(value: str, table: list[str], index: dict[str, int]) -> int:
        got = index.get(value)
        if got is None:
            got = len(table)
            index[value] = got
            table.append(value)
        return got

    rows: list[list[int]] = []
    for row in overlay.mapped_rows:
        rows.append([
            intern(row["sex"], sexes, sex_ix),
            intern(row["ann_finest_level"], labels, label_ix),
            intern(row["clid"], clids, clid_ix),
            row["azimuth_count"],
            row["pan_human_count"],
            row["both_same_cell_count"],
            row["azimuth_only_count"],
            row["pan_human_only_count"],
            row["union_count"],
            row["author_cohort_size"],
        ])

    # --- nodes ---------------------------------------------------------------
    nodes: list[dict[str, Any]] = []
    status_counts = {"shared": 0, "azimuth_only": 0, "pan_only": 0}
    comparison_node_count = 0

    for src in tree.nodes:
        node = copy.deepcopy(src)
        node_id = node["data"]["id"]
        agg = aggregates.get(node_id)
        is_comparison = bool(agg and agg["union"] > 0)
        status = agg["status"] if is_comparison else "neutral"
        if status in status_counts:
            status_counts[status] += 1
        if is_comparison:
            comparison_node_count += 1

        # terminalStatus seeds the unfiltered ("All") scope; the front-end
        # recolours from the index whenever a filter changes.
        node["data"]["terminalStatus"] = status
        node["data"]["styleData"] = {"isComparison": 1 if is_comparison else 0}
        nodes.append(node)

    outside = {c for c, a in aggregates.items() if a["union"] > 0} - tree_ids

    cohorts = {(r["sex"], r["ann_finest_level"]): r["author_cohort_size"]
               for r in overlay.mapped_rows}

    summary = {
        "inputFile": overlay.input_file,
        "rowCount": overlay.row_count,
        "nodeCount": len(nodes),
        "edgeCount": len(tree.edges),
        "rootCount": tree.summary.get("rootCount", 1),
        "comparisonNodeCount": comparison_node_count,
        "sharedCount": status_counts["shared"],
        "azimuthOnlyCount": status_counts["azimuth_only"],
        "panOnlyCount": status_counts["pan_only"],
        "outsideTreeCount": len(outside),
        "outsideTree": sorted(outside),
        "mappingStatusCounts": overlay.mapping_status_counts,
        "cohortCount": len(cohorts),
        "cohortCellCount": sum(cohorts.values()),
        "partitionCount": view.raw.get("params", {}).get("partitionCount", 0),
        "filterIndex": {
            "sexes": sexes,
            "labels": labels,
            "clids": clids,
            # [sex, label, clid, azimuth, pan, both, azOnly, panOnly, union, cohortSize]
            "rows": rows,
        },
    }

    return normalize_payload(nodes, tree.edges, summary)

"""Parse a CTann-style CSV into the canonical reference tree.

This is the shared *data root* of the dependency forest. It replaces the three
near-identical ``read_supertree`` copies that lived in the old standalone
builders; the node/edge/layout algorithm is preserved verbatim so existing
visualizations render identically.

Source filtering
----------------
The supertree is built from *included* sources only (``exclude_sources`` names
the ones held out). Excluded rows are still parsed — they never contribute
nodes or edges, but their cell types are compared against the finished tree so
the view can report what each excluded source would have added.

``compare_specs`` names sources to overlay onto the finished tree. For each, a
node is marked when it is a **terminal node of the built supertree** and also
appears anywhere in that source's paths; nodes matched by several compare
sources become ``shared``. Cell types absent from the tree entirely are
reported as *missing*.

``build_reference_tree`` returns a :class:`ReferenceTree` whose ``nodes`` carry
the full ``data``/``classes``/``position`` shape the Cytoscape front-end
expects, plus an ``index`` mapping node id -> node so views can attach overlay
values by ontology id (the join key across the whole forest).
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .layout import COLUMN_DX, LEAF_STEP, MAX_PATH_LEVEL, ROOT_GAP, ROW_DY
from .ontology import detect_delimiter, normalize_ontology_id

REQUIRED_COLUMNS = {"CT/1 - Sources", "AS/1/ID", "AS/1/LABEL"}


@dataclass
class ReferenceTree:
    """Canonical tree shared by every view built on this data root."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    summary: dict[str, Any]
    index: dict[str, dict[str, Any]] = field(default_factory=dict)

    def node(self, node_id: str) -> dict[str, Any] | None:
        return self.index.get(node_id)


def build_reference_tree(
    path: Path,
    *,
    exclude_sources: Iterable[str] = (),
    compare_specs: Iterable[dict[str, str]] = (),
) -> ReferenceTree:
    """Read ``path`` and materialize the canonical reference tree."""
    delimiter = detect_delimiter(path)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = set(reader.fieldnames or [])

        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(
                f"Missing required columns in {path}: {sorted(missing)}"
            )

        rows = list(reader)

    excluded_keys = {value.strip().casefold() for value in exclude_sources}
    compare_specs = list(compare_specs)

    # Collected for every source, included or not, so excluded sources can be
    # compared against the finished tree.
    source_all_nodes: dict[str, set[str]] = defaultdict(set)
    source_row_counts: Counter[str] = Counter()
    global_labels: dict[str, str] = {}

    # Every node appearing anywhere along an *included* source path.
    node_sources: dict[str, set[str]] = defaultdict(set)
    node_source_displays: dict[str, set[str]] = defaultdict(set)

    # Only the final, most-specific node in each included row's path.
    terminal_sources: dict[str, set[str]] = defaultdict(set)
    terminal_source_displays: dict[str, set[str]] = defaultdict(set)

    labels: dict[str, str] = {}
    label_variants: dict[str, set[str]] = defaultdict(set)

    parents: dict[str, set[str]] = defaultdict(set)
    children: dict[str, set[str]] = defaultdict(set)
    edge_counts: Counter[tuple[str, str]] = Counter()

    valid_row_count = 0
    empty_path_row_count = 0
    excluded_row_count = 0

    for row in rows:
        source_raw = (row.get("CT/1 - Sources") or "").strip()
        source_display = source_raw or "(blank)"
        source_norm = source_display.casefold()
        source_row_counts[source_display] += 1

        path_nodes: list[tuple[str, str]] = []

        for level in range(1, MAX_PATH_LEVEL + 1):
            node_id = normalize_ontology_id(row.get(f"AS/{level}/ID"))
            node_label = (row.get(f"AS/{level}/LABEL") or "").strip()

            if node_id:
                path_nodes.append((node_id, node_label or node_id))

        if not path_nodes:
            empty_path_row_count += 1
            continue

        for node_id, node_label in path_nodes:
            source_all_nodes[source_display].add(node_id)
            global_labels.setdefault(node_id, node_label)

        # Held-out sources never contribute nodes or edges to the supertree.
        if source_norm in excluded_keys:
            excluded_row_count += 1
            continue

        valid_row_count += 1

        terminal_id = path_nodes[-1][0]
        terminal_sources[terminal_id].add(source_norm)
        terminal_source_displays[terminal_id].add(source_display)

        previous: str | None = None

        for node_id, node_label in path_nodes:
            # Later rows may update the preferred display label for the same id.
            labels[node_id] = node_label
            global_labels[node_id] = node_label
            label_variants[node_id].add(node_label)

            node_sources[node_id].add(source_norm)
            node_source_displays[node_id].add(source_display)

            if previous and previous != node_id:
                parents[node_id].add(previous)
                children[previous].add(node_id)
                edge_counts[(previous, node_id)] += 1

            previous = node_id

    all_nodes = set(labels)
    if not all_nodes:
        raise ValueError(f"No supertree nodes were found in {path}.")

    indegree = {node: len(parents.get(node, set())) for node in all_nodes}
    roots = sorted(
        [node for node, degree in indegree.items() if degree == 0],
        key=lambda node: (labels.get(node, ""), node),
    )
    if not roots:
        roots = [min(all_nodes)]

    # Shortest distance from any root, matching the original layout logic.
    depth: dict[str, int] = {}
    queue: deque[str] = deque()

    for root in roots:
        depth[root] = 0
        queue.append(root)

    while queue:
        node = queue.popleft()
        ordered_children = sorted(
            children.get(node, set()),
            key=lambda child: (
                -edge_counts[(node, child)],
                labels.get(child, ""),
                child,
            ),
        )
        for child in ordered_children:
            candidate = depth[node] + 1
            if child not in depth or candidate < depth[child]:
                depth[child] = candidate
                queue.append(child)

    for node in all_nodes:
        depth.setdefault(node, 0)

    # Choose one primary parent solely for stable layout. All original
    # parent-child edges remain visible in the final graph.
    primary_parent: dict[str, str] = {}
    for node in all_nodes:
        node_parents = parents.get(node, set())
        if not node_parents:
            continue
        ranked = sorted(
            node_parents,
            key=lambda parent: (
                -edge_counts[(parent, node)],
                depth.get(parent, 999),
                labels.get(parent, ""),
                parent,
            ),
        )
        primary_parent[node] = ranked[0]

    primary_children: dict[str, list[str]] = defaultdict(list)
    for child, parent in primary_parent.items():
        primary_children[parent].append(child)

    for parent in primary_children:
        primary_children[parent].sort(
            key=lambda child: (
                depth.get(child, 999),
                -len(children.get(child, set())),
                labels.get(child, ""),
                child,
            )
        )

    # Recursive leaf-order layout, matching the original Matplotlib script.
    y_position: dict[str, float] = {}
    cursor = 0.0
    active_stack: set[str] = set()

    def assign_y(node: str) -> None:
        nonlocal cursor
        if node in y_position:
            return
        if node in active_stack:
            raise ValueError(
                f"A cycle was encountered in the primary-parent layout at {node}."
            )
        active_stack.add(node)
        child_list = primary_children.get(node, [])
        if not child_list:
            y_position[node] = cursor
            cursor += LEAF_STEP
        else:
            for child in child_list:
                assign_y(child)
            y_position[node] = sum(
                y_position[child] for child in child_list
            ) / len(child_list)
        active_stack.remove(node)

    for index, root in enumerate(roots):
        assign_y(root)
        if index < len(roots) - 1:
            cursor += ROOT_GAP

    for node in sorted(
        all_nodes,
        key=lambda value: (depth.get(value, 999), labels.get(value, ""), value),
    ):
        if node not in y_position:
            y_position[node] = cursor
            cursor += LEAF_STEP

    def primary_path(node_id: str) -> list[str]:
        result = [node_id]
        seen = {node_id}
        current = node_id
        while current in primary_parent:
            current = primary_parent[current]
            if current in seen:
                break
            seen.add(current)
            result.append(current)
        result.reverse()
        return result

    # Terminal nodes of the *built* supertree, and the compare-source overlay.
    terminal_node_ids = {node for node in all_nodes if terminal_sources.get(node)}

    nodes_by_key: dict[str, set[str]] = defaultdict(set)
    for source_name, source_nodes in source_all_nodes.items():
        nodes_by_key[source_name.casefold()] |= source_nodes

    compare_nodes: dict[str, set[str]] = {
        spec["id"]: nodes_by_key.get(spec["source"].casefold(), set())
        for spec in compare_specs
    }

    nodes: list[dict[str, Any]] = []
    node_index: dict[str, dict[str, Any]] = {}

    matched_counts: dict[str, int] = {spec["id"]: 0 for spec in compare_specs}
    shared_terminal_count = 0

    for node_id in sorted(
        all_nodes,
        key=lambda value: (depth.get(value, 999), labels.get(value, ""), value),
    ):
        is_terminal = node_id in terminal_node_ids
        matches = [
            spec["id"]
            for spec in compare_specs
            if node_id in compare_nodes[spec["id"]]
        ]

        if is_terminal and matches:
            if len(matches) > 1:
                terminal_status = "shared"
                classes = "shared-terminal"
                shared_terminal_count += 1
            else:
                terminal_status = matches[0]
                classes = f"{matches[0]}-terminal"
                matched_counts[matches[0]] += 1
        else:
            terminal_status = "neutral"
            classes = "neutral-node"

        path_ids = primary_path(node_id)
        path_labels = [labels.get(value, value) for value in path_ids]

        parent_ids = sorted(
            parents.get(node_id, set()),
            key=lambda value: (labels.get(value, ""), value),
        )
        child_ids = sorted(
            children.get(node_id, set()),
            key=lambda value: (labels.get(value, ""), value),
        )

        node = {
            "data": {
                "id": node_id,
                "label": labels.get(node_id, node_id),
                "labelVariants": sorted(
                    label_variants.get(node_id, set()), key=str.casefold
                ),
                "depth": depth.get(node_id, 0),
                "parentIds": parent_ids,
                "parentLabels": [labels.get(v, v) for v in parent_ids],
                "childIds": child_ids,
                "childLabels": [labels.get(v, v) for v in child_ids],
                "parentCount": len(parent_ids),
                "childCount": len(child_ids),
                "isRoot": node_id in roots,
                "isPrimaryParentTarget": node_id in primary_parent,
                "primaryParentId": primary_parent.get(node_id, ""),
                "primaryParentLabel": labels.get(
                    primary_parent.get(node_id, ""), ""
                ),
                "primaryPathIds": path_ids,
                "primaryPathLabels": path_labels,
                "primaryPathText": " → ".join(path_labels),
                "sources": sorted(
                    node_source_displays.get(node_id, set()), key=str.casefold
                ),
                "terminalSources": sorted(
                    terminal_source_displays.get(node_id, set()),
                    key=str.casefold,
                ),
                "terminalStatus": terminal_status,
            },
            "classes": classes,
            "position": {
                "x": depth.get(node_id, 0) * COLUMN_DX,
                "y": y_position[node_id] * ROW_DY,
            },
        }
        nodes.append(node)
        node_index[node_id] = node

    edges: list[dict[str, Any]] = []
    for index, (parent, child) in enumerate(
        sorted(
            edge_counts,
            key=lambda pair: (
                depth.get(pair[0], 999),
                labels.get(pair[0], ""),
                labels.get(pair[1], ""),
                pair,
            ),
        )
    ):
        is_primary = primary_parent.get(child) == parent
        edges.append(
            {
                "data": {
                    "id": f"edge-{index}",
                    "source": parent,
                    "target": child,
                    "rowCount": edge_counts[(parent, child)],
                    "isPrimary": is_primary,
                },
                "classes": "primary-edge" if is_primary else "secondary-edge",
            }
        )

    # Per-source inventory: which sources built the tree, and for each held-out
    # source the cell types it would have contributed that the tree lacks.
    source_inventory: list[dict[str, Any]] = []
    for source_name in sorted(source_all_nodes, key=str.casefold):
        source_nodes = source_all_nodes[source_name]
        included = source_name.casefold() not in excluded_keys
        entry: dict[str, Any] = {
            "source": source_name,
            "rowCount": source_row_counts[source_name],
            "nodeCount": len(source_nodes),
            "included": included,
        }
        if not included:
            absent = sorted(source_nodes - all_nodes)
            entry["missingCount"] = len(absent)
            entry["missing"] = [
                {"id": value, "label": global_labels.get(value, value)}
                for value in absent
            ]
        source_inventory.append(entry)

    compare_summary: list[dict[str, Any]] = []
    for spec in compare_specs:
        source_nodes = compare_nodes[spec["id"]]
        absent = sorted(source_nodes - all_nodes)
        compare_summary.append(
            {
                "id": spec["id"],
                "source": spec["source"],
                "label": spec.get("label", spec["source"]),
                "nodeCount": len(source_nodes),
                "terminalMatchCount": len(source_nodes & terminal_node_ids),
                "inTreeNonTerminalCount": len(
                    (source_nodes & all_nodes) - terminal_node_ids
                ),
                "missingCount": len(absent),
                "missing": absent,  # CLID only, by request
            }
        )

    summary = {
        "inputFile": path.name,
        "rowCount": len(rows),
        "validPathRowCount": valid_row_count,
        "emptyPathRowCount": empty_path_row_count,
        "excludedRowCount": excluded_row_count,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "rootCount": len(roots),
        "terminalNodeCount": len(terminal_node_ids),
        "multiParentNodeCount": sum(
            1 for node in all_nodes if len(parents.get(node, set())) > 1
        ),
        "sharedTerminalCount": shared_terminal_count,
        "otherNodeCount": (
            len(nodes) - sum(matched_counts.values()) - shared_terminal_count
        ),
        "sourceInventory": source_inventory,
        "compareSources": compare_summary,
    }
    for compare_id, count in matched_counts.items():
        summary[f"{compare_id}TerminalCount"] = count

    return ReferenceTree(
        nodes=nodes, edges=edges, summary=summary, index=node_index
    )

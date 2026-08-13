"""Build Task 2: HRApop v1.1 lung Azimuth vs Pan-human Azimuth.

The generated HTML overlays direct Cell Ontology outputs on the v9 reference
supertree:
- red: organ-specific Azimuth only
- blue: Pan-human Azimuth only
- purple: exact Cell Ontology ID in both
- gray: not directly output by either

Hovering a node draws its primary path to a root as a solid line and all
available descendant branches as equally thick dotted lines. Clicking a node
opens hierarchy and provenance details. The comparison drawer reports exact
node and inclusive node-plus-descendants population values by anatomical
structure and sex.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

ROOT_ID = "CL:0000000"
MAX_PATH_LEVEL = 12
COLUMN_DX = 292.5
ROW_DY = 8.5
LEAF_STEP = 3.0
ROOT_GAP = 2.0

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SUPERTREE = SCRIPT_DIR / "data" / "ctann-v9.csv"
DEFAULT_HRAPOP = (
    SCRIPT_DIR
    / "data"
    / "cell-types-in-anatomical-structurescts-per-as.csv"
)
DEFAULT_OUTPUT = (
    SCRIPT_DIR
    / "output_htmls"
    / "hrapop-v1.1-lung-azimuth-pan-human-comparison.html"
)

COLORS = {
    "neutral": "#8A8F98",
    "lung_only": "#E53935",
    "pan_only": "#1565C0",
    "shared": "#7B1FA2",
}


def normalize_ontology_id(value: str | None) -> str:
    """Normalize common OBO URI, underscore, and CURIE identifiers."""
    raw = (value or "").strip()
    if not raw:
        return ""

    for prefix in (
        "https://purl.obolibrary.org/obo/",
        "http://purl.obolibrary.org/obo/",
    ):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break

    match = re.fullmatch(
        r"([A-Za-z][A-Za-z0-9-]*)[_:]([A-Za-z0-9_.-]+)",
        raw,
    )
    if match:
        return f"{match.group(1).upper()}:{match.group(2)}"

    return raw


def detect_delimiter(path: Path) -> str:
    if path.suffix.lower() in {".tsv", ".tab"}:
        return "\t"

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(65536)

    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def read_supertree(path: Path) -> dict[str, Any]:
    delimiter = detect_delimiter(path)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = set(reader.fieldnames or [])
        required = {"AS/1/ID", "AS/1/LABEL"}
        missing = required - fieldnames
        if missing:
            raise ValueError(
                f"Missing required supertree columns in {path}: "
                f"{sorted(missing)}"
            )
        rows = list(reader)

    labels: dict[str, str] = {}
    label_variants: dict[str, set[str]] = defaultdict(set)
    node_sources: dict[str, set[str]] = defaultdict(set)
    terminal_sources: dict[str, set[str]] = defaultdict(set)
    parents: dict[str, set[str]] = defaultdict(set)
    children: dict[str, set[str]] = defaultdict(set)
    edge_counts: Counter[tuple[str, str]] = Counter()

    valid_rows = 0
    empty_rows = 0

    for row in rows:
        source = (row.get("CT/1 - Sources") or "").strip() or "(blank)"
        path_nodes: list[tuple[str, str]] = []

        for level in range(1, MAX_PATH_LEVEL + 1):
            node_id = normalize_ontology_id(row.get(f"AS/{level}/ID"))
            node_label = (row.get(f"AS/{level}/LABEL") or "").strip()
            if node_id:
                path_nodes.append((node_id, node_label or node_id))

        if not path_nodes:
            empty_rows += 1
            continue

        valid_rows += 1
        terminal_sources[path_nodes[-1][0]].add(source)

        previous: str | None = None
        for node_id, node_label in path_nodes:
            labels[node_id] = node_label
            label_variants[node_id].add(node_label)
            node_sources[node_id].add(source)

            if previous and previous != node_id:
                parents[node_id].add(previous)
                children[previous].add(node_id)
                edge_counts[(previous, node_id)] += 1
            previous = node_id

    all_nodes = set(labels)
    if not all_nodes:
        raise ValueError(f"No hierarchy nodes were found in {path}.")

    roots = sorted(
        [node for node in all_nodes if not parents.get(node)],
        key=lambda node: (labels.get(node, ""), node),
    )
    if not roots:
        roots = [min(all_nodes)]

    depth: dict[str, int] = {}
    queue: deque[str] = deque()
    for root in roots:
        depth[root] = 0
        queue.append(root)

    while queue:
        node = queue.popleft()
        ordered = sorted(
            children.get(node, set()),
            key=lambda child: (
                -edge_counts[(node, child)],
                labels.get(child, ""),
                child,
            ),
        )
        for child in ordered:
            candidate = depth[node] + 1
            if child not in depth or candidate < depth[child]:
                depth[child] = candidate
                queue.append(child)

    for node in all_nodes:
        depth.setdefault(node, 0)

    # A single primary parent is used only for stable layout and the solid
    # root path. Every original parent-child edge remains in the graph.
    primary_parent: dict[str, str] = {}
    for node in all_nodes:
        node_parents = parents.get(node, set())
        if not node_parents:
            continue
        primary_parent[node] = sorted(
            node_parents,
            key=lambda parent: (
                -edge_counts[(parent, node)],
                depth.get(parent, 999),
                labels.get(parent, ""),
                parent,
            ),
        )[0]

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

    y_position: dict[str, float] = {}
    cursor = 0.0
    active: set[str] = set()

    def assign_y(node: str) -> None:
        nonlocal cursor
        if node in y_position:
            return
        if node in active:
            raise ValueError(
                f"Cycle encountered in primary-parent layout at {node}."
            )

        active.add(node)
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
        active.remove(node)

    for index, root in enumerate(roots):
        assign_y(root)
        if index < len(roots) - 1:
            cursor += ROOT_GAP

    for node in sorted(
        all_nodes,
        key=lambda value: (
            depth.get(value, 999),
            labels.get(value, ""),
            value,
        ),
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

    ordered_children = {
        node: sorted(
            children.get(node, set()),
            key=lambda child: (labels.get(child, ""), child),
        )
        for node in all_nodes
    }

    return {
        "labels": labels,
        "label_variants": label_variants,
        "node_sources": node_sources,
        "terminal_sources": terminal_sources,
        "parents": parents,
        "children": ordered_children,
        "edge_counts": edge_counts,
        "depth": depth,
        "primary_parent": primary_parent,
        "primary_path": primary_path,
        "y_position": y_position,
        "roots": roots,
        "nodes": all_nodes,
        "row_count": len(rows),
        "valid_row_count": valid_rows,
        "empty_row_count": empty_rows,
    }


def parse_float(value: str | None, field: str) -> float:
    raw = (value or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for {field}: {value!r}") from exc


def read_hrapop(
    path: Path,
    organ: str,
    lung_tool: str,
    pan_tool: str,
    modality: str,
) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "organ",
            "as",
            "as_label",
            "sex",
            "tool",
            "modality",
            "cell_id",
            "cell_label",
            "cell_count",
            "cell_percentage",
            "dataset_count",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Missing required HRApop columns in {path}: {sorted(missing)}"
            )
        rows = list(reader)

    organ_key = organ.strip().casefold()
    lung_tool_key = lung_tool.strip().casefold()
    pan_tool_key = pan_tool.strip().casefold()
    modality_key = modality.strip().casefold()

    metadata: dict[str, dict[str, dict[str, Any]]] = {
        "lung": defaultdict(
            lambda: {
                "labels": set(),
                "sexes": set(),
                "as_labels": set(),
                "dataset_counts": set(),
            }
        ),
        "pan": defaultdict(
            lambda: {
                "labels": set(),
                "sexes": set(),
                "as_labels": set(),
                "dataset_counts": set(),
            }
        ),
    }
    groups: dict[str, dict[tuple[str, str], dict[str, Any]]] = {
        "lung": {},
        "pan": {},
    }

    filtered_row_count = 0
    blank_id_row_count = 0

    for row in rows:
        row_organ = (row.get("organ") or "").strip().casefold()
        row_modality = (row.get("modality") or "").strip().casefold()
        row_tool = (row.get("tool") or "").strip().casefold()

        if row_organ != organ_key or row_modality != modality_key:
            continue
        if row_tool not in {lung_tool_key, pan_tool_key}:
            continue

        filtered_row_count += 1
        side = "lung" if row_tool == lung_tool_key else "pan"

        as_id = (row.get("as") or "").strip()
        as_label = (row.get("as_label") or "").strip()
        sex = (row.get("sex") or "").strip() or "Unknown"
        as_key = as_id or f"LABEL::{as_label.casefold()}"
        group_key = (as_key, sex)

        group = groups[side].setdefault(
            group_key,
            {
                "asId": as_id,
                "asLabels": set(),
                "sex": sex,
                "totalCount": 0.0,
                "sourcePercentageTotal": 0.0,
                "byCell": {},
            },
        )
        if as_label:
            group["asLabels"].add(as_label)

        count = parse_float(row.get("cell_count"), "cell_count")
        percentage = parse_float(
            row.get("cell_percentage"), "cell_percentage"
        )
        group["totalCount"] += count
        group["sourcePercentageTotal"] += percentage

        cell_id = normalize_ontology_id(row.get("cell_id"))
        if not cell_id:
            blank_id_row_count += 1
            continue

        cell_label = (row.get("cell_label") or "").strip()
        dataset_count = (row.get("dataset_count") or "").strip()

        item = metadata[side][cell_id]
        if cell_label:
            item["labels"].add(cell_label)
        if as_label:
            item["as_labels"].add(as_label)
        if dataset_count:
            item["dataset_counts"].add(dataset_count)
        item["sexes"].add(sex)

        cell = group["byCell"].setdefault(
            cell_id,
            {"count": 0.0, "percentage": 0.0, "labels": set()},
        )
        cell["count"] += count
        cell["percentage"] += percentage
        if cell_label:
            cell["labels"].add(cell_label)

    if filtered_row_count == 0:
        raise ValueError(
            f"No HRApop rows matched organ={organ!r}, modality={modality!r}, "
            f"and tools {lung_tool!r}/{pan_tool!r}."
        )

    return {
        "filtered_row_count": filtered_row_count,
        "blank_id_row_count": blank_id_row_count,
        "metadata": metadata,
        "groups": groups,
        "lung_ids": set(metadata["lung"]),
        "pan_ids": set(metadata["pan"]),
    }


def sorted_values(values: set[str]) -> list[str]:
    return sorted(values, key=lambda value: value.casefold())


def materialize_metadata(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return {
            "labels": [],
            "sexes": [],
            "asLabels": [],
            "datasetCounts": [],
        }
    return {
        "labels": sorted_values(item["labels"]),
        "sexes": sorted_values(item["sexes"]),
        "asLabels": sorted_values(item["as_labels"]),
        "datasetCounts": sorted_values(item["dataset_counts"]),
    }


def build_graph_payload(
    tree: dict[str, Any],
    hra: dict[str, Any],
    validation_tolerance: float = 1e-9,
) -> dict[str, Any]:
    labels: dict[str, str] = tree["labels"]
    parents: dict[str, set[str]] = tree["parents"]
    children: dict[str, list[str]] = tree["children"]
    depth: dict[str, int] = tree["depth"]
    y_position: dict[str, float] = tree["y_position"]
    primary_parent: dict[str, str] = tree["primary_parent"]
    primary_path = tree["primary_path"]
    all_nodes: set[str] = tree["nodes"]

    lung_ids: set[str] = hra["lung_ids"]
    pan_ids: set[str] = hra["pan_ids"]
    union_ids = lung_ids | pan_ids

    subtree_node_ids: dict[str, set[str]] = {}
    visiting: set[str] = set()

    def collect_subtree(node: str) -> set[str]:
        if node in subtree_node_ids:
            return subtree_node_ids[node]
        if node in visiting:
            raise ValueError(f"Cycle encountered in hierarchy at {node}.")
        visiting.add(node)
        values = {node}
        for child in children.get(node, []):
            values.update(collect_subtree(child))
        visiting.remove(node)
        subtree_node_ids[node] = values
        return values

    for node in all_nodes:
        collect_subtree(node)

    def group_identity(group_key: tuple[str, str]) -> tuple[str, str]:
        groups_found = [
            hra["groups"][side][group_key]
            for side in ("lung", "pan")
            if group_key in hra["groups"][side]
        ]
        as_ids = [group["asId"] for group in groups_found if group["asId"]]
        label_values: set[str] = set()
        for group in groups_found:
            label_values.update(group["asLabels"])
        as_id = as_ids[0] if as_ids else ""
        as_label = (
            sorted_values(label_values)[0]
            if label_values
            else (as_id or group_key[0])
        )
        return as_id, as_label

    all_group_keys = sorted(
        set(hra["groups"]["lung"]) | set(hra["groups"]["pan"]),
        key=lambda key: (
            group_identity(key)[1].casefold(),
            key[1].casefold(),
            group_identity(key)[0] or key[0],
        ),
    )

    validation = {
        "groupCaseCount": 0,
        "exactCaseCount": 0,
        "subtreeCaseCount": 0,
        "maxGroupPercentageDifference": 0.0,
        "maxExactDifference": 0.0,
        "maxSubtreeDifference": 0.0,
    }

    for side in ("lung", "pan"):
        for group in hra["groups"][side].values():
            total_count = group["totalCount"]
            group_diff = abs(group["sourcePercentageTotal"] - 1.0)
            validation["groupCaseCount"] += 1
            validation["maxGroupPercentageDifference"] = max(
                validation["maxGroupPercentageDifference"], group_diff
            )
            if group_diff > validation_tolerance:
                raise ValueError(
                    "cell_percentage values do not sum to 1 for "
                    f"{side} / {sorted_values(group['asLabels'])[0] if group['asLabels'] else group['asId']} / "
                    f"{group['sex']}: difference={group_diff:.3g}"
                )

            for cell_id, cell in group["byCell"].items():
                derived = cell["count"] / total_count if total_count > 0 else 0.0
                diff = abs(cell["percentage"] - derived)
                validation["exactCaseCount"] += 1
                validation["maxExactDifference"] = max(
                    validation["maxExactDifference"], diff
                )
                if diff > validation_tolerance:
                    raise ValueError(
                        "Exact percentage validation failed for "
                        f"{cell_id} / {side} / {group['sex']}: "
                        f"difference={diff:.3g}"
                    )

    def values_for_side(
        side: str,
        group_key: tuple[str, str],
        included_ids: set[str],
        exact: bool,
    ) -> dict[str, Any]:
        group = hra["groups"][side].get(group_key)
        if group is None:
            return {"available": False, "count": None, "percentage": None}

        count = 0.0
        source_percentage = 0.0
        for cell_id in included_ids:
            cell = group["byCell"].get(cell_id)
            if cell is None:
                continue
            count += cell["count"]
            source_percentage += cell["percentage"]

        if exact:
            percentage = source_percentage
        else:
            percentage = count / group["totalCount"] if group["totalCount"] > 0 else 0.0
            diff = abs(source_percentage - percentage)
            validation["subtreeCaseCount"] += 1
            validation["maxSubtreeDifference"] = max(
                validation["maxSubtreeDifference"], diff
            )
            if diff > validation_tolerance:
                raise ValueError(
                    "Subtree percentage validation failed for "
                    f"{side} / {group['sex']}: difference={diff:.3g}"
                )

        return {"available": True, "count": count, "percentage": percentage}

    def comparison_rows(
        included_ids: set[str], exact: bool
    ) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for group_key in all_group_keys:
            _, sex = group_key
            as_id, as_label = group_identity(group_key)
            lung = values_for_side("lung", group_key, included_ids, exact)
            pan = values_for_side("pan", group_key, included_ids, exact)
            both = lung["available"] and pan["available"]
            output.append(
                {
                    "asId": as_id,
                    "asLabel": as_label,
                    "sex": sex,
                    "lungAvailable": lung["available"],
                    "panAvailable": pan["available"],
                    "lungCount": lung["count"],
                    "panCount": pan["count"],
                    "absCountDifference": (
                        abs(lung["count"] - pan["count"]) if both else None
                    ),
                    "lungPercentage": lung["percentage"],
                    "panPercentage": pan["percentage"],
                    "absPercentageDifference": (
                        abs(lung["percentage"] - pan["percentage"])
                        if both
                        else None
                    ),
                }
            )
        return output

    edge_pairs = sorted(
        tree["edge_counts"],
        key=lambda pair: (
            depth.get(pair[0], 999),
            labels.get(pair[0], ""),
            labels.get(pair[1], ""),
            pair,
        ),
    )
    edge_id_by_pair: dict[tuple[str, str], str] = {}
    edges: list[dict[str, Any]] = []
    for index, (parent, child) in enumerate(edge_pairs):
        edge_id = f"edge-{index}"
        edge_id_by_pair[(parent, child)] = edge_id
        edges.append(
            {
                "data": {
                    "id": edge_id,
                    "source": parent,
                    "target": child,
                    "rowCount": tree["edge_counts"][(parent, child)],
                    "isPrimary": primary_parent.get(child) == parent,
                }
            }
        )

    nodes: list[dict[str, Any]] = []
    comparisons: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for node_id in sorted(
        all_nodes,
        key=lambda value: (
            depth.get(value, 999), labels.get(value, ""), value
        ),
    ):
        in_lung = node_id in lung_ids
        in_pan = node_id in pan_ids
        if in_lung and in_pan:
            status = "shared"
        elif in_lung:
            status = "lung_only"
        elif in_pan:
            status = "pan_only"
        else:
            status = "neutral"

        path_ids = primary_path(node_id)
        path_labels = [labels.get(value, value) for value in path_ids]
        path_edge_ids = [
            edge_id_by_pair[(source, target)]
            for source, target in zip(path_ids, path_ids[1:])
            if (source, target) in edge_id_by_pair
        ]

        node_subtree = subtree_node_ids[node_id]
        lung_subtree = node_subtree & lung_ids
        pan_subtree = node_subtree & pan_ids
        is_leaf = len(children.get(node_id, [])) == 0

        comparisons[node_id] = {
            "exactRows": comparison_rows({node_id}, exact=True),
            "subtreeRows": (
                [] if is_leaf else comparison_rows(node_subtree, exact=False)
            ),
        }

        parent_ids = sorted(
            parents.get(node_id, set()),
            key=lambda value: (labels.get(value, ""), value),
        )
        child_ids = children.get(node_id, [])

        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": labels.get(node_id, node_id),
                    "displayLabel": labels.get(node_id, node_id),
                    "status": status,
                    "fillColor": COLORS[status],
                    "isCompared": status != "neutral",
                    "inLung": in_lung,
                    "inPan": in_pan,
                    "depth": depth.get(node_id, 0),
                    "parentId": primary_parent.get(node_id, ""),
                    "parentLabel": labels.get(primary_parent.get(node_id, ""), ""),
                    "parentIds": parent_ids,
                    "parentLabels": [labels.get(value, value) for value in parent_ids],
                    "childIds": child_ids,
                    "childCount": len(child_ids),
                    "isLeaf": is_leaf,
                    "descendantCount": len(node_subtree) - 1,
                    "pathIds": path_ids,
                    "pathEdgeIds": path_edge_ids,
                    "pathText": " → ".join(path_labels),
                    "sources": sorted_values(tree["node_sources"].get(node_id, set())),
                    "terminalSources": sorted_values(tree["terminal_sources"].get(node_id, set())),
                    "lungMeta": materialize_metadata(hra["metadata"]["lung"].get(node_id)),
                    "panMeta": materialize_metadata(hra["metadata"]["pan"].get(node_id)),
                    "subtreeLungCount": len(lung_subtree),
                    "subtreePanCount": len(pan_subtree),
                    "subtreeSharedCount": len(lung_subtree & pan_subtree),
                    "subtreeDifferenceCount": len(lung_subtree ^ pan_subtree),
                },
                "position": {
                    "x": depth.get(node_id, 0) * COLUMN_DX,
                    "y": y_position[node_id] * ROW_DY,
                },
            }
        )

    unmapped: list[dict[str, Any]] = []
    for cell_id in sorted(union_ids - all_nodes):
        in_lung = cell_id in lung_ids
        in_pan = cell_id in pan_ids
        if in_lung and in_pan:
            tool_status = "Azimuth and Pan-human Azimuth"
        elif in_lung:
            tool_status = "Azimuth only"
        else:
            tool_status = "Pan-human Azimuth only"
        labels_found = sorted(
            set(materialize_metadata(hra["metadata"]["lung"].get(cell_id))["labels"])
            | set(materialize_metadata(hra["metadata"]["pan"].get(cell_id))["labels"]),
            key=str.casefold,
        )
        unmapped.append(
            {"id": cell_id, "labels": labels_found, "toolStatus": tool_status}
        )

    summary = {
        "treeNodeCount": len(all_nodes),
        "treeEdgeCount": len(edges),
        "rootCount": len(tree["roots"]),
        "multiParentNodeCount": sum(
            1 for node in all_nodes if len(parents.get(node, set())) > 1
        ),
        "filteredRowCount": hra["filtered_row_count"],
        "blankIdRowCount": hra["blank_id_row_count"],
        "lungCount": len(lung_ids),
        "panCount": len(pan_ids),
        "sharedCount": len(lung_ids & pan_ids),
        "lungOnlyCount": len(lung_ids - pan_ids),
        "panOnlyCount": len(pan_ids - lung_ids),
        "mappedComparisonCount": len(union_ids & all_nodes),
        "unmappedComparisonCount": len(union_ids - all_nodes),
        "validation": validation,
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "comparisons": comparisons,
        "unmapped": unmapped,
        "summary": summary,
    }


def display_tool_name(value: str) -> str:
    normalized = value.strip().casefold().replace("_", "-")
    if normalized == "azimuth":
        return "Azimuth"
    if normalized == "pan-human-azimuth":
        return "Pan-human Azimuth"
    return " ".join(part.capitalize() for part in normalized.split("-"))


HTML_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HRApop __ORGAN_TITLE__ Population View — Azimuth Comparison</title>
<style>
:root {
    --bg: #eef2f7;
    --panel: #ffffff;
    --border: #d7dde7;
    --text: #18212f;
    --muted: #647084;
    --accent: #155eef;
    --red: #E53935;
    --blue: #1565C0;
    --purple: #7B1FA2;
    --gray: #8A8F98;
    --details-width: 390px;
    --toolbar-height: 76px;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; overflow: hidden; }
body {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--text);
    background: var(--bg);
}
button, input, select { font: inherit; }
#app {
    height: 100%;
    display: grid;
    grid-template-rows: var(--toolbar-height) 1fr;
}
header {
    height: var(--toolbar-height);
    display: flex;
    align-items: center;
    gap: 13px;
    padding: 10px 16px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    z-index: 10;
}
.brand { min-width: 275px; }
.brand h1 { margin: 0 0 3px; font-size: 18px; line-height: 1.2; }
.brand p { margin: 0; color: var(--muted); font-size: 12px; }
.search-wrap { flex: 1; max-width: 520px; position: relative; }
#search {
    width: 100%; height: 40px; padding: 0 42px 0 13px;
    border: 1px solid var(--border); border-radius: 10px;
    outline: none; background: #fbfcfe;
}
#search:focus {
    border-color: #8ca9fb;
    box-shadow: 0 0 0 3px rgba(21, 94, 239, 0.12);
}
#searchButton {
    position: absolute; top: 4px; right: 4px; width: 34px; height: 32px;
    border: 0; border-radius: 8px; background: transparent; cursor: pointer;
}
.controls { display: flex; align-items: center; gap: 7px; margin-left: auto; }
.control {
    height: 38px; border: 1px solid var(--border); border-radius: 9px;
    background: #fff; color: #253246; cursor: pointer; padding: 0 10px;
}
.control:hover { background: #f4f7fb; }
.control.active { color: #1049b8; border-color: #a6baf2; background: #edf2ff; }
main {
    min-height: 0;
    display: grid;
    grid-template-columns: 1fr var(--details-width);
}
#graphWrap {
    position: relative; overflow: hidden; min-width: 0;
    background: radial-gradient(circle at 40% 35%, #fff 0, #f7f9fc 44%, #edf1f6 100%);
}
#cy { position: absolute; inset: 0; }
#details {
    background: var(--panel); border-left: 1px solid var(--border);
    padding: 18px; overflow: auto;
}
#details h2 { font-size: 18px; margin: 0 0 4px; overflow-wrap: anywhere; }
.node-id {
    font: 12px ui-monospace, SFMono-Regular, Menlo, monospace;
    color: var(--muted); margin-bottom: 14px; overflow-wrap: anywhere;
}
.placeholder { color: var(--muted); font-size: 14px; line-height: 1.55; }
.section { border-top: 1px solid #edf0f4; padding: 11px 0; }
.section:first-of-type { border-top: 0; }
.section-title {
    text-transform: uppercase; letter-spacing: 0.055em; font-size: 11px;
    font-weight: 750; color: var(--muted); margin-bottom: 6px;
}
.section-value { font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }
.pill {
    display: inline-flex; border: 1px solid #dce3ed; border-radius: 999px;
    background: #f8fafc; padding: 4px 8px; margin: 3px 4px 0 0; font-size: 12px;
}
.status-pill { color: #fff; border: 0; font-weight: 700; }
.tool-row {
    display: grid; grid-template-columns: 1fr auto; gap: 8px;
    padding: 7px 0; border-bottom: 1px solid #f0f2f5; font-size: 13px;
}
.tool-row:last-child { border-bottom: 0; }
.tool-name { font-weight: 720; }
.direct-yes { color: #11734b; font-weight: 750; }
.direct-no { color: var(--muted); font-weight: 650; }
.open-comparison {
    width: 100%; min-height: 42px; border: 0; border-radius: 9px;
    background: var(--accent); color: white; font-weight: 760; cursor: pointer;
    padding: 10px 14px;
}
.open-comparison:hover { background: #0d4ed1; }
.summary {
    position: absolute; top: 13px; left: 14px; z-index: 4; max-width: 500px;
    background: rgba(255,255,255,.95); border: 1px solid var(--border);
    border-radius: 10px; padding: 8px 10px;
    box-shadow: 0 3px 14px rgba(20,30,45,.08); font-size: 12px;
}
.summary strong { font-weight: 760; }
.legend {
    position: absolute;
    left: 50%;
    bottom: 14px;
    transform: translateX(-50%);
    width: 90%;
    z-index: 4;
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    column-gap: 14px;
    row-gap: 4px;
    align-items: center;
    background: rgba(255,255,255,.95);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 8px 12px;
    box-shadow: 0 3px 14px rgba(20,30,45,.08);
    font-size: 11px;
}
.legend-title {
    grid-column: 1 / -1;
    font-weight: 760;
    margin-bottom: 1px;
}
.legend-row {
    display: flex;
    align-items: center;
    gap: 7px;
    min-width: 0;
    line-height: 1.25;
}
.dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
.line-sample {
    width: 27px;
    height: 0;
    border-top: 4px solid #111827;
    flex: none;
}
.line-sample.subtree {
    border-top-style: dotted;
    border-top-color: #4B5563;
}
#tooltip {
    position: fixed; z-index: 999; display: none; max-width: 380px;
    background: rgba(17,24,39,.96); color: #fff; border-radius: 9px;
    padding: 10px 11px; font-size: 12px; line-height: 1.45;
    pointer-events: none; box-shadow: 0 8px 28px rgba(0,0,0,.22);
}
#tooltip .title { font-weight: 760; font-size: 13px; }
#tooltip .id { color: #cbd5e1; font-family: ui-monospace, monospace; margin: 2px 0 7px; }
#tooltip .path { color: #dbe4f0; margin-top: 7px; }
#toast {
    position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%) translateY(20px);
    opacity: 0; pointer-events: none; background: #111827; color: #fff;
    padding: 9px 13px; border-radius: 8px; font-size: 13px; z-index: 1200;
    transition: .18s ease;
}
#toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
.drawer-backdrop {
    position: fixed; inset: 0; background: rgba(15,23,42,.28); z-index: 1000;
    opacity: 0; pointer-events: none; transition: opacity .18s ease;
}
.drawer-backdrop.open { opacity: 1; pointer-events: auto; }
#comparisonDrawer {
    position: fixed; z-index: 1001; left: 4vw; right: 4vw; bottom: 0;
    height: min(78vh, 790px); background: #fff;
    border: 1px solid var(--border); border-bottom: 0;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 -12px 38px rgba(15,23,42,.18);
    transform: translateY(105%); transition: transform .22s ease;
    display: grid; grid-template-rows: auto auto auto 1fr;
    overflow: hidden;
}
#comparisonDrawer.open { transform: translateY(0); }
.drawer-header {
    display: flex; align-items: start; gap: 14px; padding: 14px 18px 11px;
    border-bottom: 1px solid var(--border);
}
.drawer-title-wrap { min-width: 0; flex: 1; }
.drawer-title { margin: 0; font-size: 18px; overflow-wrap: anywhere; }
.drawer-subtitle { margin-top: 3px; font-size: 12px; color: var(--muted); }
.drawer-close {
    width: 36px; height: 36px; border: 1px solid var(--border);
    border-radius: 9px; background: #fff; cursor: pointer; font-size: 20px;
}
.tabs { display: flex; gap: 8px; padding: 10px 18px 0; }
.tab {
    border: 1px solid var(--border); border-radius: 9px 9px 0 0;
    background: #f8fafc; color: #435067; padding: 8px 13px; cursor: pointer;
    font-weight: 700; font-size: 13px;
}
.tab.active { color: #1049b8; border-color: #a6baf2; background: #edf2ff; }
.tab[hidden] { display: none; }
.drawer-controls {
    display: flex; align-items: center; flex-wrap: wrap; gap: 9px;
    padding: 10px 18px; border-bottom: 1px solid var(--border); background: #fbfcfe;
}
.drawer-controls input, .drawer-controls select {
    height: 36px; border: 1px solid var(--border); border-radius: 8px;
    background: white; padding: 0 10px; color: var(--text);
}
.drawer-controls input { min-width: 260px; flex: 1; }
.drawer-body { overflow: auto; padding: 14px 18px 24px; }
.metric-strip {
    display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px;
    margin-bottom: 14px;
}
.metric-card { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }
.metric-label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.metric-value { margin-top: 4px; font-size: 18px; font-weight: 780; }
.table-section { margin-top: 18px; }
.table-section:first-of-type { margin-top: 0; }
.table-heading { display: flex; align-items: baseline; gap: 8px; margin-bottom: 7px; }
.table-heading h3 { margin: 0; font-size: 15px; }
.table-heading span { color: var(--muted); font-size: 12px; }
.table-wrap {
    max-height: 280px; overflow: auto; border: 1px solid var(--border);
    border-radius: 10px; background: white;
}
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
th, td { padding: 8px 10px; border-bottom: 1px solid #edf0f4; text-align: right; white-space: nowrap; }
th {
    position: sticky; top: 0; z-index: 2; background: #f7f9fc;
    color: #46546b; font-size: 11px; text-transform: uppercase; letter-spacing: .025em;
}
th:first-child, td:first-child { text-align: left; }
th:nth-child(2), td:nth-child(2) { text-align: left; }
tr:last-child td { border-bottom: 0; }
.tool-lung { background: rgba(229,57,53,.045); }
.tool-pan { background: rgba(21,101,192,.045); }
.diff-cell { font-weight: 740; }
.na { color: #8b95a5; }
.method-note {
    margin-top: 18px; border: 1px solid var(--border); border-radius: 10px;
    background: #fbfcfe; padding: 0 12px;
}
.method-note summary { cursor: pointer; padding: 10px 0; font-weight: 720; font-size: 13px; }
.method-note-content { padding: 0 0 11px; color: #48566d; font-size: 12px; line-height: 1.55; }
.method-note-content p { margin: 5px 0; }
.unmapped-labels { white-space: normal; text-align: left; max-width: 360px; }
.unmapped-tool { text-align: left; }
.sidebar-unmapped {
    margin-top: 14px;
    border-top: 1px solid #edf0f4;
    border-bottom: 1px solid #edf0f4;
}
.sidebar-unmapped .table-wrap { max-height: 260px; }
.sidebar-unmapped table { min-width: 560px; }
.formula { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #24324a; }
@media (max-width: 900px) {
    :root { --details-width: 330px; }
    .metric-strip { grid-template-columns: 1fr; }
    #comparisonDrawer { left: 1vw; right: 1vw; }
}
</style>
</head>
<body>
<div id="app">
<header>
    <div class="brand">
        <h1>HRApop __ORGAN_TITLE__ Population View</h1>
        <p>Estimated cell counts and shares by anatomical structure and sex</p>
    </div>
    <div class="search-wrap">
        <input id="search" type="search" placeholder="Search cell type or ontology ID" />
        <button id="searchButton" title="Search">⌕</button>
    </div>
    <div class="controls">
        <button class="control" id="fitButton" title="Fit graph">Fit</button>
        <button class="control" id="zoomOut" title="Zoom out">−</button>
        <button class="control" id="zoomIn" title="Zoom in">+</button>
        <button class="control active" id="inspectToggle" title="Enable or disable hover inspection">Inspect</button>
        <button class="control active" id="labelsToggle" title="Show or hide labels">Labels</button>
    </div>
</header>
<main>
    <section id="graphWrap">
        <div id="cy"></div>
        <div class="summary" id="summary"></div>
        <div class="legend">
            <div class="legend-title">Direct HRApop output and hierarchy tracing</div>
            <div class="legend-row"><span class="dot" style="background:var(--red)"></span>__LUNG_TOOL_DISPLAY__ only</div>
            <div class="legend-row"><span class="dot" style="background:var(--blue)"></span>__PAN_TOOL_DISPLAY__ only</div>
            <div class="legend-row"><span class="dot" style="background:var(--purple)"></span>Exact CT ID in both</div>
            <div class="legend-row"><span class="dot" style="background:var(--gray)"></span>Not directly output by either</div>
            <div class="legend-row"><span class="line-sample"></span>Primary path to root</div>
            <div class="legend-row"><span class="line-sample subtree"></span>All descendant branches</div>
        </div>
    </section>
    <aside id="details"></aside>
</main>
</div>
<div id="tooltip"></div>
<div id="toast"></div>
<div class="drawer-backdrop" id="drawerBackdrop"></div>
<section id="comparisonDrawer" aria-hidden="true">
    <div class="drawer-header">
        <div class="drawer-title-wrap">
            <h2 class="drawer-title" id="drawerTitle">Comparison tables</h2>
            <div class="drawer-subtitle" id="drawerSubtitle"></div>
        </div>
        <button class="drawer-close" id="drawerClose" aria-label="Close comparison tables">×</button>
    </div>
    <div class="tabs">
        <button class="tab active" data-tab="exact" id="exactTab">Exact cell type</button>
        <button class="tab" data-tab="subtree" id="subtreeTab">Node + descendants</button>
    </div>
    <div class="drawer-controls">
        <input id="asFilter" type="search" placeholder="Filter anatomical structures" />
        <select id="sexFilter" aria-label="Filter by sex"><option value="all">All sexes</option></select>
        <select id="sortRows" aria-label="Sort rows">
            <option value="share-diff">Largest percentage-point difference</option>
            <option value="count-diff">Largest count difference</option>
            <option value="as">Anatomical structure</option>
        </select>
    </div>
    <div class="drawer-body">
        <div class="metric-strip">
            <div class="metric-card"><div class="metric-label">AS × sex groups compared</div><div class="metric-value" id="metricGroups">—</div></div>
            <div class="metric-card"><div class="metric-label">Median absolute count difference</div><div class="metric-value" id="metricCount">—</div></div>
            <div class="metric-card"><div class="metric-label">Median absolute share difference</div><div class="metric-value" id="metricShare">—</div></div>
        </div>
        <section class="table-section">
            <div class="table-heading"><h3 id="countHeading">Estimated cell count</h3><span>by anatomical structure and sex</span></div>
            <div class="table-wrap"><table><thead><tr><th>Anatomical structure</th><th>Sex</th><th class="tool-lung">__LUNG_TOOL_DISPLAY__</th><th class="tool-pan">__PAN_TOOL_DISPLAY__</th><th>Absolute difference</th></tr></thead><tbody id="countRows"></tbody></table></div>
        </section>
        <section class="table-section">
            <div class="table-heading"><h3 id="percentageHeading">Share of annotated cells</h3><span>absolute difference shown in percentage points</span></div>
            <div class="table-wrap"><table><thead><tr><th>Anatomical structure</th><th>Sex</th><th class="tool-lung">__LUNG_TOOL_DISPLAY__</th><th class="tool-pan">__PAN_TOOL_DISPLAY__</th><th>Absolute difference</th></tr></thead><tbody id="percentageRows"></tbody></table></div>
        </section>
        <details class="method-note">
            <summary>How these values are calculated</summary>
            <div class="method-note-content">
                <p><strong>Exact percentage:</strong> <span class="formula">cell_percentage × 100</span>.</p>
                <p><strong>Subtree count:</strong> sum of the selected node and all descendants.</p>
                <p><strong>Subtree percentage:</strong> <span class="formula">subtree count ÷ total cell count</span> for the same AS, sex, and tool.</p>
                <p><strong>Absolute difference:</strong> unsigned difference; share differences are reported in percentage points (pp).</p>
                <p><strong>0</strong> means the tool has that AS × sex group but did not output the selected label. <strong>N/A</strong> means that complete tool group is unavailable.</p>
                <p>Counts are estimated HRApop AS-level populations.</p>
            </div>
        </details>
    </div>
</section>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.33.1/dist/cytoscape.min.js"></script>
<script>
(() => {
"use strict";
const payload = __PAYLOAD_JSON__;
const summary = payload.summary;
const lungTool = __LUNG_TOOL_JS__;
const panTool = __PAN_TOOL_JS__;
const rootId = "CL:0000000";
const statusText = {
    neutral: "Not directly output by either tool",
    lung_only: `${lungTool} only`,
    pan_only: `${panTool} only`,
    shared: "Exact CT ID in both tools"
};
const statusColors = {
    neutral: "#8A8F98",
    lung_only: "#E53935",
    pan_only: "#1565C0",
    shared: "#7B1FA2"
};
const graph = cytoscape({
    container: document.getElementById("cy"),
    elements: { nodes: payload.nodes, edges: payload.edges },
    layout: { name: "preset", fit: true, padding: 75 },
    minZoom: 0.05, maxZoom: 5, wheelSensitivity: 0.16,
    boxSelectionEnabled: false, autoungrabify: true,
    style: [
        { selector: "node", style: {
            "background-color": "data(fillColor)", "width": 10, "height": 10,
            "border-width": 0, "label": "data(displayLabel)", "font-size": 9,
            "color": "#172033", "text-wrap": "wrap", "text-max-width": 145,
            "text-valign": "bottom", "text-halign": "center", "text-margin-y": 7,
            "text-background-color": "#ffffff", "text-background-opacity": .82,
            "text-background-padding": 2, "z-index": 3
        }},
        { selector: "node[isCompared = true]", style: {
            "width": 19, "height": 19, "border-width": 2,
            "border-color": "#ffffff", "border-opacity": .95,
            "font-weight": 700, "z-index": 10
        }},
        { selector: `node[id = "${rootId}"]`, style: { "width": 21, "height": 21, "font-weight": 750 }},
        { selector: "edge", style: {
            "width": 1, "line-color": "#667085", "opacity": .32,
            "curve-style": "straight", "z-index": 1
        }},
        { selector: ".path-node", style: { "border-width": 4, "border-color": "#111827", "border-opacity": 1, "z-index": 30 }},
        { selector: ".path-edge", style: { "width": 4, "line-color": "#111827", "line-style": "solid", "opacity": .95, "z-index": 25 }},
        { selector: ".subtree-node", style: { "border-width": 3, "border-color": "#4B5563", "border-style": "dotted", "border-opacity": .95, "z-index": 28 }},
        { selector: ".subtree-edge", style: { "width": 4, "line-color": "#4B5563", "line-style": "dotted", "opacity": .88, "z-index": 24 }},
        { selector: ".faded", style: { "opacity": .08 }},
        { selector: "node:selected", style: { "border-width": 5, "border-color": "#111827", "border-opacity": 1 }}
    ]
});
const tooltip = document.getElementById("tooltip");
const details = document.getElementById("details");
const searchInput = document.getElementById("search");
const inspectToggle = document.getElementById("inspectToggle");
const labelsToggle = document.getElementById("labelsToggle");
const drawer = document.getElementById("comparisonDrawer");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const exactTab = document.getElementById("exactTab");
const subtreeTab = document.getElementById("subtreeTab");
const asFilter = document.getElementById("asFilter");
const sexFilter = document.getElementById("sexFilter");
const sortRows = document.getElementById("sortRows");
let inspectEnabled = true;
let labelsEnabled = true;
let pinnedNode = null;
let comparisonNode = null;
let activeTab = "exact";
function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
function pills(values) {
    if (!values || values.length === 0) return '<span class="placeholder">None</span>';
    return values.map(value => `<span class="pill">${escapeHtml(value)}</span>`).join("");
}
function toolBlock(title, meta, isDirect) {
    return `
        <div class="tool-row">
            <div><span class="tool-name">${escapeHtml(title)}</span>${isDirect && meta.labels.length ? `<div class="section-value">${pills(meta.labels)}</div>` : ""}${isDirect && meta.sexes.length ? `<div class="section-value"><strong>Sex:</strong> ${pills(meta.sexes)}</div>` : ""}</div>
            <div class="${isDirect ? "direct-yes" : "direct-no"}">${isDirect ? "Direct output" : "Not direct"}</div>
        </div>`;
}
function unmappedDisclosureHtml() {
    if (!summary.unmappedComparisonCount) return "";
    const rows = (payload.unmapped || []).map(item => {
        const labelText = item.labels && item.labels.length
            ? item.labels.join("; ")
            : "—";
        return `<tr><td>${escapeHtml(item.id)}</td><td class="unmapped-labels">${escapeHtml(labelText)}</td><td class="unmapped-tool">${escapeHtml(item.toolStatus)}</td></tr>`;
    }).join("");
    return `
        <details class="method-note sidebar-unmapped">
            <summary>Unmapped HRApop cell-type IDs (${countFormatter.format(summary.unmappedComparisonCount)})</summary>
            <div class="method-note-content">
                <p>These output IDs are not present in the supplied supertree.</p>
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Cell-type ID</th><th>HRApop label</th><th>Output by</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        </details>`;
}
function renderNodeDetails(node) {
    const data = node.data();
    const color = statusColors[data.status];
    const parentText = data.parentLabels && data.parentLabels.length
        ? data.parentLabels.map((label, index) => `${escapeHtml(label)} (${escapeHtml(data.parentIds[index])})`).join("<br>")
        : "Root";
    details.innerHTML = `
        <h2>${escapeHtml(data.label)}</h2>
        <div class="node-id">${escapeHtml(data.id)}</div>
        <div class="section"><span class="pill status-pill" style="background:${color}">${escapeHtml(statusText[data.status])}</span></div>
        <div class="section"><div class="section-title">Primary ontology path</div><div class="section-value">${escapeHtml(data.pathText)}</div></div>
        <div class="section">
            <div class="section-title">Hierarchy position</div>
            <div class="section-value"><strong>Node type:</strong> ${data.isLeaf ? "Leaf" : `Non-leaf · ${data.descendantCount} descendants`}</div>
            <div class="section-value"><strong>Depth:</strong> ${data.depth}</div>
            <div class="section-value"><strong>Immediate parent${data.parentIds && data.parentIds.length === 1 ? "" : "s"}:</strong><br>${parentText}</div>
        </div>
        <div class="section">
            <div class="section-title">Hierarchy provenance</div>
            <div class="section-value"><strong>Used anywhere in hierarchy paths from:</strong><br>${pills(data.sources)}</div>
            <div class="section-value"><strong>Listed as the terminal cell type by:</strong><br>${pills(data.terminalSources)}</div>
        </div>
        <div class="section">
            <div class="section-title">Tool outputs</div>
            ${toolBlock(lungTool, data.lungMeta, data.inLung)}
            ${toolBlock(panTool, data.panMeta, data.inPan)}
        </div>
        <div class="section">
            <div class="section-title">Directly predicted CTs in this subtree</div>
            <div class="section-value"><strong>${escapeHtml(lungTool)}:</strong> ${data.subtreeLungCount}</div>
            <div class="section-value"><strong>${escapeHtml(panTool)}:</strong> ${data.subtreePanCount}</div>
            <div class="section-value"><strong>Exact shared:</strong> ${data.subtreeSharedCount}</div>
            <div class="section-value"><strong>Tool-specific:</strong> ${data.subtreeDifferenceCount}</div>
        </div>
        <div class="section"><button class="open-comparison" id="openComparison">Open comparison tables</button></div>
        ${unmappedDisclosureHtml()}`;
    document.getElementById("openComparison").addEventListener("click", () => openComparison(node));
}
function resetDetails() {
    details.innerHTML = `<h2>Cell type details</h2><p class="placeholder">Hover over a node to emphasize its path and descendant subtree. Click a node to keep its details here and open AS × sex comparison tables.</p>${unmappedDisclosureHtml()}`;
}
function highlightContext(node) {
    graph.elements().removeClass("path-node path-edge subtree-node subtree-edge faded");
    const pathSet = new Set(node.data("pathIds"));
    const pathEdgeSet = new Set(node.data("pathEdgeIds") || []);
    const descendantNodeIds = new Set(node.successors("node").map(item => item.id()));
    const descendantEdgeIds = new Set(node.successors("edge").map(item => item.id()));
    graph.nodes().forEach(candidate => {
        if (pathSet.has(candidate.id())) candidate.addClass("path-node");
        else if (descendantNodeIds.has(candidate.id())) candidate.addClass("subtree-node");
        else candidate.addClass("faded");
    });
    graph.edges().forEach(edge => {
        if (pathEdgeSet.has(edge.id())) edge.addClass("path-edge");
        else if (descendantEdgeIds.has(edge.id())) edge.addClass("subtree-edge");
        else edge.addClass("faded");
    });
}
function clearHighlight() {
    if (pinnedNode) { highlightContext(pinnedNode); return; }
    graph.elements().removeClass("path-node path-edge subtree-node subtree-edge faded");
}
function tooltipHtml(node) {
    const data = node.data();
    return `<div class="title">${escapeHtml(data.label)}</div><div class="id">${escapeHtml(data.id)}</div><div><strong>Status:</strong> ${escapeHtml(statusText[data.status])}</div><div><strong>Subtree:</strong> ${escapeHtml(lungTool)} ${data.subtreeLungCount}, ${escapeHtml(panTool)} ${data.subtreePanCount}, shared ${data.subtreeSharedCount}</div><div class="path"><strong>Primary path:</strong> ${escapeHtml(data.pathText)}<br><strong>Descendants:</strong> ${data.descendantCount}</div>`;
}
function moveTooltip(event) {
    const padding = 14;
    let x = event.originalEvent.clientX + 16;
    let y = event.originalEvent.clientY + 16;
    tooltip.style.display = "block";
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - padding) x = event.originalEvent.clientX - rect.width - 16;
    if (y + rect.height > window.innerHeight - padding) y = event.originalEvent.clientY - rect.height - 16;
    tooltip.style.left = `${Math.max(padding, x)}px`;
    tooltip.style.top = `${Math.max(padding, y)}px`;
}
graph.on("mouseover", "node", event => {
    if (!inspectEnabled) return;
    const node = event.target;
    tooltip.innerHTML = tooltipHtml(node);
    moveTooltip(event);
    highlightContext(node);
});
graph.on("mousemove", "node", event => { if (inspectEnabled) moveTooltip(event); });
graph.on("mouseout", "node", () => { tooltip.style.display = "none"; clearHighlight(); });
graph.on("tap", "node", event => {
    pinnedNode = event.target;
    renderNodeDetails(pinnedNode);
    highlightContext(pinnedNode);
    if (drawer.classList.contains("open")) openComparison(pinnedNode, false);
});
graph.on("tap", event => {
    if (event.target === graph) {
        pinnedNode = null;
        graph.$(":selected").unselect();
        clearHighlight();
        resetDetails();
    }
});
graph.on("dbltap", "node", event => {
    const node = event.target;
    graph.animate({ center: { eles: node }, zoom: Math.min(2, Math.max(.9, graph.zoom() * 1.45)), duration: 350 });
});
function setLabels() {
    const showAll = labelsEnabled && graph.zoom() >= .62;
    graph.batch(() => graph.nodes().forEach(node => {
        const shouldShow = labelsEnabled && (showAll || node.data("isCompared") || node.selected());
        node.data("displayLabel", shouldShow ? node.data("label") : "");
    }));
}
graph.on("zoom", setLabels);
function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message; toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 1700);
}
function search() {
    const query = searchInput.value.trim().toLowerCase();
    if (!query) return;
    const matches = graph.nodes().filter(node => node.id().toLowerCase().includes(query) || String(node.data("label") || "").toLowerCase().includes(query));
    if (!matches.length) { showToast("No matching node found"); return; }
    const node = matches[0];
    node.select(); pinnedNode = node; renderNodeDetails(node); highlightContext(node);
    graph.animate({ center: { eles: node }, zoom: 1.45, duration: 400 });
    if (matches.length > 1) showToast(`Showing first of ${matches.length} matches`);
}
function median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a,b) => a-b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle-1] + sorted[middle]) / 2;
}
const countFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
function formatCount(value) { return value == null ? '<span class="na">N/A</span>' : countFormatter.format(value); }
function formatPercentage(value) { return value == null ? '<span class="na">N/A</span>' : `${(value * 100).toFixed(2)}%`; }
function formatPp(value) { return value == null ? '<span class="na">N/A</span>' : `${(value * 100).toFixed(2)} pp`; }
function setSexOptions(rows) {
    const current = sexFilter.value;
    const sexes = [...new Set(rows.map(row => row.sex))].sort((a,b) => a.localeCompare(b));
    sexFilter.innerHTML = '<option value="all">All sexes</option>' + sexes.map(sex => `<option value="${escapeHtml(sex)}">${escapeHtml(sex)}</option>`).join("");
    if (sexes.includes(current)) sexFilter.value = current;
}
function activeRows() {
    if (!comparisonNode) return [];
    const comparison = payload.comparisons[comparisonNode.id()] || { exactRows: [], subtreeRows: [] };
    return activeTab === "subtree" ? comparison.subtreeRows : comparison.exactRows;
}
function filteredSortedRows() {
    const query = asFilter.value.trim().toLowerCase();
    const sex = sexFilter.value;
    const rows = activeRows().filter(row => (!query || row.asLabel.toLowerCase().includes(query) || row.asId.toLowerCase().includes(query)) && (sex === "all" || row.sex === sex));
    const sortMode = sortRows.value;
    return rows.sort((a,b) => {
        if (sortMode === "as") return a.asLabel.localeCompare(b.asLabel) || a.sex.localeCompare(b.sex);
        const key = sortMode === "count-diff" ? "absCountDifference" : "absPercentageDifference";
        const av = a[key], bv = b[key];
        if (av == null && bv == null) return a.asLabel.localeCompare(b.asLabel);
        if (av == null) return 1;
        if (bv == null) return -1;
        return bv - av || a.asLabel.localeCompare(b.asLabel);
    });
}
function renderComparisonTables() {
    if (!comparisonNode) return;
    const data = comparisonNode.data();
    const rows = filteredSortedRows();
    const prefix = activeTab === "subtree" ? "Subtree" : "Exact label";
    document.getElementById("countHeading").textContent = `${prefix} — estimated cell count`;
    document.getElementById("percentageHeading").textContent = `${prefix} — share of annotated cells`;
    document.getElementById("countRows").innerHTML = rows.map(row => `<tr><td title="${escapeHtml(row.asId)}">${escapeHtml(row.asLabel)}</td><td>${escapeHtml(row.sex)}</td><td class="tool-lung">${formatCount(row.lungCount)}</td><td class="tool-pan">${formatCount(row.panCount)}</td><td class="diff-cell">${formatCount(row.absCountDifference)}</td></tr>`).join("") || '<tr><td colspan="5" class="placeholder">No matching rows</td></tr>';
    document.getElementById("percentageRows").innerHTML = rows.map(row => `<tr><td title="${escapeHtml(row.asId)}">${escapeHtml(row.asLabel)}</td><td>${escapeHtml(row.sex)}</td><td class="tool-lung">${formatPercentage(row.lungPercentage)}</td><td class="tool-pan">${formatPercentage(row.panPercentage)}</td><td class="diff-cell">${formatPp(row.absPercentageDifference)}</td></tr>`).join("") || '<tr><td colspan="5" class="placeholder">No matching rows</td></tr>';
    const comparable = rows.filter(row => row.lungAvailable && row.panAvailable);
    document.getElementById("metricGroups").textContent = countFormatter.format(comparable.length);
    const medianCount = median(comparable.map(row => row.absCountDifference).filter(value => value != null));
    const medianShare = median(comparable.map(row => row.absPercentageDifference).filter(value => value != null));
    document.getElementById("metricCount").innerHTML = formatCount(medianCount);
    document.getElementById("metricShare").innerHTML = formatPp(medianShare);
    document.getElementById("drawerSubtitle").textContent = activeTab === "subtree" ? `${data.id} · selected node plus ${data.descendantCount} descendants` : `${data.id} · exact ontology-linked label`;
}
function setActiveTab(tab) {
    if (!comparisonNode) return;
    if (tab === "subtree" && comparisonNode.data("isLeaf")) tab = "exact";
    activeTab = tab;
    exactTab.classList.toggle("active", tab === "exact");
    subtreeTab.classList.toggle("active", tab === "subtree");
    renderComparisonTables();
}
function openComparison(node, resetTab = true) {
    comparisonNode = node;
    const data = node.data();
    document.getElementById("drawerTitle").textContent = data.label;
    subtreeTab.hidden = data.isLeaf;
    if (resetTab || (activeTab === "subtree" && data.isLeaf)) activeTab = "exact";
    asFilter.value = "";
    setSexOptions(activeRows());
    drawer.classList.add("open");
    drawerBackdrop.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    setActiveTab(activeTab);
}
function closeComparison() {
    drawer.classList.remove("open");
    drawerBackdrop.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
}
exactTab.addEventListener("click", () => { setActiveTab("exact"); setSexOptions(activeRows()); renderComparisonTables(); });
subtreeTab.addEventListener("click", () => { setActiveTab("subtree"); setSexOptions(activeRows()); renderComparisonTables(); });
asFilter.addEventListener("input", renderComparisonTables);
sexFilter.addEventListener("change", renderComparisonTables);
sortRows.addEventListener("change", renderComparisonTables);
document.getElementById("drawerClose").addEventListener("click", closeComparison);
drawerBackdrop.addEventListener("click", closeComparison);
document.addEventListener("keydown", event => { if (event.key === "Escape") closeComparison(); });
document.getElementById("searchButton").addEventListener("click", search);
searchInput.addEventListener("keydown", event => { if (event.key === "Enter") search(); });
document.getElementById("fitButton").addEventListener("click", () => graph.fit(graph.elements(), 70));
document.getElementById("zoomIn").addEventListener("click", () => graph.zoom({ level: graph.zoom() * 1.25, renderedPosition: { x: graph.width()/2, y: graph.height()/2 }}));
document.getElementById("zoomOut").addEventListener("click", () => graph.zoom({ level: graph.zoom() / 1.25, renderedPosition: { x: graph.width()/2, y: graph.height()/2 }}));
inspectToggle.addEventListener("click", () => {
    inspectEnabled = !inspectEnabled;
    inspectToggle.classList.toggle("active", inspectEnabled);
    if (!inspectEnabled) { tooltip.style.display = "none"; clearHighlight(); }
});
labelsToggle.addEventListener("click", () => {
    labelsEnabled = !labelsEnabled;
    labelsToggle.classList.toggle("active", labelsEnabled);
    setLabels();
});
document.getElementById("summary").innerHTML = `<strong>${summary.lungCount}</strong> ${escapeHtml(lungTool)} CTs · <strong>${summary.panCount}</strong> ${escapeHtml(panTool)} CTs · <strong>${summary.sharedCount}</strong> exact shared · <strong>${summary.unmappedComparisonCount}</strong> outside supertree`;
resetDetails();
setLabels();
graph.fit(graph.elements(), 70);
})();
</script>
</body>
</html>'''


def render_html(
    payload: dict[str, Any],
    organ: str,
    lung_tool: str,
    pan_tool: str,
) -> str:
    graph_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    replacements = {
        "__PAYLOAD_JSON__": graph_json,
        "__ORGAN_TITLE__": html.escape(organ.title()),
        "__LUNG_TOOL_DISPLAY__": html.escape(display_tool_name(lung_tool)),
        "__PAN_TOOL_DISPLAY__": html.escape(display_tool_name(pan_tool)),
        "__LUNG_TOOL_JS__": json.dumps(display_tool_name(lung_tool)),
        "__PAN_TOOL_JS__": json.dumps(display_tool_name(pan_tool)),
    }

    output = HTML_TEMPLATE
    for old, new in replacements.items():
        output = output.replace(old, new)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the Task 2 Cytoscape HTML comparing HRApop v1.1 "
            "lung Azimuth and Pan-human Azimuth outputs."
        )
    )
    parser.add_argument(
        "--supertree",
        type=Path,
        default=DEFAULT_SUPERTREE,
        help="Reference supertree CSV/TSV. Default: data/ctann-v9.csv",
    )
    parser.add_argument(
        "--hrapop",
        type=Path,
        default=DEFAULT_HRAPOP,
        help=(
            "HRApop population CSV. Default: "
            "data/cell-types-in-anatomical-structurescts-per-as.csv"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Output HTML. Default: output_htmls/"
            "hrapop-v1.1-lung-azimuth-pan-human-comparison.html"
        ),
    )
    parser.add_argument("--organ", default="lung")
    parser.add_argument("--lung-tool", default="azimuth")
    parser.add_argument("--pan-tool", default="pan-human-azimuth")
    parser.add_argument("--modality", default="sc_transcriptomics")
    parser.add_argument(
        "--validation-tolerance",
        type=float,
        default=1e-9,
        help="Tolerance used for population-percentage validation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Supertree input: {args.supertree.resolve()}")
    print(f"HRApop input:   {args.hrapop.resolve()}")
    print(f"HTML output:    {args.output.resolve()}")

    if not args.supertree.exists():
        raise FileNotFoundError(f"Supertree file not found: {args.supertree}")
    if not args.hrapop.exists():
        raise FileNotFoundError(f"HRApop file not found: {args.hrapop}")

    tree = read_supertree(args.supertree)
    hra = read_hrapop(
        args.hrapop,
        organ=args.organ,
        lung_tool=args.lung_tool,
        pan_tool=args.pan_tool,
        modality=args.modality,
    )
    payload = build_graph_payload(
        tree,
        hra,
        validation_tolerance=args.validation_tolerance,
    )
    output_html = render_html(
        payload,
        organ=args.organ,
        lung_tool=args.lung_tool,
        pan_tool=args.pan_tool,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_html, encoding="utf-8")

    summary = payload["summary"]
    validation = summary["validation"]
    print(f"Saved: {args.output.resolve()}")
    print(
        "Supertree: "
        f"{summary['treeNodeCount']} nodes, "
        f"{summary['treeEdgeCount']} edges, "
        f"{summary['multiParentNodeCount']} multi-parent nodes"
    )
    print(
        f"{display_tool_name(args.lung_tool)}: {summary['lungCount']} CT IDs; "
        f"{display_tool_name(args.pan_tool)}: {summary['panCount']} CT IDs"
    )
    print(
        f"Shared: {summary['sharedCount']}; "
        f"{display_tool_name(args.lung_tool)}-only: {summary['lungOnlyCount']}; "
        f"{display_tool_name(args.pan_tool)}-only: {summary['panOnlyCount']}; "
        f"unmapped: {summary['unmappedComparisonCount']}"
    )
    print(
        "Percentage validation passed: "
        f"{validation['exactCaseCount']} exact cases and "
        f"{validation['subtreeCaseCount']} subtree cases."
    )
    print(
        "Note: the generated HTML loads Cytoscape.js from jsDelivr when opened."
    )


if __name__ == "__main__":
    main()
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

CYTOSCAPE_CDN = (
    "https://cdn.jsdelivr.net/npm/cytoscape@3.33.1/dist/cytoscape.min.js"
)

BUILD_VERSION = "1.0"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TREE = SCRIPT_DIR / "data" / "ctann-v9.csv"
DEFAULT_OUTPUT = (
    SCRIPT_DIR
    / "output_htmls"
    / "hlca-azimuth-pan-human-exact-node-comparison.html"
)

MAX_PATH_LEVEL = 12
COLUMN_DX = 292.5
ROW_DY = 8.5
LEAF_STEP = 3.0
ROOT_GAP = 2.0

COLORS = {
    "neutral": "#8A8F98",
    "azimuth_only": "#E53935",
    "pan_only": "#1565C0",
    "shared": "#7B1FA2",
}

# The builder accepts the aggregate comparison format used by the prior
# HLCA exact-node view. Header aliases are supported.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "sex": (
        "sex",
    ),
    "ann_finest_level": (
        "ann_finest_level",
        "author_label",
        "author label",
        "original_label",
        "original label",
    ),
    "clid": (
        "clid",
        "cell_ontology_id",
        "cell ontology id",
        "cell_id",
        "predicted_clid",
        "supertree_clid",
    ),
    "mapping_status": (
        "mapping_status",
        "mapping status",
        "status",
    ),
    "author_cohort_size": (
        "author_cohort_size",
        "author cohort size",
        "cohort_size",
        "cohort size",
        "total_cells_in_cohort",
        "total cells in cohort",
    ),
    "azimuth_count": (
        "azimuth_count",
        "azimuth count",
        "lung_azimuth_count",
        "lung azimuth count",
    ),
    "pan_human_count": (
        "pan_human_count",
        "pan human count",
        "pan_human_azimuth_count",
        "pan human azimuth count",
        "pan-human count",
    ),
    "both_same_cell_count": (
        "both_same_cell_count",
        "both same cell count",
        "both_count",
        "both count",
        "same_cell_count",
    ),
    "azimuth_only_count": (
        "azimuth_only_count",
        "azimuth only count",
    ),
    "pan_human_only_count": (
        "pan_human_only_count",
        "pan human only count",
        "pan-human only count",
    ),
    "union_count": (
        "union_count",
        "union count",
    ),
}

PREFERRED_COMPARISON_FILENAMES = (
    "hlca-azimuth-pan-human-comparison.csv",
    "hlca-azimuth-pan-human-comparison.tsv",
    "hlca-azimuth-pan-human-by-sex-author-label-clid.csv",
    "hlca-azimuth-pan-human-by-sex-author-label-clid.tsv",
    "hlca-exact-node-comparison.csv",
    "hlca-exact-node-comparison.tsv",
    "lung-azimuth-comparison-aggregated.csv",
    "lung-azimuth-comparison-aggregated.tsv",
)


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


def normalize_header(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().casefold()).strip()


def detect_delimiter(path: Path) -> str:
    if path.suffix.lower() in {".tsv", ".tab"}:
        return "\t"

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(65536)

    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def read_header(path: Path) -> tuple[list[str], str]:
    delimiter = detect_delimiter(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return [], delimiter
    return header, delimiter


def resolve_column_map(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized_to_actual = {
        normalize_header(name): name
        for name in fieldnames
        if name is not None
    }

    result: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            actual = normalized_to_actual.get(normalize_header(alias))
            if actual:
                result[canonical] = actual
                break
    return result


def has_comparison_header(path: Path) -> bool:
    try:
        header, _ = read_header(path)
    except (OSError, UnicodeError, csv.Error):
        return False

    columns = resolve_column_map(header)
    minimum = {
        "sex",
        "ann_finest_level",
        "clid",
        "author_cohort_size",
        "azimuth_count",
        "pan_human_count",
        "both_same_cell_count",
    }
    return minimum <= set(columns)


def discover_comparison_path(data_dir: Path) -> Path:
    for filename in PREFERRED_COMPARISON_FILENAMES:
        candidate = data_dir / filename
        if candidate.exists() and has_comparison_header(candidate):
            return candidate

    candidates: list[Path] = []
    for pattern in ("*.csv", "*.tsv", "*.tab"):
        candidates.extend(sorted(data_dir.glob(pattern)))

    matches = [
        path
        for path in candidates
        if path.name != DEFAULT_TREE.name and has_comparison_header(path)
    ]

    if not matches:
        raise FileNotFoundError(
            "Could not automatically locate the HLCA aggregate comparison "
            f"file in {data_dir}. Expected columns include sex, "
            "ann_finest_level, clid, author_cohort_size, azimuth_count, "
            "pan_human_count, and both_same_cell_count. Supply its path "
            "with --comparison."
        )

    if len(matches) > 1:
        names = "\n  - ".join(str(path) for path in matches)
        raise ValueError(
            "More than one file in the data directory matches the HLCA "
            "comparison schema. Supply one explicitly with --comparison:\n"
            f"  - {names}"
        )

    return matches[0]


def parse_nonnegative_int(
    value: str | None,
    *,
    column: str,
    row_number: int,
    allow_blank: bool = False,
) -> int:
    raw = (value or "").strip()
    if not raw:
        if allow_blank:
            return 0
        raise ValueError(
            f"Blank numeric value in column {column!r} at input row "
            f"{row_number}."
        )

    try:
        number = float(raw.replace(",", ""))
    except ValueError as error:
        raise ValueError(
            f"Invalid numeric value {raw!r} in column {column!r} at "
            f"input row {row_number}."
        ) from error

    if not number.is_integer() or number < 0:
        raise ValueError(
            f"Expected a nonnegative integer in column {column!r} at "
            f"input row {row_number}, found {raw!r}."
        )

    return int(number)


def infer_mapping_status(clid: str, supplied: str) -> tuple[str, str]:
    raw = clid.strip()
    upper = raw.upper()

    if not raw:
        return "blank_id", ""

    if upper in {"NA", "N/A", "NONE", "NULL", "MISSING"}:
        return "method_prediction_absent", "NA"

    normalized = normalize_ontology_id(raw)
    if normalized.startswith("CL:"):
        return "mapped_clid", normalized

    supplied_key = supplied.strip().casefold()
    if supplied_key in {
        "method_prediction_absent",
        "method prediction absent",
        "absent",
    }:
        return "method_prediction_absent", "NA"

    return "unmapped_non_cl_id", normalized


def read_comparison(
    path: Path,
    *,
    validate_counts: bool,
) -> dict[str, Any]:
    delimiter = detect_delimiter(path)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = reader.fieldnames or []
        column_map = resolve_column_map(fieldnames)

        required = {
            "sex",
            "ann_finest_level",
            "clid",
            "author_cohort_size",
            "azimuth_count",
            "pan_human_count",
            "both_same_cell_count",
        }
        missing = required - set(column_map)
        if missing:
            raise ValueError(
                f"Missing required comparison columns in {path}: "
                f"{sorted(missing)}. Available columns: {fieldnames}"
            )

        raw_rows = list(reader)

    grouped: dict[
        tuple[str, str, str, str],
        dict[str, Any],
    ] = {}

    cohort_sizes: dict[tuple[str, str], int] = {}
    validation_errors: list[str] = []

    for row_number, raw_row in enumerate(raw_rows, start=2):
        def get(canonical: str) -> str:
            actual = column_map.get(canonical)
            return (raw_row.get(actual) or "").strip() if actual else ""

        sex = get("sex")
        author_label = get("ann_finest_level")
        supplied_status = get("mapping_status")
        mapping_status, clid = infer_mapping_status(
            get("clid"),
            supplied_status,
        )

        cohort_size = parse_nonnegative_int(
            get("author_cohort_size"),
            column="author_cohort_size",
            row_number=row_number,
        )
        azimuth = parse_nonnegative_int(
            get("azimuth_count"),
            column="azimuth_count",
            row_number=row_number,
        )
        pan = parse_nonnegative_int(
            get("pan_human_count"),
            column="pan_human_count",
            row_number=row_number,
        )
        both = parse_nonnegative_int(
            get("both_same_cell_count"),
            column="both_same_cell_count",
            row_number=row_number,
        )

        if both > min(azimuth, pan):
            validation_errors.append(
                f"row {row_number}: both_same_cell_count={both} exceeds "
                f"min(azimuth_count={azimuth}, pan_human_count={pan})"
            )

        expected_azimuth_only = azimuth - both
        expected_pan_only = pan - both
        expected_union = azimuth + pan - both

        if "azimuth_only_count" in column_map:
            azimuth_only = parse_nonnegative_int(
                get("azimuth_only_count"),
                column="azimuth_only_count",
                row_number=row_number,
            )
        else:
            azimuth_only = expected_azimuth_only

        if "pan_human_only_count" in column_map:
            pan_only = parse_nonnegative_int(
                get("pan_human_only_count"),
                column="pan_human_only_count",
                row_number=row_number,
            )
        else:
            pan_only = expected_pan_only

        if "union_count" in column_map:
            union = parse_nonnegative_int(
                get("union_count"),
                column="union_count",
                row_number=row_number,
            )
        else:
            union = expected_union

        if validate_counts:
            if azimuth_only != expected_azimuth_only:
                validation_errors.append(
                    f"row {row_number}: azimuth_only_count={azimuth_only}, "
                    f"expected {expected_azimuth_only}"
                )
            if pan_only != expected_pan_only:
                validation_errors.append(
                    f"row {row_number}: pan_human_only_count={pan_only}, "
                    f"expected {expected_pan_only}"
                )
            if union != expected_union:
                validation_errors.append(
                    f"row {row_number}: union_count={union}, "
                    f"expected {expected_union}"
                )

        if not sex:
            sex = "(blank)"
        if not author_label:
            author_label = "(blank)"

        cohort_key = (sex, author_label)
        prior_cohort_size = cohort_sizes.get(cohort_key)
        if (
            prior_cohort_size is not None
            and prior_cohort_size != cohort_size
        ):
            validation_errors.append(
                f"row {row_number}: cohort {cohort_key!r} has "
                f"author_cohort_size={cohort_size}; previously "
                f"{prior_cohort_size}"
            )
        cohort_sizes[cohort_key] = cohort_size

        group_key = (
            sex,
            author_label,
            clid,
            mapping_status,
        )

        if group_key not in grouped:
            grouped[group_key] = {
                "sex": sex,
                "ann_finest_level": author_label,
                "clid": clid,
                "mapping_status": mapping_status,
                "author_cohort_size": cohort_size,
                "azimuth_count": 0,
                "pan_human_count": 0,
                "both_same_cell_count": 0,
                "azimuth_only_count": 0,
                "pan_human_only_count": 0,
                "union_count": 0,
            }

        item = grouped[group_key]
        item["azimuth_count"] += azimuth
        item["pan_human_count"] += pan
        item["both_same_cell_count"] += both
        item["azimuth_only_count"] += azimuth_only
        item["pan_human_only_count"] += pan_only
        item["union_count"] += union

    if validation_errors:
        preview = "\n  - ".join(validation_errors[:20])
        suffix = (
            f"\n  ... and {len(validation_errors) - 20} more"
            if len(validation_errors) > 20
            else ""
        )
        raise ValueError(
            "Comparison validation failed:\n"
            f"  - {preview}{suffix}\n"
            "Use --skip-count-validation only after confirming that the "
            "input intentionally uses different definitions."
        )

    rows = sorted(
        grouped.values(),
        key=lambda row: (
            row["sex"].casefold(),
            row["ann_finest_level"].casefold(),
            row["mapping_status"],
            row["clid"],
        ),
    )

    return {
        "rows": rows,
        "cohort_sizes": cohort_sizes,
        "input_row_count": len(raw_rows),
        "aggregated_row_count": len(rows),
    }


def read_supertree(path: Path) -> dict[str, Any]:
    delimiter = detect_delimiter(path)

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = set(reader.fieldnames or [])
        required = {"CT/1 - Sources", "AS/1/ID", "AS/1/LABEL"}
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

    for row in rows:
        source = (row.get("CT/1 - Sources") or "").strip() or "(blank)"
        path_nodes: list[tuple[str, str]] = []

        for level in range(1, MAX_PATH_LEVEL + 1):
            node_id = normalize_ontology_id(row.get(f"AS/{level}/ID"))
            node_label = (row.get(f"AS/{level}/LABEL") or "").strip()
            if node_id:
                path_nodes.append((node_id, node_label or node_id))

        if not path_nodes:
            continue

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
        raise ValueError(f"No supertree nodes were found in {path}.")

    roots = sorted(
        [
            node
            for node in all_nodes
            if not parents.get(node)
        ],
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
        for child in sorted(
            children.get(node, set()),
            key=lambda value: (
                -edge_counts[(node, value)],
                labels.get(value, ""),
                value,
            ),
        ):
            candidate = depth[node] + 1
            if child not in depth or candidate < depth[child]:
                depth[child] = candidate
                queue.append(child)

    for node in all_nodes:
        depth.setdefault(node, 0)

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
    active_stack: set[str] = set()

    def assign_y(node: str) -> None:
        nonlocal cursor
        if node in y_position:
            return
        if node in active_stack:
            raise ValueError(
                "A cycle was encountered in the primary-parent layout at "
                f"{node}."
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

    for root_index, root in enumerate(roots):
        assign_y(root)
        if root_index < len(roots) - 1:
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

    descendant_cache: dict[str, set[str]] = {}

    def descendants(node_id: str) -> set[str]:
        if node_id in descendant_cache:
            return descendant_cache[node_id]

        result: set[str] = set()
        stack = list(children.get(node_id, set()))
        while stack:
            child = stack.pop()
            if child in result:
                continue
            result.add(child)
            stack.extend(children.get(child, set()))
        descendant_cache[node_id] = result
        return result

    return {
        "labels": labels,
        "label_variants": label_variants,
        "node_sources": node_sources,
        "terminal_sources": terminal_sources,
        "parents": parents,
        "children": children,
        "edge_counts": edge_counts,
        "roots": roots,
        "depth": depth,
        "primary_parent": primary_parent,
        "y_position": y_position,
        "primary_path": primary_path,
        "descendants": descendants,
        "nodes": all_nodes,
    }


def status_from_counts(azimuth: int, pan: int) -> str:
    if azimuth > 0 and pan > 0:
        return "shared"
    if azimuth > 0:
        return "azimuth_only"
    if pan > 0:
        return "pan_only"
    return "neutral"


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cohort_sizes: dict[tuple[str, str], int] = {}
    azimuth = 0
    pan = 0
    both = 0
    azimuth_only = 0
    pan_only = 0
    union = 0

    for row in rows:
        if row["azimuth_count"] <= 0 and row["pan_human_count"] <= 0:
            continue

        cohort_key = (row["sex"], row["ann_finest_level"])
        cohort_sizes[cohort_key] = row["author_cohort_size"]
        azimuth += row["azimuth_count"]
        pan += row["pan_human_count"]
        both += row["both_same_cell_count"]
        azimuth_only += row["azimuth_only_count"]
        pan_only += row["pan_human_only_count"]
        union += row["union_count"]

    status = status_from_counts(azimuth, pan)

    return {
        "azimuth": azimuth,
        "pan": pan,
        "both": both,
        "azimuthOnly": azimuth_only,
        "panOnly": pan_only,
        "union": union,
        "cohortCount": len(cohort_sizes),
        "cohortCellCount": sum(cohort_sizes.values()),
        "status": status,
        "fillColor": COLORS[status],
    }


def group_disclosure_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["clid"]].append(row)

    return [
        {
            "clid": clid,
            "aggregate": aggregate_rows(group_rows),
            "rows": group_rows,
        }
        for clid, group_rows in sorted(
            grouped.items(),
            key=lambda item: item[0],
        )
    ]


def build_payload(
    tree: dict[str, Any],
    comparison: dict[str, Any],
    *,
    paired_dataset_count: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = comparison["rows"]
    all_nodes: set[str] = tree["nodes"]
    labels: dict[str, str] = tree["labels"]
    parents: dict[str, set[str]] = tree["parents"]
    children: dict[str, set[str]] = tree["children"]
    depth: dict[str, int] = tree["depth"]
    primary_parent: dict[str, str] = tree["primary_parent"]
    y_position: dict[str, float] = tree["y_position"]
    primary_path = tree["primary_path"]
    descendants = tree["descendants"]

    mapped_rows = [
        row
        for row in rows
        if row["mapping_status"] == "mapped_clid"
    ]
    rows_by_clid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in mapped_rows:
        rows_by_clid[row["clid"]].append(row)

    global_aggregates = {
        clid: aggregate_rows(group_rows)
        for clid, group_rows in rows_by_clid.items()
    }

    comparison_clids = {
        clid
        for clid, aggregate in global_aggregates.items()
        if aggregate["union"] > 0
    }
    comparison_tree_clids = comparison_clids & all_nodes

    nodes: list[dict[str, Any]] = []
    for node_id in sorted(
        all_nodes,
        key=lambda value: (
            depth.get(value, 999),
            labels.get(value, ""),
            value,
        ),
    ):
        aggregate = global_aggregates.get(node_id)
        status = (
            aggregate["status"]
            if aggregate and aggregate["union"] > 0
            else "neutral"
        )
        path_ids = primary_path(node_id)
        path_labels = [
            labels.get(path_id, path_id)
            for path_id in path_ids
        ]
        parent_ids = sorted(
            parents.get(node_id, set()),
            key=lambda value: (
                labels.get(value, ""),
                value,
            ),
        )
        child_ids = sorted(
            children.get(node_id, set()),
            key=lambda value: (
                labels.get(value, ""),
                value,
            ),
        )

        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": labels.get(node_id, node_id),
                    "displayLabel": labels.get(node_id, node_id),
                    "labelVariants": sorted(
                        tree["label_variants"].get(node_id, set()),
                        key=str.casefold,
                    ),
                    "isComparisonNode": node_id in comparison_tree_clids,
                    "status": status,
                    "fillColor": COLORS[status],
                    "depth": depth.get(node_id, 0),
                    "parentId": primary_parent.get(node_id, ""),
                    "parentLabel": labels.get(
                        primary_parent.get(node_id, ""),
                        "",
                    ),
                    "parentIds": parent_ids,
                    "parentLabels": [
                        labels.get(value, value)
                        for value in parent_ids
                    ],
                    "childIds": child_ids,
                    "childLabels": [
                        labels.get(value, value)
                        for value in child_ids
                    ],
                    "childCount": len(child_ids),
                    "descendantCount": len(descendants(node_id)),
                    "pathIds": path_ids,
                    "pathLabels": path_labels,
                    "pathText": " → ".join(path_labels),
                    "sources": sorted(
                        tree["node_sources"].get(node_id, set()),
                        key=str.casefold,
                    ),
                    "terminalSources": sorted(
                        tree["terminal_sources"].get(node_id, set()),
                        key=str.casefold,
                    ),
                },
                "position": {
                    "x": depth.get(node_id, 0) * COLUMN_DX,
                    "y": y_position[node_id] * ROW_DY,
                },
            }
        )

    edges: list[dict[str, Any]] = []
    for edge_index, (parent_id, child_id) in enumerate(
        sorted(
            tree["edge_counts"],
            key=lambda edge: (
                depth.get(edge[0], 999),
                labels.get(edge[0], ""),
                labels.get(edge[1], ""),
                edge[0],
                edge[1],
            ),
        )
    ):
        edges.append(
            {
                "data": {
                    "id": f"edge-{edge_index}",
                    "source": parent_id,
                    "target": child_id,
                    "isPrimary": (
                        primary_parent.get(child_id) == parent_id
                    ),
                    "sourceRowCount": tree["edge_counts"][
                        (parent_id, child_id)
                    ],
                }
            }
        )

    outside_rows = [
        row
        for row in mapped_rows
        if row["clid"] not in all_nodes
    ]
    non_cl_rows = [
        row
        for row in rows
        if row["mapping_status"] == "unmapped_non_cl_id"
    ]
    absent_rows = [
        row
        for row in rows
        if row["mapping_status"] == "method_prediction_absent"
    ]
    blank_rows = [
        row
        for row in rows
        if row["mapping_status"] == "blank_id"
    ]

    cohort_sizes: dict[tuple[str, str], int] = {}
    for row in rows:
        cohort_sizes[
            (row["sex"], row["ann_finest_level"])
        ] = row["author_cohort_size"]

    initial_status_counts = Counter(
        global_aggregates[clid]["status"]
        for clid in comparison_tree_clids
    )

    valid_clids = set(rows_by_clid)
    outside_clids = valid_clids - all_nodes
    non_cl_ids = {
        row["clid"]
        for row in non_cl_rows
        if row["clid"]
    }

    payload = {
        "nodes": nodes,
        "edges": edges,
        "comparisonRows": rows,
        "sexes": sorted(
            {row["sex"] for row in rows},
            key=str.casefold,
        ),
        "authorLabels": sorted(
            {row["ann_finest_level"] for row in rows},
            key=str.casefold,
        ),
        "outsideTree": group_disclosure_rows(outside_rows),
        "nonCl": group_disclosure_rows(non_cl_rows),
        "absentRows": absent_rows,
        "blankRows": blank_rows,
        "summary": {
            "treeNodeCount": len(all_nodes),
            "treeEdgeCount": len(edges),
            "treeRootCount": len(tree["roots"]),
            "treeMultiParentNodeCount": sum(
                1
                for node in all_nodes
                if len(parents.get(node, set())) > 1
            ),
            "inputComparisonRowCount": comparison["input_row_count"],
            "comparisonRowCount": len(rows),
            "mappedRowCount": len(mapped_rows),
            "comparisonClidCount": len(valid_clids),
            "mappedToTreeClidCount": len(valid_clids & all_nodes),
            "outsideTreeClidCount": len(outside_clids),
            "nonClIdentifierCount": len(non_cl_ids),
            "nonClCellCount": sum(
                row["union_count"]
                for row in non_cl_rows
            ),
            "absentRowCount": len(absent_rows),
            "absentCellCount": sum(
                row["union_count"]
                for row in absent_rows
            ),
            "blankRowCount": len(blank_rows),
            "cohortCount": len(cohort_sizes),
            "cohortCellCount": sum(cohort_sizes.values()),
            "pairedHlcaDatasetCount": paired_dataset_count,
            "initialStatusCounts": {
                "pan_only": initial_status_counts["pan_only"],
                "shared": initial_status_counts["shared"],
                "azimuth_only": initial_status_counts["azimuth_only"],
            },
        },
    }
    return payload


def safe_json_for_script(value: Any) -> str:
    text = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )



HTML_TEMPLATE = r'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HLCA Exact-Node View — Lung Azimuth Comparison</title>
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
    --green: #16A34A;
    --details-width: 410px;
    --toolbar-height: 82px;
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
    min-height: var(--toolbar-height);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 9px 14px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    z-index: 10;
}
.brand { min-width: 238px; }
.brand h1 { margin: 0 0 3px; font-size: 18px; line-height: 1.2; }
.brand p { margin: 0; color: var(--muted); font-size: 12px; }
.search-wrap { flex: 1; min-width: 180px; max-width: 390px; position: relative; }
#search {
    width: 100%; height: 40px; padding: 0 42px 0 13px;
    border: 1px solid var(--border); border-radius: 10px;
    outline: none; background: #fbfcfe;
}
#search:focus, .filter-select:focus {
    border-color: #8ca9fb;
    box-shadow: 0 0 0 3px rgba(21, 94, 239, 0.12);
}
#searchButton {
    position: absolute; top: 4px; right: 4px; width: 34px; height: 32px;
    border: 0; border-radius: 8px; background: transparent; cursor: pointer;
}
.filter-group { display: flex; align-items: end; gap: 8px; }
.filter-field { display: grid; gap: 3px; }
.filter-field label {
    color: var(--muted); font-size: 10px; font-weight: 760;
    text-transform: uppercase; letter-spacing: .045em;
}
.filter-select {
    height: 40px; border: 1px solid var(--border); border-radius: 9px;
    background: #fff; color: var(--text); padding: 0 28px 0 9px;
    outline: none;
}
#sexFilter { width: 112px; }
#authorFilter { width: 230px; max-width: 26vw; }
.controls { display: flex; align-items: center; gap: 6px; margin-left: auto; }
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
    color: var(--muted); margin-bottom: 12px; overflow-wrap: anywhere;
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
.exact-pill { color: #1049b8; border-color: #b8c8f5; background: #edf2ff; font-weight: 720; }
.metric-grid {
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px; margin: 8px 0 2px;
}
.side-metric { border: 1px solid var(--border); border-radius: 9px; padding: 8px 9px; }
.side-metric-label { color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.side-metric-value { margin-top: 3px; font-size: 15px; font-weight: 760; }
.side-metric-sub { color: var(--muted); font-size: 10px; line-height: 1.35; margin-top: 4px; }
.open-comparison {
    width: 100%; min-height: 42px; border: 0; border-radius: 9px;
    background: var(--accent); color: white; font-weight: 760; cursor: pointer;
    padding: 10px 14px;
}
.open-comparison:hover { background: #0d4ed1; }
.open-comparison:disabled { cursor: not-allowed; opacity: .45; }
.summary {
    position: absolute; top: 13px; left: 14px; z-index: 4; max-width: 560px;
    background: rgba(255,255,255,.96); border: 1px solid var(--border);
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
    background: rgba(255,255,255,.96);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 14px;
    box-shadow: 0 3px 14px rgba(20,30,45,.08);
    font-size: 12px;
    transition: width .18s ease, left .18s ease, right .18s ease,
        transform .18s ease, padding .18s ease;
}
.legend-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}
.legend-title {
    font-weight: 760;
    margin-bottom: 2px;
}
.legend-toggle {
    flex: none;
    min-height: 30px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: #fff;
    color: #253246;
    cursor: pointer;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 720;
}
.legend-toggle:hover { background: #f4f7fb; }
.legend-toggle:focus-visible {
    outline: 3px solid rgba(21, 94, 239, .18);
    outline-offset: 2px;
}
.legend-content {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    column-gap: 18px;
    row-gap: 4px;
    margin-top: 4px;
}
.legend.collapsed {
    left: auto;
    right: 14px;
    width: auto;
    min-width: 220px;
    transform: none;
    padding: 8px 10px;
}
.legend.collapsed .legend-content { display: none; }
.legend-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 3px 0;
    min-width: 0;
}
.legend-note {
    grid-column: 1 / -1;
}
.legend-subtitle {
    grid-column: 1 / -1;
}
.dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
.ring-key {
    position: relative; width: 28px; height: 28px; border-radius: 50%;
    border: 5px solid var(--green); flex: none;
}
.ring-key::before {
    content: ""; position: absolute; inset: 3px; border-radius: 50%;
    background: var(--purple);
}
.legend-note.legend-note { color: var(--muted); max-width: none; line-height: 1.35; margin-top: 6px; }
.legend-subtitle {
    grid-column: 1 / -1;
    font-weight: 740;
    margin-top: 5px;
    margin-bottom: 2px;
    padding-top: 7px;
    border-top: 1px solid #e7ebf1;
}
.projection-key { width: 14px; height: 14px; border-radius: 50%; flex: none; background: var(--purple); }
.projection-key.direct { opacity: 1; }
.projection-key.ancestor { opacity: .45; }
.projection-key.unrelated { opacity: .11; }
.line-key {
    width: 30px;
    height: 0;
    border-top: 3px solid #111827;
    flex: none;
}
.line-key.dotted {
    border-top-style: dotted;
    border-top-color: #657084;
}
#tooltip {
    position: fixed; z-index: 999; display: none; max-width: 410px;
    background: rgba(17,24,39,.97); color: #fff; border-radius: 9px;
    padding: 10px 11px; font-size: 12px; line-height: 1.48;
    pointer-events: none; box-shadow: 0 8px 28px rgba(0,0,0,.22);
}
#tooltip .title { font-weight: 760; font-size: 13px; }
#tooltip .id { color: #cbd5e1; font-family: ui-monospace, monospace; margin: 2px 0 7px; }
#tooltip .path { color: #dbe4f0; margin-top: 7px; }
#tooltip .scope { color: #bfdbfe; margin-bottom: 7px; }
#tooltip .interpretation { margin-top: 8px; padding-top: 7px; border-top: 1px solid rgba(255,255,255,.18); color: #dbe4f0; }
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
    position: fixed; z-index: 1001; left: 3vw; right: 3vw; bottom: 0;
    height: min(80vh, 820px); background: #fff;
    border: 1px solid var(--border); border-bottom: 0;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 -12px 38px rgba(15,23,42,.18);
    transform: translateY(105%); transition: transform .22s ease;
    display: grid; grid-template-rows: auto auto 1fr;
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
.drawer-controls {
    display: flex; align-items: center; flex-wrap: wrap; gap: 9px;
    padding: 10px 18px; border-bottom: 1px solid var(--border); background: #fbfcfe;
}
.drawer-scope { color: var(--muted); font-size: 12px; margin-left: auto; }
.drawer-body { overflow: auto; padding: 14px 18px 24px; }
.metric-strip {
    display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 10px;
    margin-bottom: 14px;
}
.metric-card { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }
.metric-label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.metric-value { margin-top: 4px; font-size: 18px; font-weight: 780; }
.metric-sub { color: var(--muted); font-size: 10px; line-height: 1.35; margin-top: 4px; }
.table-heading { display: flex; align-items: baseline; gap: 8px; margin-bottom: 7px; }
.table-heading h3 { margin: 0; font-size: 15px; }
.table-heading span { color: var(--muted); font-size: 12px; }
.table-wrap {
    max-height: 420px; overflow: auto; border: 1px solid var(--border);
    border-radius: 10px; background: white;
}
table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
th, td { padding: 8px 10px; border-bottom: 1px solid #edf0f4; text-align: right; white-space: nowrap; }
th {
    position: sticky; top: 0; z-index: 2; background: #f7f9fc;
    color: #46546b; font-size: 11px; text-transform: uppercase; letter-spacing: .025em;
}
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
tr:last-child td { border-bottom: 0; }
.tool-lung { background: rgba(229,57,53,.05); }
.tool-pan { background: rgba(21,101,192,.05); }
.method-note {
    margin-top: 18px; border: 1px solid var(--border); border-radius: 10px;
    background: #fbfcfe; padding: 0 12px;
}
.method-note summary { cursor: pointer; padding: 10px 0; font-weight: 720; font-size: 13px; }
.method-note-content { padding: 0 0 11px; color: #48566d; font-size: 12px; line-height: 1.55; }
.method-note-content p { margin: 5px 0; }
.formula { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #24324a; }
.disclosure { margin-top: 8px; border: 1px solid var(--border); border-radius: 9px; background: #fbfcfe; }
.disclosure summary { cursor: pointer; padding: 9px 10px; font-size: 12px; font-weight: 720; }
.disclosure-body { padding: 0 10px 10px; font-size: 12px; color: #48566d; line-height: 1.5; }
.disclosure-list { margin: 6px 0 0 18px; padding: 0; }
@media (max-width: 1180px) {
    :root { --details-width: 360px; }
    .brand { min-width: 190px; }
    #authorFilter { width: 185px; }
    .control { padding: 0 8px; }
}
@media (max-width: 920px) {
    header { flex-wrap: wrap; align-content: center; }
    :root { --toolbar-height: 132px; --details-width: 330px; }
    .brand { min-width: 225px; }
    .filter-group { order: 4; width: 100%; }
    #authorFilter { max-width: none; width: min(420px, 58vw); }
    .metric-strip { grid-template-columns: repeat(2, minmax(0,1fr)); }
    #comparisonDrawer { left: 1vw; right: 1vw; }
}
</style>
</head>
<body>
<div id="app">
<header>
    <div class="brand">
        <h1>HLCA Exact-Node View</h1>
        <p>Cell-level comparison across 47 paired lung partitions with author-label projection</p>
    </div>
    <div class="search-wrap">
        <input id="search" type="search" placeholder="Search cell type or ontology ID" />
        <button id="searchButton" title="Search">⌕</button>
    </div>
    <div class="filter-group" aria-label="Comparison filters">
        <div class="filter-field">
            <label for="sexFilter">Sex</label>
            <select class="filter-select" id="sexFilter">
                <option value="all">All</option>
            </select>
        </div>
        <div class="filter-field">
            <label for="authorFilter">Author label</label>
            <select class="filter-select" id="authorFilter">
                <option value="all">All</option>
            </select>
        </div>
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
        <div class="legend" id="legend">
            <div class="legend-header">
                <div class="legend-title">Node fill — current filter scope</div>
                <button
                    class="legend-toggle"
                    id="legendToggle"
                    type="button"
                    aria-expanded="true"
                    aria-controls="legendContent"
                >Minimize</button>
            </div>
            <div class="legend-content" id="legendContent">
                <div class="legend-row"><span class="dot" style="background:var(--red)"></span>Azimuth only</div>
                <div class="legend-row"><span class="dot" style="background:var(--blue)"></span>Pan-human only</div>
                <div class="legend-row"><span class="dot" style="background:var(--purple)"></span>Exact CT ID in both</div>
                <div class="legend-row"><span class="dot" style="background:var(--gray)"></span>No direct output in current scope</div>
                <div class="legend-row"><span class="ring-key"></span>Green ring — exact CLID occurs in the comparison results from 47 paired HLCA lung dataset partitions</div>
                <div class="legend-note">The ring identifies comparison membership and does not encode a count. Green-ringed nodes are enlarged; node fill changes with the Sex and Author label filters.</div>
                <div class="legend-subtitle">Author-label projection</div>
                <div class="legend-row"><span class="projection-key direct"></span>Full opacity — exact CLID destination for the selected author label</div>
                <div class="legend-row"><span class="projection-key ancestor"></span>Medium opacity — ancestor retained for hierarchy context</div>
                <div class="legend-row"><span class="projection-key unrelated"></span>Faded — unrelated to the selected author label</div>
                <div class="legend-note">Projection focus activates only when a specific Author label is selected.</div>
                <div class="legend-subtitle">Hierarchy hover</div>
                <div class="legend-row"><span class="line-key"></span>Solid — primary path from the hovered node to a root</div>
                <div class="legend-row"><span class="line-key dotted"></span>Dotted — all descendant branches below the hovered node</div>
            </div>
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
            <h2 class="drawer-title" id="drawerTitle">Exact-node comparison</h2>
            <div class="drawer-subtitle" id="drawerSubtitle"></div>
        </div>
        <button class="drawer-close" id="drawerClose" aria-label="Close comparison table">×</button>
    </div>
    <div class="drawer-controls">
        <div><strong>Exact-node counts summed across matching cohorts</strong></div>
        <div class="drawer-scope" id="drawerScope"></div>
    </div>
    <div class="drawer-body">
        <div class="metric-strip">
            <div class="metric-card"><div class="metric-label">Active cohorts</div><div class="metric-value" id="metricCohorts">—</div><div class="metric-sub">Distinct sex + author-label cohorts matching the active filters.</div></div>
            <div class="metric-card"><div class="metric-label">Total cells in active cohort</div><div class="metric-value" id="metricCohortCells">—</div><div class="metric-sub">All author-annotated cells matching the active Sex and Author label filters, counting each cohort once. This is the denominator for percentages.</div></div>
            <div class="metric-card"><div class="metric-label">Azimuth total</div><div class="metric-value" id="metricAzimuth">—</div><div class="metric-sub">Cells Azimuth assigned to this exact CLID across the active cohorts.</div></div>
            <div class="metric-card"><div class="metric-label">Pan-human total</div><div class="metric-value" id="metricPan">—</div><div class="metric-sub">Cells pan-human Azimuth assigned to this exact CLID across the active cohorts.</div></div>
            <div class="metric-card"><div class="metric-label">Both same cells</div><div class="metric-value" id="metricBoth">—</div><div class="metric-sub">The same individual cells were assigned to this exact CLID by both methods.</div></div>
            <div class="metric-card"><div class="metric-label">Azimuth only</div><div class="metric-value" id="metricAzimuthOnly">—</div><div class="metric-sub">Cells assigned here by Azimuth but not to this exact CLID by pan-human.</div></div>
            <div class="metric-card"><div class="metric-label">Pan-human only</div><div class="metric-value" id="metricPanOnly">—</div><div class="metric-sub">Cells assigned here by pan-human but not to this exact CLID by Azimuth.</div></div>
            <div class="metric-card"><div class="metric-label">Union</div><div class="metric-value" id="metricUnion">—</div><div class="metric-sub">Unique cells assigned to this exact CLID by either method; both-agreed cells are counted once.</div></div>
        </div>
        <section>
            <div class="table-heading"><h3>Exact CLID rows</h3><span>count and percentage of each author cohort</span></div>
            <div class="table-wrap">
                <table>
                    <thead><tr>
                        <th>Sex</th><th>Author label</th><th>Cohort size</th>
                        <th class="tool-lung">Azimuth</th><th class="tool-pan">Pan-human</th>
                        <th>Both same cells</th><th>Azimuth only</th><th>Pan-human only</th><th>Union</th>
                    </tr></thead>
                    <tbody id="comparisonRows"></tbody>
                </table>
            </div>
        </section>
        <details class="method-note">
            <summary>How to interpret these counts</summary>
            <div class="method-note-content">
                <p>The KPI cards sum exact-CLID rows after applying the Sex and Author label filters. Each count is paired with its percentage of all cells in the active cohort. They are exact-node values, not subtree values.</p>
                <p><strong>Total cells in active cohort:</strong> sum of <span class="formula">author_cohort_size</span> across all distinct cohorts matching the active Sex and Author label filters, counting each cohort once. It includes cells whether or not either method assigned them to this CLID and is the denominator used for all percentages.</p>
                <p><strong>Azimuth / Pan-human:</strong> cells each method assigned to this exact CLID; percentages use total cells in the active cohort as the denominator.</p>
                <p><strong>Both same cells:</strong> the same individual cells were assigned to this exact CLID by both methods; the percentage uses the same active-cohort denominator.</p>
                <p><strong>Azimuth only / Pan-human only:</strong> cells assigned here by one method but not to this exact CLID by the other method.</p>
                <p><strong>Union:</strong> unique cells assigned to this exact CLID by either method.</p>
            </div>
        </details>
    </div>
</section>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.33.1/dist/cytoscape.min.js"></script>
<script>
(() => {
"use strict";
const payload = __PAYLOAD_JSON__;
const COLORS = {
    neutral: "#8A8F98",
    azimuth_only: "#E53935",
    pan_only: "#1565C0",
    shared: "#7B1FA2"
};
const STATUS_LABELS = {
    neutral: "No direct output in current scope",
    azimuth_only: "Azimuth only",
    pan_only: "Pan-human only",
    shared: "Exact CT ID in both"
};
const state = {
    sex: "all",
    author: "all",
    inspect: true,
    labels: true,
    selectedId: null,
};

const byId = new Map(payload.nodes.map(node => [node.data.id, node]));
const allMappedRows = payload.comparisonRows.filter(row => row.mapping_status === "mapped_clid");
const rowsByClid = new Map();
for (const row of allMappedRows) {
    if (!rowsByClid.has(row.clid)) rowsByClid.set(row.clid, []);
    rowsByClid.get(row.clid).push(row);
}

let projectionFocus = {
    enabled: false,
    active: new Set(),
    ancestors: new Set(),
    pathEdges: new Set(),
    outsideTree: new Set(),
    statusCounts: { shared: 0, azimuth_only: 0, pan_only: 0 }
};

function projectionEdgeKey(source, target) {
    return `${source}\u0000${target}`;
}

function computeProjectionFocus() {
    const active = new Set();
    const ancestors = new Set();
    const pathEdges = new Set();
    const outsideTree = new Set();
    const statusCounts = { shared: 0, azimuth_only: 0, pan_only: 0 };

    if (state.author === "all") {
        return { enabled: false, active, ancestors, pathEdges, outsideTree, statusCounts };
    }

    const selectedClids = new Set(
        allMappedRows
            .filter(row => matchesFilters(row) && (row.azimuth_count > 0 || row.pan_human_count > 0))
            .map(row => row.clid)
    );

    for (const clid of selectedClids) {
        if (!byId.has(clid)) {
            outsideTree.add(clid);
            continue;
        }
        active.add(clid);
    }

    for (const clid of active) {
        const base = byId.get(clid);
        const pathIds = base?.data?.pathIds || [];
        for (const pathId of pathIds) ancestors.add(pathId);
        for (let index = 1; index < pathIds.length; index++) {
            pathEdges.add(projectionEdgeKey(pathIds[index - 1], pathIds[index]));
        }
        const status = aggregateClid(clid).status;
        if (statusCounts[status] !== undefined) statusCounts[status] += 1;
    }

    for (const clid of active) ancestors.delete(clid);

    return { enabled: true, active, ancestors, pathEdges, outsideTree, statusCounts };
}

function projectionRole(clid) {
    if (!projectionFocus.enabled) return "none";
    if (projectionFocus.active.has(clid)) return "destination";
    if (projectionFocus.ancestors.has(clid)) return "ancestor";
    return "unrelated";
}

function projectionScopeSentence() {
    if (state.author === "all") return "";
    if (state.sex === "all") {
        return `Counts sum the female and male source cohorts for “${state.author}” where available.`;
    }
    return `Counts use only the ${state.sex.toLowerCase()} source cohort for “${state.author}”.`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
function fmtInt(value) { return Number(value || 0).toLocaleString("en-US"); }
function fmtPct(value, denominator) {
    const numerator = Number(value || 0);
    const total = Number(denominator || 0);
    if (!total) return "0.00%";
    return `${(numerator / total * 100).toFixed(2)}%`;
}
function fmtCountPct(value, denominator) {
    return `${fmtInt(value)} (${fmtPct(value, denominator)})`;
}
function scopeText() {
    const sex = state.sex === "all" ? "All sexes" : state.sex;
    const author = state.author === "all" ? "All author labels" : state.author;
    return `${sex} · ${author}`;
}
function matchesFilters(row) {
    return (state.sex === "all" || row.sex === state.sex)
        && (state.author === "all" || row.ann_finest_level === state.author);
}
function filteredRowsForClid(clid) {
    return (rowsByClid.get(clid) || []).filter(matchesFilters);
}
function aggregate(rows) {
    const cohortSizes = new Map();
    let azimuth = 0, pan = 0, both = 0, azimuthOnly = 0, panOnly = 0, union = 0;
    for (const row of rows) {
        if (row.azimuth_count <= 0 && row.pan_human_count <= 0) continue;
        const cohortKey = `${row.sex}\u0000${row.ann_finest_level}`;
        const previousSize = cohortSizes.get(cohortKey);
        if (previousSize !== undefined && previousSize !== row.author_cohort_size) {
            throw new Error(`Inconsistent author cohort size for ${cohortKey}`);
        }
        cohortSizes.set(cohortKey, row.author_cohort_size);
        azimuth += row.azimuth_count;
        pan += row.pan_human_count;
        both += row.both_same_cell_count;
        azimuthOnly += row.azimuth_only_count;
        panOnly += row.pan_human_only_count;
        union += row.union_count;
    }
    let status = "neutral";
    if (azimuth > 0 && pan > 0) status = "shared";
    else if (azimuth > 0) status = "azimuth_only";
    else if (pan > 0) status = "pan_only";
    const activeScope = selectedScopeSummary();
    return {
        cohortCount: cohortSizes.size,
        cohortCellCount: [...cohortSizes.values()].reduce((sum, value) => sum + value, 0),
        activeCohortCount: activeScope.cohortCount,
        activeCohortCellCount: activeScope.cohortCells,
        azimuth, pan, both, azimuthOnly, panOnly, union,
        azimuthPct: activeScope.cohortCells ? azimuth / activeScope.cohortCells * 100 : 0,
        panPct: activeScope.cohortCells ? pan / activeScope.cohortCells * 100 : 0,
        bothPct: activeScope.cohortCells ? both / activeScope.cohortCells * 100 : 0,
        azimuthOnlyPct: activeScope.cohortCells ? azimuthOnly / activeScope.cohortCells * 100 : 0,
        panOnlyPct: activeScope.cohortCells ? panOnly / activeScope.cohortCells * 100 : 0,
        unionPct: activeScope.cohortCells ? union / activeScope.cohortCells * 100 : 0,
        status, fillColor: COLORS[status]
    };
}
function aggregateClid(clid) { return aggregate(filteredRowsForClid(clid)); }
function selectedScopeSummary() {
    const rows = payload.comparisonRows.filter(matchesFilters);
    const cohorts = new Map();
    for (const row of rows) {
        cohorts.set(`${row.sex}\u0000${row.ann_finest_level}`, row.author_cohort_size);
    }
    const mappedClids = new Set(
        rows.filter(row => row.mapping_status === "mapped_clid"
            && (row.azimuth_count > 0 || row.pan_human_count > 0))
            .map(row => row.clid)
    );
    return {
        cohortCount: cohorts.size,
        cohortCells: [...cohorts.values()].reduce((a, b) => a + b, 0),
        mappedClids: mappedClids.size
    };
}

const elements = [];
for (const node of payload.nodes) {
    if (node.data.isComparisonNode) {
        elements.push({
            data: { id: `comparison-ring::${node.data.id}`, logicalId: node.data.id },
            position: node.position,
            classes: "comparisonRing"
        });
    }
    elements.push({ ...node, classes: node.data.isComparisonNode ? "core comparisonCore" : "core normalCore" });
}
elements.push(...payload.edges);

const cy = cytoscape({
    container: document.getElementById("cy"),
    elements,
    layout: { name: "preset", fit: true, padding: 50 },
    minZoom: 0.025,
    maxZoom: 5,
    wheelSensitivity: 0.16,
    selectionType: "single",
    style: [
        {
            selector: "node.core",
            style: {
                "background-color": "data(fillColor)",
                "label": "data(displayLabel)",
                "font-size": 9,
                "color": "#111827",
                "text-valign": "bottom",
                "text-halign": "center",
                "text-margin-y": 5,
                "text-wrap": "wrap",
                "text-max-width": 150,
                "overlay-opacity": 0,
                "z-index-compare": "manual",
                "z-index": 30
            }
        },
        { selector: "node.normalCore", style: { "width": 14, "height": 14 } },
        { selector: "node.comparisonCore", style: { "width": 28, "height": 28 } },
        {
            selector: "node.comparisonRing",
            style: {
                "width": 40, "height": 40,
                "background-color": "#16A34A",
                "border-width": 0,
                "events": "no",
                "overlay-opacity": 0,
                "z-index-compare": "manual",
                "z-index": 10
            }
        },
        {
            selector: "edge",
            style: {
                "width": 1.05,
                "line-color": "#8A94A3",
                "opacity": 0.48,
                "curve-style": "straight",
                "overlay-opacity": 0,
                "z-index-compare": "manual",
                "z-index": 1
            }
        },
        {
            selector: ".projectionDestination",
            style: { "opacity": 1, "text-opacity": 1 }
        },
        {
            selector: ".projectionAncestor",
            style: { "opacity": 0.45, "text-opacity": 0.55 }
        },
        {
            selector: ".projectionMuted",
            style: { "opacity": 0.10, "text-opacity": 0.10 }
        },
        {
            selector: "edge.projectionEdge",
            style: { "line-color": "#6B7280", "width": 1.35, "opacity": 0.42 }
        },
        {
            selector: "edge.projectionMutedEdge",
            style: { "opacity": 0.045 }
        },
        {
            selector: "node.core:selected",
            style: {
                "border-width": 3,
                "border-color": "#111827",
                "border-opacity": 0.85,
                "opacity": 1,
                "text-opacity": 1
            }
        },
        {
            selector: ".pathNode",
            style: { "border-width": 3, "border-color": "#F59E0B", "border-opacity": 1, "opacity": 1, "text-opacity": 1 }
        },
        {
            selector: ".pathEdge",
            style: { "line-color": "#F59E0B", "width": 3.2, "opacity": 0.95 }
        },
        {
            selector: ".hoverRootNode",
            style: {
                "border-width": 3,
                "border-color": "#111827",
                "border-opacity": 1,
                "opacity": 1,
                "text-opacity": 1
            }
        },
        {
            selector: ".hoverSubtreeNode",
            style: {
                "border-width": 2,
                "border-style": "dotted",
                "border-color": "#657084",
                "border-opacity": 0.9,
                "opacity": 1,
                "text-opacity": 1
            }
        },
        {
            selector: "edge.hoverRootEdge",
            style: {
                "line-style": "solid",
                "line-color": "#111827",
                "width": 3.2,
                "opacity": 1,
                "z-index": 45
            }
        },
        {
            selector: "edge.hoverSubtreeEdge",
            style: {
                "line-style": "dotted",
                "line-color": "#657084",
                "width": 3.2,
                "opacity": 0.95,
                "z-index": 40
            }
        },
        {
            selector: ".searchMatch",
            style: { "border-width": 4, "border-color": "#0EA5E9", "border-opacity": 1, "opacity": 1, "text-opacity": 1 }
        }
    ]
});

const details = document.getElementById("details");
const tooltip = document.getElementById("tooltip");
const summary = document.getElementById("summary");
const toast = document.getElementById("toast");
const sexFilter = document.getElementById("sexFilter");
const authorFilter = document.getElementById("authorFilter");
const drawer = document.getElementById("comparisonDrawer");
const drawerBackdrop = document.getElementById("drawerBackdrop");

function populateFilters() {
    for (const sex of payload.sexes) {
        const option = document.createElement("option");
        option.value = sex; option.textContent = sex; sexFilter.appendChild(option);
    }
    for (const label of payload.authorLabels) {
        const option = document.createElement("option");
        option.value = label; option.textContent = label; authorFilter.appendChild(option);
    }
}

function updateNodeVisuals() {
    projectionFocus = computeProjectionFocus();

    cy.batch(() => {
        cy.nodes().removeClass("projectionDestination projectionAncestor projectionMuted");
        cy.edges().removeClass("projectionEdge projectionMutedEdge");

        for (const [clid] of rowsByClid) {
            const core = cy.getElementById(clid);
            if (!core || core.empty()) continue;
            const metrics = aggregateClid(clid);
            core.data("status", metrics.status);
            core.data("fillColor", metrics.fillColor);
            core.style("background-color", metrics.fillColor);
        }

        if (projectionFocus.enabled) {
            for (const node of cy.nodes(".core")) {
                const role = projectionRole(node.id());
                const className = role === "destination"
                    ? "projectionDestination"
                    : role === "ancestor"
                        ? "projectionAncestor"
                        : "projectionMuted";
                node.addClass(className);

                const ring = cy.getElementById(`comparison-ring::${node.id()}`);
                if (ring && !ring.empty()) ring.addClass(className);
            }

            for (const edge of cy.edges()) {
                const key = projectionEdgeKey(edge.source().id(), edge.target().id());
                edge.addClass(projectionFocus.pathEdges.has(key) ? "projectionEdge" : "projectionMutedEdge");
            }
        }
    });

    updateSummary();
    if (state.selectedId) renderDetails(state.selectedId);
    if (drawer.classList.contains("open") && state.selectedId) renderDrawer(state.selectedId);
}

function updateSummary() {
    const selected = selectedScopeSummary();
    if (!projectionFocus.enabled) {
        summary.innerHTML = `<strong>${escapeHtml(scopeText())}</strong> · `
            + `${fmtInt(selected.cohortCount)} cohort${selected.cohortCount === 1 ? "" : "s"} · `
            + `${fmtInt(selected.mappedClids)} mapped CLIDs with direct assignments`;
        return;
    }

    const status = projectionFocus.statusCounts;
    const sexText = state.sex === "all" ? "All sexes" : state.sex;
    const outsideText = projectionFocus.outsideTree.size
        ? ` · ${fmtInt(projectionFocus.outsideTree.size)} additional CLID${projectionFocus.outsideTree.size === 1 ? "" : "s"} outside the tree`
        : "";
    summary.innerHTML = `<strong>Projected author label: ${escapeHtml(state.author)}</strong><br>`
        + `${escapeHtml(sexText)} · ${fmtInt(selected.cohortCount)} source cohort${selected.cohortCount === 1 ? "" : "s"} · `
        + `${fmtInt(projectionFocus.active.size)} exact CLID destination${projectionFocus.active.size === 1 ? "" : "s"} on the tree`
        + outsideText
        + `<br>${fmtInt(status.shared)} both · ${fmtInt(status.azimuth_only)} Azimuth only · ${fmtInt(status.pan_only)} pan-human only`;
}

function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 1700);
}

function clearPath() {
    cy.elements().removeClass("pathNode pathEdge searchMatch");
}
function highlightPath(node) {
    clearPath();
    const ids = node.data("pathIds") || [];
    for (const id of ids) cy.getElementById(id).addClass("pathNode");
    for (let i = 1; i < ids.length; i++) {
        cy.edges(`[source = "${ids[i - 1]}"][target = "${ids[i]}"]`).addClass("pathEdge");
    }
}
function clearHoverTrace() {
    cy.elements().removeClass(
        "hoverRootNode hoverSubtreeNode hoverRootEdge hoverSubtreeEdge"
    );
}
function applyHoverTrace(node) {
    clearHoverTrace();

    const rootPathIds = node.data("pathIds") || [];
    for (const id of rootPathIds) {
        cy.getElementById(id).addClass("hoverRootNode");
    }
    for (let index = 1; index < rootPathIds.length; index++) {
        cy.edges(
            `[source = "${rootPathIds[index - 1]}"][target = "${rootPathIds[index]}"]`
        ).addClass("hoverRootEdge");
    }

    const queue = [node.id()];
    const visited = new Set([node.id()]);

    while (queue.length) {
        const sourceId = queue.shift();
        const sourceData = byId.get(sourceId)?.data;
        for (const childId of sourceData?.childIds || []) {
            cy.edges(
                `[source = "${sourceId}"][target = "${childId}"]`
            ).addClass("hoverSubtreeEdge");

            if (!visited.has(childId)) {
                visited.add(childId);
                queue.push(childId);
            }
        }
    }

    visited.delete(node.id());
    for (const descendantId of visited) {
        cy.getElementById(descendantId).addClass("hoverSubtreeNode");
    }
}

function disclosureHtml() {
    const outsideItems = payload.outsideTree.map(item =>
        `<li><span class="formula">${escapeHtml(item.clid)}</span> — ${fmtInt(item.aggregate.union)} union assignments across ${fmtInt(item.aggregate.cohortCount)} cohorts</li>`
    ).join("") || "<li>None</li>";
    const nonClItems = payload.nonCl.map(item =>
        `<li><span class="formula">${escapeHtml(item.clid)}</span> — ${fmtInt(item.aggregate.union)} assignments across ${fmtInt(item.aggregate.cohortCount)} cohorts</li>`
    ).join("") || "<li>None</li>";
    return `
        <details class="disclosure">
            <summary>Outside-supertree mapped CLIDs (${fmtInt(payload.summary.outsideTreeClidCount)})</summary>
            <div class="disclosure-body"><ul class="disclosure-list">${outsideItems}</ul></div>
        </details>
        <details class="disclosure">
            <summary>Non-CL identifiers (${fmtInt(payload.summary.nonClCellCount)} cells)</summary>
            <div class="disclosure-body"><ul class="disclosure-list">${nonClItems}</ul></div>
        </details>
        <details class="disclosure">
            <summary>Absent method records represented as NA (${fmtInt(payload.summary.absentCellCount)} cells)</summary>
            <div class="disclosure-body">These cells are retained in the validation accounting but do not create ontology nodes. The NA category is displayed only as a completeness disclosure.</div>
        </details>`;
}

function renderPlaceholder() {
    details.innerHTML = `
        <h2>Exact-node comparison</h2>
        <div class="node-id">Select a Cell Ontology node</div>
        <div class="placeholder">A green ring marks an exact CLID that occurs in the comparison results from 47 paired HLCA lung dataset partitions. The ring only indicates comparison membership; it does not encode magnitude. Green-ringed nodes are enlarged. Node fill shows which method assigns that exact CLID in the current filter scope. Selecting a specific Author label projects that source cohort across its exact CLID destinations: destination nodes remain fully visible, their ancestors remain as hierarchy context, and unrelated nodes fade. Hover or click for exact-node counts.</div>
        <div class="section">
            <div class="section-title">Validated input</div>
            <div class="section-value">
                ${fmtInt(payload.summary.comparisonRowCount)} aggregate rows ·
                ${fmtInt(payload.summary.cohortCount)} author cohorts ·
                ${fmtInt(payload.summary.comparisonClidCount)} valid CLIDs
            </div>
        </div>
        <div class="section">
            <div class="section-title">Comparison nodes on tree</div>
            <div class="section-value">
                ${fmtInt(payload.summary.mappedToTreeClidCount)} comparison CLIDs are shown on the tree;
                ${fmtInt(payload.summary.outsideTreeClidCount)} valid CLIDs are outside this hierarchy.
            </div>
        </div>
        ${disclosureHtml()}`;
}

function metricCard(label, value, sub = "") {
    return `<div class="side-metric"><div class="side-metric-label">${escapeHtml(label)}</div><div class="side-metric-value">${escapeHtml(value)}</div>${sub ? `<div class="side-metric-sub">${escapeHtml(sub)}</div>` : ""}</div>`;
}

function renderDetails(clid) {
    const base = byId.get(clid);
    if (!base) return;
    state.selectedId = clid;
    const metrics = aggregateClid(clid);
    const statusLabel = STATUS_LABELS[metrics.status];
    const statusColor = COLORS[metrics.status];
    const comparisonNode = Boolean(base.data.isComparisonNode);
    const role = projectionRole(clid);
    const projectionSection = projectionFocus.enabled ? `
        <div class="section">
            <div class="section-title">Author-label projection</div>
            ${role === "destination" ? `
                <div class="section-value"><strong>Source:</strong> ${escapeHtml(state.author)} → <strong>Destination:</strong> ${escapeHtml(base.data.label)}</div>
                <div class="section-value" style="margin-top:6px">The selected author cohort is the source population. This exact Cell Ontology node is one destination predicted for cells from that cohort. ${escapeHtml(projectionScopeSentence())} Descendants are not included.</div>` : role === "ancestor" ? `
                <div class="section-value"><strong>Hierarchy context</strong></div>
                <div class="section-value" style="margin-top:6px">This node is shown at medium opacity because it connects the root to one or more exact CLID destinations for the selected author label. It is not itself a direct destination in the current scope.</div>` : `
                <div class="section-value"><strong>No direct projection here</strong></div>
                <div class="section-value" style="margin-top:6px">No cells from the selected author-label scope were assigned to this exact CLID by either method. The node remains visible only to preserve the full supertree context.</div>`}
        </div>` : "";
    details.innerHTML = `
        <h2>${escapeHtml(base.data.label)}</h2>
        <div class="node-id">${escapeHtml(clid)}</div>
        <span class="pill exact-pill">Exact node only</span>
        <span class="pill status-pill" style="background:${statusColor}">${escapeHtml(statusLabel)}</span>
        <div class="section">
            <div class="section-title">Current filter scope</div>
            <div class="section-value">${escapeHtml(scopeText())}</div>
        </div>
        ${projectionSection}
        <div class="section">
            <div class="section-title">${projectionFocus.enabled ? "Projected exact-node totals" : "Exact-node totals across cohorts"}</div>
            ${comparisonNode ? `
                <div class="metric-grid">
                    ${metricCard("Active cohorts", fmtInt(metrics.activeCohortCount), "Distinct sex + author-label cohorts matching the current filters.")}
                    ${metricCard("Total cells in active cohort", fmtInt(metrics.activeCohortCellCount), "All author-annotated cells matching the active filters, counted once per cohort; denominator for every percentage.")}
                    ${metricCard("Azimuth", fmtCountPct(metrics.azimuth, metrics.activeCohortCellCount), "Exact-node assignments and their share of the active cohort.")}
                    ${metricCard("Pan-human", fmtCountPct(metrics.pan, metrics.activeCohortCellCount), "Exact-node assignments and their share of the active cohort.")}
                    ${metricCard("Both same cells", fmtCountPct(metrics.both, metrics.activeCohortCellCount), "Same individual cells assigned here by both methods.")}
                    ${metricCard("Azimuth only", fmtCountPct(metrics.azimuthOnly, metrics.activeCohortCellCount), "Assigned here by Azimuth but not by pan-human.")}
                    ${metricCard("Pan-human only", fmtCountPct(metrics.panOnly, metrics.activeCohortCellCount), "Assigned here by pan-human but not by Azimuth.")}
                    ${metricCard("Union", fmtCountPct(metrics.union, metrics.activeCohortCellCount), "Unique cells assigned here by either method; shared cells count once.")}
                </div>
                <div class="section-value" style="margin-top:8px">${projectionFocus.enabled ? `These counts show how cells originally labeled <strong>“${escapeHtml(state.author)}”</strong> by the dataset authors were assigned to this exact Cell Ontology term. ${escapeHtml(projectionScopeSentence())}` : `Counts are summed across matching <span class="formula">sex + author label</span> cohorts in the current filters.`} Values refer to this exact CLID only, not descendants. “Total cells in active cohort” is the denominator used for all percentages shown here.</div>` : `<div class="section-value">This CLID is not present in the comparison CSV.</div>`}
        </div>
        <div class="section">
            <div class="section-title">Hierarchy</div>
            <div class="section-value"><strong>Parents:</strong> ${escapeHtml((base.data.parentLabels || []).length ? base.data.parentLabels.join(", ") : "Root")}</div>
            <div class="section-value"><strong>Primary layout parent:</strong> ${escapeHtml(base.data.parentLabel || "Root")}</div>
            <div class="section-value"><strong>Children:</strong> ${fmtInt(base.data.childCount)}</div>
            <div class="section-value"><strong>Descendants:</strong> ${fmtInt(base.data.descendantCount)}</div>
        </div>
        <div class="section">
            <div class="section-title">Root-to-node path</div>
            <div class="section-value">${escapeHtml(base.data.pathText)}</div>
        </div>
        ${comparisonNode ? `<button class="open-comparison" id="openComparison" ${metrics.cohortCount ? "" : "disabled"}>Open exact-node cohort table</button>` : ""}
        ${disclosureHtml()}`;
    const button = document.getElementById("openComparison");
    if (button) button.addEventListener("click", () => openDrawer(clid));
}

function tooltipHtml(clid) {
    const base = byId.get(clid);
    const metrics = aggregateClid(clid);
    const comparisonNode = Boolean(base.data.isComparisonNode);
    const role = projectionRole(clid);
    let body = `<div class="title">${escapeHtml(base.data.label)}</div><div class="id">${escapeHtml(clid)}</div><div class="scope">${escapeHtml(scopeText())}</div>`;

    if (projectionFocus.enabled && role === "ancestor") {
        body += `<div><strong>Hierarchy context</strong></div>`
            + `<div>This node is kept at medium opacity because it lies on a root-to-destination path for the selected author label <strong>“${escapeHtml(state.author)}”</strong>. No cells from that source cohort were assigned directly to this exact CLID in the current scope.</div>`;
    } else if (projectionFocus.enabled && role === "unrelated") {
        body += `<div><strong>No direct projection here</strong></div>`
            + `<div>No cells originally labeled <strong>“${escapeHtml(state.author)}”</strong> were assigned to this exact CLID by either method under the current Sex filter. The node is faded to preserve focus while keeping the whole hierarchy visible.</div>`;
        if (comparisonNode) {
            body += `<div class="interpretation">The green ring is global: this CLID occurs somewhere in the full comparison of 47 paired HLCA lung dataset partitions, even though it is unrelated to the current author-label projection.</div>`;
        }
    } else if (comparisonNode && metrics.cohortCount) {
        body += `<div><strong>${escapeHtml(STATUS_LABELS[metrics.status])}</strong></div>`
            + `<div>Active cohorts: ${fmtInt(metrics.activeCohortCount)}</div>`
            + `<div>Total cells in active cohort: ${fmtInt(metrics.activeCohortCellCount)}</div>`
            + `<div>Azimuth: ${fmtCountPct(metrics.azimuth, metrics.activeCohortCellCount)}</div>`
            + `<div>Pan-human: ${fmtCountPct(metrics.pan, metrics.activeCohortCellCount)}</div>`
            + `<div>Both same cells: ${fmtCountPct(metrics.both, metrics.activeCohortCellCount)}</div>`
            + `<div>Azimuth only: ${fmtCountPct(metrics.azimuthOnly, metrics.activeCohortCellCount)}</div>`
            + `<div>Pan-human only: ${fmtCountPct(metrics.panOnly, metrics.activeCohortCellCount)}</div>`
            + `<div>Union: ${fmtCountPct(metrics.union, metrics.activeCohortCellCount)}</div>`;

        if (projectionFocus.enabled) {
            body += `<div class="interpretation"><strong>How to read this projection:</strong> these counts show how cells originally labeled <strong>“${escapeHtml(state.author)}”</strong> by the dataset authors were assigned to this exact Cell Ontology term. ${escapeHtml(projectionScopeSentence())} Azimuth and pan-human are exact-node assignments; “Both same cells” are the same individual cells assigned here by both methods, and “Union” counts unique cells assigned here by either method. Descendants are not included.</div>`;
        } else {
            body += `<div class="interpretation"><strong>How to read:</strong> a cohort is one sex + author-label group in which either method assigned at least one cell to this exact CLID. “Total cells in active cohort” counts every author-annotated cell matching the active filters once per cohort and is the denominator for the displayed percentages. Azimuth and pan-human totals are exact-CLID assignments. “Both same cells” are the same individual cells assigned here by both methods, while “Union” counts unique cells assigned here by either method.</div>`;
        }
    } else if (comparisonNode) {
        body += `<div>The green ring means this CLID is represented somewhere in the 47-partition comparison, but no exact-node rows match the current filters.</div>`;
    } else {
        body += `<div>Not present in the comparison CSV.</div>`;
    }
    body += `<div class="path">${escapeHtml(base.data.pathText)}</div>`;
    return body;
}

function positionTooltip(event) {
    const pad = 14;
    let x = event.originalEvent.clientX + 14;
    let y = event.originalEvent.clientY + 14;
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width + pad > window.innerWidth) x = event.originalEvent.clientX - rect.width - 14;
    if (y + rect.height + pad > window.innerHeight) y = event.originalEvent.clientY - rect.height - 14;
    tooltip.style.left = `${Math.max(pad, x)}px`;
    tooltip.style.top = `${Math.max(pad, y)}px`;
}

function openDrawer(clid) {
    state.selectedId = clid;
    renderDrawer(clid);
    drawer.classList.add("open");
    drawerBackdrop.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
}
function closeDrawer() {
    drawer.classList.remove("open");
    drawerBackdrop.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
}
function renderDrawer(clid) {
    const base = byId.get(clid);
    const rows = filteredRowsForClid(clid).sort((a, b) =>
        a.ann_finest_level.localeCompare(b.ann_finest_level) || a.sex.localeCompare(b.sex)
    );
    const metrics = aggregate(rows);
    document.getElementById("drawerTitle").textContent = base.data.label;
    document.getElementById("drawerSubtitle").textContent = projectionFocus.enabled
        ? `${clid} · ${state.author} → ${base.data.label} · Exact node only`
        : `${clid} · Exact node only`;
    document.getElementById("drawerScope").textContent = scopeText();
    document.getElementById("metricCohorts").textContent = fmtInt(metrics.activeCohortCount);
    document.getElementById("metricCohortCells").textContent = fmtInt(metrics.activeCohortCellCount);
    document.getElementById("metricAzimuth").textContent = fmtCountPct(metrics.azimuth, metrics.activeCohortCellCount);
    document.getElementById("metricPan").textContent = fmtCountPct(metrics.pan, metrics.activeCohortCellCount);
    document.getElementById("metricBoth").textContent = fmtCountPct(metrics.both, metrics.activeCohortCellCount);
    document.getElementById("metricAzimuthOnly").textContent = fmtCountPct(metrics.azimuthOnly, metrics.activeCohortCellCount);
    document.getElementById("metricPanOnly").textContent = fmtCountPct(metrics.panOnly, metrics.activeCohortCellCount);
    document.getElementById("metricUnion").textContent = fmtCountPct(metrics.union, metrics.activeCohortCellCount);
    document.getElementById("comparisonRows").innerHTML = rows.length ? rows.map(row => `
        <tr>
            <td>${escapeHtml(row.sex)}</td>
            <td>${escapeHtml(row.ann_finest_level)}</td>
            <td>${fmtInt(row.author_cohort_size)}</td>
            <td class="tool-lung">${fmtCountPct(row.azimuth_count, row.author_cohort_size)}</td>
            <td class="tool-pan">${fmtCountPct(row.pan_human_count, row.author_cohort_size)}</td>
            <td>${fmtCountPct(row.both_same_cell_count, row.author_cohort_size)}</td>
            <td>${fmtCountPct(row.azimuth_only_count, row.author_cohort_size)}</td>
            <td>${fmtCountPct(row.pan_human_only_count, row.author_cohort_size)}</td>
            <td>${fmtCountPct(row.union_count, row.author_cohort_size)}</td>
        </tr>`).join("") : `<tr><td colspan="9" style="text-align:left;color:#647084">No rows match the current filters.</td></tr>`;
}

cy.on("mouseover", "node.core", event => {
    if (!state.inspect) return;
    applyHoverTrace(event.target);
    tooltip.innerHTML = tooltipHtml(event.target.id());
    tooltip.style.display = "block";
    positionTooltip(event);
});
cy.on("mousemove", "node.core", event => {
    if (state.inspect && tooltip.style.display === "block") positionTooltip(event);
});
cy.on("mouseout", "node.core", () => {
    tooltip.style.display = "none";
    clearHoverTrace();
});
cy.on("tap", "node.core", event => {
    const node = event.target;
    state.selectedId = node.id();
    highlightPath(node);
    renderDetails(node.id());
});
cy.on("tap", event => {
    if (event.target === cy) {
        clearPath();
        state.selectedId = null;
        renderPlaceholder();
    }
});

function runSearch() {
    const query = document.getElementById("search").value.trim().toLowerCase();
    cy.elements().removeClass("searchMatch");
    if (!query) return;
    const matches = cy.nodes(".core").filter(node =>
        node.id().toLowerCase().includes(query)
        || String(node.data("label") || "").toLowerCase().includes(query)
    );
    if (!matches.length) { showToast("No matching cell type or ontology ID"); return; }
    matches.addClass("searchMatch");
    cy.animate({ fit: { eles: matches, padding: 100 }, duration: 320 });
    if (matches.length === 1) {
        const node = matches[0]; node.select(); highlightPath(node); renderDetails(node.id()); state.selectedId = node.id();
    } else showToast(`${matches.length} matching nodes`);
}

document.getElementById("searchButton").addEventListener("click", runSearch);
document.getElementById("search").addEventListener("keydown", event => { if (event.key === "Enter") runSearch(); });
document.getElementById("fitButton").addEventListener("click", () => cy.animate({ fit: { eles: cy.elements(), padding: 45 }, duration: 300 }));
document.getElementById("zoomIn").addEventListener("click", () => cy.zoom({ level: cy.zoom() * 1.22, renderedPosition: { x: cy.width()/2, y: cy.height()/2 } }));
document.getElementById("zoomOut").addEventListener("click", () => cy.zoom({ level: cy.zoom() / 1.22, renderedPosition: { x: cy.width()/2, y: cy.height()/2 } }));
document.getElementById("inspectToggle").addEventListener("click", event => {
    state.inspect = !state.inspect; event.currentTarget.classList.toggle("active", state.inspect);
    if (!state.inspect) {
        tooltip.style.display = "none";
        clearHoverTrace();
    }
});
document.getElementById("labelsToggle").addEventListener("click", event => {
    state.labels = !state.labels; event.currentTarget.classList.toggle("active", state.labels);
    cy.style().selector("node.core").style("label", state.labels ? "data(displayLabel)" : "").update();
});
sexFilter.addEventListener("change", () => { state.sex = sexFilter.value; updateNodeVisuals(); });
authorFilter.addEventListener("change", () => { state.author = authorFilter.value; updateNodeVisuals(); });
document.getElementById("drawerClose").addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);
const legend = document.getElementById("legend");
const legendToggle = document.getElementById("legendToggle");
legendToggle.addEventListener("click", () => {
    const collapsed = legend.classList.toggle("collapsed");
    legendToggle.textContent = collapsed ? "Expand" : "Minimize";
    legendToggle.setAttribute("aria-expanded", String(!collapsed));
    legendToggle.setAttribute(
        "aria-label",
        collapsed ? "Expand legend" : "Minimize legend"
    );
});
document.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
populateFilters();
renderPlaceholder();
updateNodeVisuals();
window.setTimeout(() => cy.fit(cy.elements(), 45), 60);
})();
</script>
</body>
</html>

'''



def render_html(payload: dict[str, Any]) -> str:
    payload_json = safe_json_for_script(payload)
    return HTML_TEMPLATE.replace("__PAYLOAD_JSON__", payload_json)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the HLCA exact-node organ-specific Azimuth versus "
            "pan-human Azimuth comparison on the CTann v9 supertree."
        )
    )
    parser.add_argument(
        "--tree",
        type=Path,
        default=DEFAULT_TREE,
        help="Supertree CSV/TSV. Default: data/ctann-v9.csv",
    )
    parser.add_argument(
        "--comparison",
        type=Path,
        default=None,
        help=(
            "Aggregate HLCA comparison CSV/TSV. When omitted, the script "
            "searches the data directory for a file with the required "
            "comparison columns."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Output HTML. Default: output_htmls/"
            "hlca-azimuth-pan-human-exact-node-comparison.html"
        ),
    )
    parser.add_argument(
        "--paired-dataset-count",
        type=int,
        default=47,
        help="Number of paired HLCA dataset partitions described in the UI.",
    )
    parser.add_argument(
        "--skip-count-validation",
        action="store_true",
        help=(
            "Skip formula checks for method-only and union columns. "
            "Cohort-size consistency is still checked."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tree_path = args.tree.expanduser().resolve()
    if not tree_path.exists():
        raise FileNotFoundError(
            f"Supertree input not found: {tree_path}"
        )

    comparison_path = (
        args.comparison.expanduser().resolve()
        if args.comparison is not None
        else discover_comparison_path(tree_path.parent).resolve()
    )
    if not comparison_path.exists():
        raise FileNotFoundError(
            f"HLCA comparison input not found: {comparison_path}"
        )

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Builder version: {BUILD_VERSION}")
    print(f"Supertree input: {tree_path}")
    print(f"HLCA comparison input: {comparison_path}")
    print(f"Output HTML: {output_path}")

    tree = read_supertree(tree_path)
    comparison = read_comparison(
        comparison_path,
        validate_counts=not args.skip_count_validation,
    )
    payload = build_payload(
        tree,
        comparison,
        paired_dataset_count=args.paired_dataset_count,
    )

    output_path.write_text(
        render_html(payload),
        encoding="utf-8",
    )

    summary = payload["summary"]
    print(
        "Built "
        f"{summary['treeNodeCount']:,} nodes and "
        f"{summary['treeEdgeCount']:,} edges."
    )
    print(
        "Comparison: "
        f"{summary['comparisonRowCount']:,} aggregate rows, "
        f"{summary['cohortCount']:,} sex × author-label cohorts, "
        f"{summary['mappedToTreeClidCount']:,} CLIDs on the tree, "
        f"{summary['outsideTreeClidCount']:,} CLIDs outside the tree."
    )
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import html
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

CYTOSCAPE_CDN = (
    "https://cdn.jsdelivr.net/npm/cytoscape@3.33.1/dist/cytoscape.min.js"
)

BUILD_VERSION = "3.0"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "data" / "ctann-v9.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "output_htmls" / "reference-supertree-v9.html"

MAX_PATH_LEVEL = 12
COLUMN_DX = 292.5
ROW_DY = 8.5
LEAF_STEP = 3.0
ROOT_GAP = 2.0

COLORS = {
    "neutral": "#7A7B78",
    "martin": "#1E90FF",
    "chenchen": "#E31A1C",
    "search": "#00A651",
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

    # Preserve identifiers that are not standard OBO CURIEs.
    return raw


def detect_delimiter(path: Path) -> str:
    """Detect comma- versus tab-delimited input."""
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

        required = {"CT/1 - Sources", "AS/1/ID", "AS/1/LABEL"}
        missing = required - fieldnames
        if missing:
            raise ValueError(
                f"Missing required columns in {path}: {sorted(missing)}"
            )

        rows = list(reader)

    # Every node appearing anywhere along a source path.
    node_sources: dict[str, set[str]] = defaultdict(set)
    node_source_displays: dict[str, set[str]] = defaultdict(set)

    # Only the final, most-specific node in each row's path.
    terminal_sources: dict[str, set[str]] = defaultdict(set)
    terminal_source_displays: dict[str, set[str]] = defaultdict(set)

    labels: dict[str, str] = {}
    label_variants: dict[str, set[str]] = defaultdict(set)

    parents: dict[str, set[str]] = defaultdict(set)
    children: dict[str, set[str]] = defaultdict(set)
    edge_counts: Counter[tuple[str, str]] = Counter()
    source_counts: Counter[str] = Counter()

    valid_row_count = 0
    empty_path_row_count = 0

    for row in rows:
        source_raw = (row.get("CT/1 - Sources") or "").strip()
        source_display = source_raw or "(blank)"
        source_norm = source_display.casefold()
        source_counts[source_display] += 1

        path_nodes: list[tuple[str, str]] = []

        for level in range(1, MAX_PATH_LEVEL + 1):
            node_id = normalize_ontology_id(row.get(f"AS/{level}/ID"))
            node_label = (row.get(f"AS/{level}/LABEL") or "").strip()

            if node_id:
                path_nodes.append((node_id, node_label or node_id))

        if not path_nodes:
            empty_path_row_count += 1
            continue

        valid_row_count += 1

        terminal_id = path_nodes[-1][0]
        terminal_sources[terminal_id].add(source_norm)
        terminal_source_displays[terminal_id].add(source_display)

        previous: str | None = None

        for node_id, node_label in path_nodes:
            # This mirrors the original script: later rows may update the
            # preferred display label for the same ontology ID.
            labels[node_id] = node_label
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

    # Any disconnected nodes are retained, as in the original fallback.
    for node in all_nodes:
        depth.setdefault(node, 0)

    # Choose one primary parent solely for stable layout. All original
    # parent-child edges remain visible in the final Cytoscape graph.
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

    # Keep the same recursive leaf-order layout used by the Matplotlib script.
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

    nodes: list[dict[str, Any]] = []

    martin_only_count = 0
    chenchen_only_count = 0
    shared_terminal_count = 0

    for node_id in sorted(
        all_nodes,
        key=lambda value: (
            depth.get(value, 999),
            labels.get(value, ""),
            value,
        ),
    ):
        node_terminal_sources = terminal_sources.get(node_id, set())
        is_martin_terminal = "martin" in node_terminal_sources
        is_chenchen_terminal = "chenchen" in node_terminal_sources

        if is_martin_terminal and is_chenchen_terminal:
            terminal_status = "shared"
            classes = "shared-terminal"
            shared_terminal_count += 1
        elif is_martin_terminal:
            terminal_status = "martin"
            classes = "martin-terminal"
            martin_only_count += 1
        elif is_chenchen_terminal:
            terminal_status = "chenchen"
            classes = "chenchen-terminal"
            chenchen_only_count += 1
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

        nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": labels.get(node_id, node_id),
                    "labelVariants": sorted(
                        label_variants.get(node_id, set()),
                        key=str.casefold,
                    ),
                    "depth": depth.get(node_id, 0),
                    "parentIds": parent_ids,
                    "parentLabels": [
                        labels.get(value, value) for value in parent_ids
                    ],
                    "childIds": child_ids,
                    "childLabels": [
                        labels.get(value, value) for value in child_ids
                    ],
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
                        node_source_displays.get(node_id, set()),
                        key=str.casefold,
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
        )

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

    summary = {
        "inputFile": path.name,
        "rowCount": len(rows),
        "validPathRowCount": valid_row_count,
        "emptyPathRowCount": empty_path_row_count,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
        "rootCount": len(roots),
        "multiParentNodeCount": sum(
            1 for node in all_nodes if len(parents.get(node, set())) > 1
        ),
        "martinTerminalCount": martin_only_count,
        "chenchenTerminalCount": chenchen_only_count,
        "sharedTerminalCount": shared_terminal_count,
        "otherNodeCount": (
            len(nodes)
            - martin_only_count
            - chenchen_only_count
            - shared_terminal_count
        ),
        "sourceCounts": [
            {"source": source, "rowCount": count}
            for source, count in sorted(
                source_counts.items(), key=lambda item: item[0].casefold()
            )
        ],
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": summary,
    }


def cytoscape_script_tag(local_js: Path | None) -> str:
    if local_js is None:
        return f'<script src="{CYTOSCAPE_CDN}"></script>'

    if not local_js.exists():
        raise FileNotFoundError(f"Cytoscape.js file not found: {local_js}")

    code = local_js.read_text(encoding="utf-8")
    return f"<script>\n{code}\n</script>"


def render_html(
    payload: dict[str, Any],
    title: str,
    local_cytoscape_js: Path | None,
) -> str:
    graph_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    template = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__</title>
__CYTOSCAPE_SCRIPT__
<style>
:root {
    --bg: #eef2f7;
    --panel: #ffffff;
    --border: #d8dee8;
    --text: #18212f;
    --muted: #657287;
    --blue: __MARTIN_COLOR__;
    --red: __CHENCHEN_COLOR__;
    --gray: __NEUTRAL_COLOR__;
    --green: __SEARCH_COLOR__;
    --details-width: 390px;
    --toolbar-height: 76px;
}

* { box-sizing: border-box; }

html,
body {
    width: 100%;
    height: 100%;
    margin: 0;
    overflow: hidden;
}

body {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--text);
    background: var(--bg);
}

button,
input { font: inherit; }

#app {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-rows: var(--toolbar-height) 1fr;
}

header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    z-index: 10;
}

.brand { min-width: 330px; }
.brand h1 {
    margin: 0 0 3px;
    font-size: 18px;
    line-height: 1.2;
}
.brand p {
    margin: 0;
    color: var(--muted);
    font-size: 12px;
}

.search-wrap {
    position: relative;
    flex: 1;
    max-width: 540px;
}

#searchInput {
    width: 100%;
    height: 40px;
    padding: 0 44px 0 13px;
    border: 1px solid var(--border);
    border-radius: 10px;
    outline: none;
    background: #fbfcfe;
}

#searchInput:focus {
    border-color: #8ca9fb;
    box-shadow: 0 0 0 3px rgba(21, 94, 239, 0.12);
}

#searchButton {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 34px;
    height: 32px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    cursor: pointer;
}

.controls {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-left: auto;
}

.control {
    height: 38px;
    padding: 0 11px;
    border: 1px solid var(--border);
    border-radius: 9px;
    background: #fff;
    color: #253246;
    cursor: pointer;
}
.control:hover { background: #f4f7fb; }
.control.active {
    color: #1049b8;
    border-color: #a6baf2;
    background: #edf2ff;
}

main {
    min-height: 0;
    display: grid;
    grid-template-columns: 1fr var(--details-width);
}

#graphWrap {
    position: relative;
    min-width: 0;
    overflow: hidden;
    background:
        radial-gradient(circle at 35% 20%, #ffffff 0, #f7f9fc 42%, #eef2f7 100%);
}

#cy {
    position: absolute;
    inset: 0;
}

#legend {
    position: absolute;

    /* Center the legend along the bottom of the graph canvas */
    left: 50%;
    bottom: 14px;
    top: auto;
    transform: translateX(-50%);

    /* Use 90% of the Cytoscape canvas width */
    width: 90%;
    padding: 10px 14px;

    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    column-gap: 18px;
    row-gap: 3px;

    border: 1px solid rgba(204, 212, 224, 0.95);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.94);
    box-shadow: 0 8px 30px rgba(49, 67, 92, 0.10);
    backdrop-filter: blur(7px);
    z-index: 6;
}

.legend-title {
    grid-column: 1 / -1;
    margin-bottom: 4px;
    font-size: 13px;
    font-weight: 700;
}

.legend-row {
    display: flex;
    align-items: center;
    gap: 9px;
    margin: 3px 0;
    color: #364258;
    font-size: 12px;
    line-height: 1.25;
}

.legend-note {
    grid-column: 1 / -1;
    margin-top: 5px;
    padding-top: 7px;
    border-top: 1px solid #e3e7ee;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.35;
}

.dot {
    flex: 0 0 auto;
    width: 14px;
    height: 14px;
    border-radius: 50%;
}
.dot.gray { background: var(--gray); }
.dot.blue { background: var(--blue); }
.dot.red { background: var(--red); }
.dot.shared {
    background: linear-gradient(90deg, var(--blue) 0 50%, var(--red) 50% 100%);
}

.line-sample {
    width: 26px;
    height: 0;
    border-top: 2px solid #4a4a4a;
}
.line-sample.secondary {
    border-top-style: dashed;
    opacity: 0.35;
}
.line-sample.hover-root {
    border-top-width: 3px;
    border-top-color: #111827;
}
.line-sample.hover-subtree {
    border-top-width: 3px;
    border-top-style: dotted;
    border-top-color: #657084;
}

.legend-note {
    margin-top: 9px;
    padding-top: 8px;
    border-top: 1px solid #e3e7ee;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.35;
}

#statusBadge {
    position: absolute;
    left: 14px;
    top: 14px;
    bottom: auto;
    max-width: 520px;
    padding: 8px 10px;
    border: 1px solid rgba(204, 212, 224, 0.95);
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.94);
    color: #445168;
    font-size: 12px;
    z-index: 6;
}

#tooltip {
    position: fixed;
    display: none;
    max-width: 360px;
    padding: 9px 11px;
    border: 1px solid #cfd6e2;
    border-radius: 9px;
    background: rgba(20, 28, 40, 0.96);
    color: #fff;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.22);
    font-size: 12px;
    line-height: 1.35;
    pointer-events: none;
    z-index: 30;
}
.tooltip-title { font-weight: 700; margin-bottom: 3px; }
.tooltip-muted { color: #c7d0dc; }

aside {
    min-width: 0;
    overflow-y: auto;
    padding: 16px;
    background: var(--panel);
    border-left: 1px solid var(--border);
}

aside h2 {
    margin: 0 0 4px;
    font-size: 17px;
}

.aside-subtitle {
    margin: 0 0 14px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.4;
}

.card {
    margin-bottom: 12px;
    padding: 12px;
    border: 1px solid var(--border);
    border-radius: 11px;
    background: #fff;
}

.card-title {
    margin: 0 0 9px;
    color: #4f5b70;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.045em;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
}

.kpi {
    padding: 9px;
    border-radius: 9px;
    background: #f4f7fb;
}
.kpi-value {
    font-size: 19px;
    font-weight: 750;
}
.kpi-label {
    margin-top: 2px;
    color: var(--muted);
    font-size: 11px;
}

.detail-grid {
    display: grid;
    grid-template-columns: 112px minmax(0, 1fr);
    gap: 7px 9px;
    font-size: 12px;
}
.detail-key { color: var(--muted); }
.detail-value {
    overflow-wrap: anywhere;
    color: #263247;
}

.path-box,
.list-box {
    margin-top: 8px;
    padding: 8px 9px;
    border-radius: 8px;
    background: #f6f8fb;
    color: #334057;
    font-size: 11px;
    line-height: 1.45;
    overflow-wrap: anywhere;
}

.source-list {
    margin: 0;
    padding-left: 18px;
    color: #334057;
    font-size: 12px;
}
.source-list li { margin: 4px 0; }

.empty-state {
    padding: 18px 12px;
    border: 1px dashed #ccd4e0;
    border-radius: 10px;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
    text-align: center;
}
</style>
</head>
<body>
<div id="app">
    <header>
        <div class="brand">
            <h1>__TITLE__</h1>
            <p>Interactive Cytoscape rendering of the CTann v9 reference supertree</p>
        </div>

        <div class="search-wrap">
            <input
                id="searchInput"
                type="search"
                placeholder="Search by cell type label, ontology ID, or source"
                autocomplete="off"
            />
            <button id="searchButton" title="Search">⌕</button>
        </div>

        <div class="controls">
            <button id="fitButton" class="control">Fit graph</button>
            <button id="labelsButton" class="control active">Labels</button>
            <button id="clearButton" class="control">Clear</button>
            <button id="pngButton" class="control">Export PNG</button>
        </div>
    </header>

    <main>
        <section id="graphWrap">
            <div id="cy"></div>

            <div id="legend">
                <div class="legend-title">Reference supertree legend</div>
                <div class="legend-row">
                    <span class="dot gray"></span>
                    <span>All other hierarchy nodes</span>
                </div>
                <div class="legend-row">
                    <span class="dot blue"></span>
                    <span>Martin terminal node</span>
                </div>
                <div class="legend-row">
                    <span class="dot red"></span>
                    <span>Chenchen terminal node</span>
                </div>
                <div class="legend-row">
                    <span class="dot shared"></span>
                    <span>Terminal node in both sources</span>
                </div>
                <div class="legend-row">
                    <span class="line-sample"></span>
                    <span>Primary layout edge</span>
                </div>
                <div class="legend-row">
                    <span class="line-sample secondary"></span>
                    <span>Additional parent edge</span>
                </div>
                <div class="legend-row">
                    <span class="line-sample hover-root"></span>
                    <span>Hover: primary path to root</span>
                </div>
                <div class="legend-row">
                    <span class="line-sample hover-subtree"></span>
                    <span>Hover: all descendant branches</span>
                </div>
                <div class="legend-note">
                    Hover over a node to trace its primary root path with solid lines and every reachable descendant branch with dotted lines. “Terminal” means the final, most-specific ontology node in at least one source row.
                </div>
            </div>

            <div id="statusBadge"></div>
        </section>

        <aside>
            <h2>Reference supertree</h2>
            <p class="aside-subtitle">
                Click a node for ontology, hierarchy, and source details. Hover to trace its root path and descendant subtrees.
            </p>

            <div id="summaryPanel"></div>
            <div id="detailsPanel" class="empty-state">
                Select a node to inspect its details.
            </div>
        </aside>
    </main>
</div>

<div id="tooltip"></div>

<script>
const GRAPH = __GRAPH_JSON__;
const summary = GRAPH.summary;

const cy = cytoscape({
    container: document.getElementById("cy"),
    elements: [...GRAPH.nodes, ...GRAPH.edges],
    layout: {
        name: "preset",
        fit: true,
        padding: 72
    },
    minZoom: 0.03,
    maxZoom: 5,
    wheelSensitivity: 0.18,
    pixelRatio: "auto",
    style: [
        {
            selector: "node",
            style: {
                "width": 14,
                "height": 14,
                "background-color": "__NEUTRAL_COLOR__",
                "border-width": 0,
                "label": "data(label)",
                "font-size": 10,
                "font-family": "Inter, system-ui, sans-serif",
                "color": "#111111",
                "text-valign": "bottom",
                "text-halign": "center",
                "text-margin-y": 4,
                "text-wrap": "wrap",
                "text-max-width": 200,
                "min-zoomed-font-size": 4,
                "z-index": 3
            }
        },
        {
            selector: "node.martin-terminal",
            style: {
                "background-color": "__MARTIN_COLOR__"
            }
        },
        {
            selector: "node.chenchen-terminal",
            style: {
                "background-color": "__CHENCHEN_COLOR__"
            }
        },
        {
            selector: "node.shared-terminal",
            style: {
                "background-color": "#ffffff",
                "pie-size": "100%",
                "pie-1-background-color": "__MARTIN_COLOR__",
                "pie-1-background-size": "50%",
                "pie-2-background-color": "__CHENCHEN_COLOR__",
                "pie-2-background-size": "50%"
            }
        },
        {
            selector: "edge",
            style: {
                "curve-style": "straight",
                "line-color": "#4a4a4a",
                "width": 0.8,
                "opacity": 0.22,
                "z-index": 1
            }
        },
        {
            selector: "edge.primary-edge",
            style: {
                "width": 1.0,
                "opacity": 0.56
            }
        },
        {
            selector: "edge.secondary-edge",
            style: {
                "line-style": "dashed",
                "opacity": 0.22
            }
        },
        {
            selector: ".dimmed",
            style: {
                "opacity": 0.07,
                "text-opacity": 0.03
            }
        },
        {
            selector: "node.search-hit",
            style: {
                "width": 22,
                "height": 22,
                "border-width": 4,
                "border-color": "__SEARCH_COLOR__",
                "border-opacity": 1,
                "z-index": 20,
                "font-size": 12,
                "font-weight": 700,
                "text-background-color": "#ffffff",
                "text-background-opacity": 0.9,
                "text-background-padding": 3,
                "text-background-shape": "roundrectangle"
            }
        },
        {
            selector: "node:selected",
            style: {
                "width": 22,
                "height": 22,
                "border-width": 4,
                "border-color": "#155eef",
                "border-opacity": 1,
                "z-index": 25,
                "font-size": 12,
                "font-weight": 700,
                "text-background-color": "#ffffff",
                "text-background-opacity": 0.92,
                "text-background-padding": 3,
                "text-background-shape": "roundrectangle"
            }
        },
        {
            selector: "edge.hover-subtree-edge",
            style: {
                "line-style": "dotted",
                "line-color": "#657084",
                "width": 3.2,
                "opacity": 0.9,
                "z-index": 35
            }
        },
        {
            selector: "edge.hover-root-path-edge",
            style: {
                "line-style": "solid",
                "line-color": "#111827",
                "width": 3.2,
                "opacity": 1,
                "z-index": 40
            }
        },
        {
            selector: "node.hover-subtree-node",
            style: {
                "border-width": 2,
                "border-style": "dotted",
                "border-color": "#657084",
                "border-opacity": 0.95,
                "z-index": 34
            }
        },
        {
            selector: "node.hover-root-path-node",
            style: {
                "width": 18,
                "height": 18,
                "border-width": 3,
                "border-style": "solid",
                "border-color": "#111827",
                "border-opacity": 1,
                "z-index": 41
            }
        },
        {
            selector: "node.hover-focus-node",
            style: {
                "width": 26,
                "height": 26,
                "border-width": 5,
                "border-style": "solid",
                "border-color": "#111827",
                "border-opacity": 1,
                "font-size": 10,
                "font-weight": 700,
                "text-background-color": "#ffffff",
                "text-background-opacity": 0.94,
                "text-background-padding": 3,
                "text-background-shape": "roundrectangle",
                "z-index": 50
            }
        }
    ]
});

const summaryPanel = document.getElementById("summaryPanel");
const detailsPanel = document.getElementById("detailsPanel");
const statusBadge = document.getElementById("statusBadge");
const tooltip = document.getElementById("tooltip");
const searchInput = document.getElementById("searchInput");

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function statusLabel(status) {
    if (status === "martin") return "Martin terminal node";
    if (status === "chenchen") return "Chenchen terminal node";
    if (status === "shared") return "Martin + Chenchen terminal node";
    return "Other hierarchy node";
}

function listText(values, limit = 12) {
    const clean = Array.isArray(values) ? values : [];
    if (!clean.length) return "None";
    if (clean.length <= limit) return clean.join(", ");
    return `${clean.slice(0, limit).join(", ")} … (+${clean.length - limit} more)`;
}

function renderSummary() {
    const sourceRows = summary.sourceCounts
        .map(item => `<li>${escapeHtml(item.source)}: ${formatNumber(item.rowCount)} rows</li>`)
        .join("");

    summaryPanel.innerHTML = `
        <div class="card">
            <div class="card-title">Graph summary</div>
            <div class="kpi-grid">
                <div class="kpi">
                    <div class="kpi-value">${formatNumber(summary.nodeCount)}</div>
                    <div class="kpi-label">Nodes</div>
                </div>
                <div class="kpi">
                    <div class="kpi-value">${formatNumber(summary.edgeCount)}</div>
                    <div class="kpi-label">Edges</div>
                </div>
                <div class="kpi">
                    <div class="kpi-value">${formatNumber(summary.rootCount)}</div>
                    <div class="kpi-label">Roots</div>
                </div>
                <div class="kpi">
                    <div class="kpi-value">${formatNumber(summary.multiParentNodeCount)}</div>
                    <div class="kpi-label">Multi-parent nodes</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Terminal-source nodes</div>
            <div class="detail-grid">
                <div class="detail-key">Martin only</div>
                <div class="detail-value">${formatNumber(summary.martinTerminalCount)}</div>
                <div class="detail-key">Chenchen only</div>
                <div class="detail-value">${formatNumber(summary.chenchenTerminalCount)}</div>
                <div class="detail-key">Both sources</div>
                <div class="detail-value">${formatNumber(summary.sharedTerminalCount)}</div>
                <div class="detail-key">All other nodes</div>
                <div class="detail-value">${formatNumber(summary.otherNodeCount)}</div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Included CT/1 sources</div>
            <ul class="source-list">${sourceRows}</ul>
        </div>
    `;

    statusBadge.textContent =
        `${summary.inputFile} • ${formatNumber(summary.rowCount)} rows • ` +
        `${formatNumber(summary.nodeCount)} nodes • ${formatNumber(summary.edgeCount)} edges`;
}

function renderNodeDetails(node) {
    const data = node.data();

    detailsPanel.className = "";
    detailsPanel.innerHTML = `
        <div class="card">
            <div class="card-title">Selected node</div>
            <div class="detail-grid">
                <div class="detail-key">Label</div>
                <div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
                <div class="detail-key">Ontology ID</div>
                <div class="detail-value">${escapeHtml(data.id)}</div>
                <div class="detail-key">Status</div>
                <div class="detail-value">${escapeHtml(statusLabel(data.terminalStatus))}</div>
                <div class="detail-key">Depth</div>
                <div class="detail-value">${formatNumber(data.depth)}</div>
                <div class="detail-key">Parents</div>
                <div class="detail-value">${formatNumber(data.parentCount)}</div>
                <div class="detail-key">Children</div>
                <div class="detail-value">${formatNumber(data.childCount)}</div>
            </div>

            <div class="path-box">
                <strong>Primary layout path</strong><br />
                ${escapeHtml(data.primaryPathText || data.label)}
            </div>
        </div>

        <div class="card">
            <div class="card-title">Hierarchy relationships</div>
            <div class="detail-key">Parent nodes</div>
            <div class="list-box">${escapeHtml(listText(data.parentLabels))}</div>
            <div class="detail-key" style="margin-top:9px;">Child nodes</div>
            <div class="list-box">${escapeHtml(listText(data.childLabels))}</div>
        </div>

        <div class="card">
            <div class="card-title">Source provenance</div>
            <div class="detail-key">Appears anywhere in paths from</div>
            <div class="list-box">${escapeHtml(listText(data.sources))}</div>
            <div class="detail-key" style="margin-top:9px;">Is terminal in rows from</div>
            <div class="list-box">${escapeHtml(listText(data.terminalSources))}</div>
        </div>

        <div class="card">
            <div class="card-title">Label variants</div>
            <div class="list-box">${escapeHtml(listText(data.labelVariants))}</div>
        </div>
    `;
}

function clearSearch() {
    cy.elements().removeClass("dimmed search-hit");
    searchInput.value = "";
    cy.$(":selected").unselect();
    statusBadge.textContent =
        `${summary.inputFile} • ${formatNumber(summary.rowCount)} rows • ` +
        `${formatNumber(summary.nodeCount)} nodes • ${formatNumber(summary.edgeCount)} edges`;
}

function runSearch() {
    const query = searchInput.value.trim().toLocaleLowerCase();
    cy.elements().removeClass("dimmed search-hit");

    if (!query) {
        clearSearch();
        cy.fit(cy.elements(), 72);
        return;
    }

    const matches = cy.nodes().filter(node => {
        const data = node.data();
        const haystack = [
            data.id,
            data.label,
            ...(data.labelVariants || []),
            ...(data.sources || []),
            ...(data.terminalSources || [])
        ].join(" ").toLocaleLowerCase();
        return haystack.includes(query);
    });

    if (!matches.length) {
        statusBadge.textContent = `No nodes matched “${searchInput.value.trim()}”.`;
        return;
    }

    const context = matches
        .union(matches.predecessors())
        .union(matches.connectedEdges())
        .union(matches.predecessors().connectedEdges());

    cy.elements().addClass("dimmed");
    context.removeClass("dimmed");
    matches.removeClass("dimmed").addClass("search-hit");
    cy.fit(context, 90);

    statusBadge.textContent =
        `${formatNumber(matches.length)} matching node${matches.length === 1 ? "" : "s"} ` +
        `for “${searchInput.value.trim()}”.`;
}

cy.on("tap", "node", event => {
    renderNodeDetails(event.target);
});

cy.on("tap", event => {
    if (event.target === cy) {
        cy.$(":selected").unselect();
        detailsPanel.className = "empty-state";
        detailsPanel.textContent = "Select a node to inspect its details.";
    }
});

const HOVER_CLASSES = [
    "hover-root-path-node",
    "hover-root-path-edge",
    "hover-subtree-node",
    "hover-subtree-edge",
    "hover-focus-node"
];

function clearHoverTrace() {
    for (const className of HOVER_CLASSES) {
        cy.elements(`.${className}`).removeClass(className);
    }
}

function tracePrimaryRootPath(node) {
    const pathIds = node.data("primaryPathIds") || [];

    for (const nodeId of pathIds) {
        const pathNode = cy.getElementById(nodeId);
        if (pathNode.nonempty()) {
            pathNode.addClass("hover-root-path-node");
        }
    }

    for (let index = 0; index < pathIds.length - 1; index += 1) {
        const sourceId = pathIds[index];
        const targetId = pathIds[index + 1];

        cy.edges().filter(edge => (
            edge.data("source") === sourceId &&
            edge.data("target") === targetId
        )).addClass("hover-root-path-edge");
    }
}

function traceDescendantSubtrees(node) {
    // successors() follows every directed outgoing edge, so this includes
    // all primary and additional-parent descendant branches below the node.
    const successors = node.successors();
    successors.nodes().addClass("hover-subtree-node");
    successors.edges().addClass("hover-subtree-edge");
}

cy.on("mouseover", "node", event => {
    const node = event.target;
    const data = node.data();

    clearHoverTrace();
    traceDescendantSubtrees(node);
    tracePrimaryRootPath(node);
    node.addClass("hover-focus-node");

    const descendantNodeCount = node.successors("node").length;
    const descendantEdgeCount = node.successors("edge").length;

    tooltip.innerHTML = `
        <div class="tooltip-title">${escapeHtml(data.label)}</div>
        <div>${escapeHtml(data.id)}</div>
        <div class="tooltip-muted">${escapeHtml(statusLabel(data.terminalStatus))}</div>
        <div class="tooltip-muted">Root path: ${formatNumber((data.primaryPathIds || []).length)} nodes</div>
        <div class="tooltip-muted">Descendants: ${formatNumber(descendantNodeCount)} nodes • ${formatNumber(descendantEdgeCount)} edges</div>
    `;
    tooltip.style.display = "block";
});

cy.on("mousemove", "node", event => {
    const original = event.originalEvent;
    if (!original) return;
    tooltip.style.left = `${original.clientX + 14}px`;
    tooltip.style.top = `${original.clientY + 14}px`;
});

cy.on("mouseout", "node", () => {
    clearHoverTrace();
    tooltip.style.display = "none";
});

document.getElementById("fitButton").addEventListener("click", () => {
    cy.fit(cy.elements(":visible"), 72);
});

document.getElementById("labelsButton").addEventListener("click", event => {
    const button = event.currentTarget;
    const labelsVisible = button.classList.toggle("active");
    cy.style()
        .selector("node")
        .style("label", labelsVisible ? "data(label)" : "")
        .update();
});

document.getElementById("clearButton").addEventListener("click", () => {
    clearSearch();
    cy.fit(cy.elements(), 72);
});

document.getElementById("searchButton").addEventListener("click", runSearch);
searchInput.addEventListener("keydown", event => {
    if (event.key === "Enter") runSearch();
    if (event.key === "Escape") {
        clearSearch();
        cy.fit(cy.elements(), 72);
    }
});

document.getElementById("pngButton").addEventListener("click", () => {
    const dataUrl = cy.png({
        full: true,
        scale: 2,
        bg: "#ffffff"
    });

    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = "reference-supertree-v9.png";
    document.body.appendChild(link);
    link.click();
    link.remove();
});

renderSummary();
</script>
</body>
</html>
'''

    replacements = {
        "__TITLE__": html.escape(title),
        "__CYTOSCAPE_SCRIPT__": cytoscape_script_tag(local_cytoscape_js),
        "__GRAPH_JSON__": graph_json,
        "__MARTIN_COLOR__": COLORS["martin"],
        "__CHENCHEN_COLOR__": COLORS["chenchen"],
        "__NEUTRAL_COLOR__": COLORS["neutral"],
        "__SEARCH_COLOR__": COLORS["search"],
    }

    for marker, value in replacements.items():
        template = template.replace(marker, value)

    return template


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an interactive Cytoscape reference supertree from the "
            "CTann v9 hierarchy CSV/TSV."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Input CTann hierarchy file. Default: data/ctann-v9.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=(
            "Output HTML file. Default: "
            "output_htmls/reference-supertree-v9.html"
        ),
    )
    parser.add_argument(
        "--title",
        default="Reference Cell Ontology Supertree — CTann v9",
        help="Title displayed in the generated HTML.",
    )
    parser.add_argument(
        "--cytoscape-js",
        type=Path,
        default=None,
        help=(
            "Optional local cytoscape.min.js file for a fully offline HTML. "
            "Without it, the HTML loads Cytoscape.js from jsDelivr."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Reference supertree builder v{BUILD_VERSION}")
    print(f"Input:  {args.input.resolve()}")
    print(f"Output: {args.output.resolve()}")

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    payload = read_supertree(args.input)
    output_html = render_html(
        payload=payload,
        title=args.title,
        local_cytoscape_js=args.cytoscape_js,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output_html, encoding="utf-8")

    summary = payload["summary"]
    print(f"Saved: {args.output.resolve()}")
    print(
        "Reference supertree: "
        f"{summary['nodeCount']} nodes, "
        f"{summary['edgeCount']} edges, "
        f"{summary['rootCount']} roots"
    )
    print(
        "Terminal source nodes: "
        f"Martin only={summary['martinTerminalCount']}, "
        f"Chenchen only={summary['chenchenTerminalCount']}, "
        f"shared={summary['sharedTerminalCount']}"
    )


if __name__ == "__main__":
    main()
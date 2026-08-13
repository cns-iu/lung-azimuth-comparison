"""CTann tool-agreement view.

Measures where the CTann tools in HRApop agree or disagree on lung cell-type
labels, overlaid on the shared supertree.

Why two axes
------------
Counting tools per exact CLID is misleading on its own. Every tool "sees"
macrophages, but only one uses the generic ``macrophage`` label — the rest
scatter into ``lung macrophage``, ``elicited macrophage`` and so on. That is a
disagreement about *granularity*, not about biology, and it is invisible unless
the hierarchy is taken into account. So each node carries:

``coverage``
    how many tools call this cell type *or any of its descendants* — i.e. how
    many tools see this population at all (0 means nobody does).
``consensus``
    of those tools, how many use *this exact* label.

The signed score fed to the diverging colour scale is::

    score = (2 * exact - coverage) / coverage        in [-1, +1]

     +1  every tool that sees this population labels it exactly here
      0  half label it here, half use finer labels
     -1  tools see it, but none use this label

Coverage is encoded separately (node size), so a cell type called by a single
tool cannot masquerade as perfect consensus.

Bands
-----
Curated "easy" / "difficult" cell types are declared in the view config as
subtree roots; the band is inherited by every descendant. A CLID listed
explicitly always keeps its own band, so an easy cell type nested inside a
difficult subtree (aerocyte inside capillary endothelial cell) stays easy.
"""

from __future__ import annotations

import copy
from typing import Any

from ..normalize import normalize_payload
from ..overlays import read_hrapop_tool_calls
from . import BuildContext

# Score cut-points for the coarse status buckets (used by the minimap).
AGREE_AT = 0.34
DISAGREE_AT = -0.34


def _children_map(tree) -> dict[str, list[str]]:
    return {n["data"]["id"]: list(n["data"].get("childIds", [])) for n in tree.nodes}


def _descendants(children: dict[str, list[str]], roots: list[str]) -> dict[str, set[str]]:
    """Inclusive descendant set per node, memoized, cycle-safe."""
    cache: dict[str, set[str]] = {}

    def walk(node_id: str, stack: set[str]) -> set[str]:
        if node_id in cache:
            return cache[node_id]
        if node_id in stack:
            return {node_id}
        stack.add(node_id)
        acc = {node_id}
        for child in children.get(node_id, []):
            acc |= walk(child, stack)
        stack.discard(node_id)
        cache[node_id] = acc
        return acc

    for node_id in roots:
        walk(node_id, set())
    return cache


def _resolve_bands(
    bands: dict[str, list[str]],
    descendants: dict[str, set[str]],
    known: set[str],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Map node id -> band, with explicit listings beating inherited ones."""
    inherited: dict[str, str] = {}
    for band in ("difficult", "easy"):
        for root in bands.get(band, []):
            for node_id in descendants.get(root, {root}):
                inherited[node_id] = band

    explicit = {
        node_id: band
        for band in ("difficult", "easy")
        for node_id in bands.get(band, [])
    }

    resolved = dict(inherited)
    resolved.update(explicit)

    missing = {
        band: sorted(node_id for node_id in bands.get(band, []) if node_id not in known)
        for band in ("easy", "difficult")
    }
    return resolved, missing


def build_payload(view: Any, context: BuildContext) -> dict[str, Any]:
    tree = context.trees[view.base[0]]
    ov = view.overlay

    calls = read_hrapop_tool_calls(
        context.root / ov["hrapop"],
        organ=ov.get("organ", "lung"),
        modality=ov.get("modality", "sc_transcriptomics"),
        tools=ov.get("tools"),
    )
    tools = calls.tools
    tool_count = len(tools)
    tool_index = {name: i for i, name in enumerate(tools)}

    tree_ids = set(tree.index)
    children = _children_map(tree)
    descendants = _descendants(children, list(tree_ids))

    bands_cfg = view.raw.get("bands", {})
    band_of, band_missing = _resolve_bands(bands_cfg, descendants, tree_ids)

    nodes: list[dict[str, Any]] = []
    buckets = {"agree": 0, "mixed": 0, "disagree": 0, "unused": 0, "inactive": 0}
    band_totals = {"easy": 0, "difficult": 0, "other": 0}
    scored_by_band: dict[str, list[float]] = {"easy": [], "difficult": [], "other": []}

    for src in tree.nodes:
        node = copy.deepcopy(src)
        node_id = node["data"]["id"]

        exact = sorted(calls.by_clid.get(node_id, set()), key=str.casefold)
        subtree: set[str] = set()
        for member in descendants.get(node_id, {node_id}):
            subtree |= calls.by_clid.get(member, set())
        subtree_sorted = sorted(subtree, key=str.casefold)

        coverage = len(subtree)
        exact_n = len(exact)
        score = (2 * exact_n - coverage) / coverage if coverage else 0.0

        # The diverging scale answers "of the tools that see this population,
        # how many use THIS label". That question is degenerate when no tool
        # proposes the label at all — which is true of every high-level ancestor
        # (nothing is annotated "cell"). Those get their own state rather than
        # being painted as maximal disagreement.
        if not coverage:
            status = "inactive"
        elif exact_n == 0:
            status = "unused"
        elif score >= AGREE_AT:
            status = "agree"
        elif score <= DISAGREE_AT:
            status = "disagree"
        else:
            status = "mixed"
        buckets[status] += 1

        band = band_of.get(node_id, "")
        band_totals[band or "other"] += 1
        if exact_n:
            scored_by_band[band or "other"].append(score)

        node["data"]["terminalStatus"] = status
        node["data"]["styleData"] = {
            "score": round(score, 4),
            "coverage": coverage,
            "exactCount": exact_n,
            "band": band,
        }
        node["data"]["overlay"] = {
            "exact": [tool_index[t] for t in exact if t in tool_index],
            "subtree": [tool_index[t] for t in subtree_sorted if t in tool_index],
        }
        nodes.append(node)

    unmapped = sorted(set(calls.by_clid) - tree_ids)

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    summary = {
        "inputFile": calls.input_file,
        "rowCount": calls.row_count,
        "nodeCount": len(nodes),
        "edgeCount": len(tree.edges),
        "rootCount": tree.summary.get("rootCount", 1),
        "tools": tools,
        "toolCount": tool_count,
        "groupCount": calls.group_count,
        "calledClidCount": len(calls.by_clid),
        "mappedClidCount": len(set(calls.by_clid) & tree_ids),
        "unmappedClidCount": len(unmapped),
        "unmapped": unmapped,
        "buckets": buckets,
        "activeNodeCount": len(nodes) - buckets["inactive"],
        "proposedNodeCount": buckets["agree"] + buckets["mixed"] + buckets["disagree"],
        "bandCounts": band_totals,
        # Nodes contributing to the mean, i.e. labels at least one tool proposes.
        # Reported alongside the mean so both use the same denominator.
        "bandScoredCounts": {
            key: len(values) for key, values in scored_by_band.items()
        },
        "bandMeanScore": {
            "easy": mean(scored_by_band["easy"]),
            "difficult": mean(scored_by_band["difficult"]),
            "other": mean(scored_by_band["other"]),
        },
        "bandMissing": band_missing,
        "toolClidCounts": [
            {"tool": t, "clidCount": sum(1 for s in calls.by_clid.values() if t in s)}
            for t in tools
        ],
    }

    return normalize_payload(nodes, tree.edges, summary)

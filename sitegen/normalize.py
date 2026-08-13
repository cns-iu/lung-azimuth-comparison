"""Compact, deduplicated JSON emitted per view (design step 3).

The rich in-memory node carries every label several times over
(``parentLabels``, ``childLabels``, ``primaryPathLabels``, ``primaryPathText``)
plus repeated ontology ids and source names. Across hundreds of nodes and
thousands of references that dominates payload size and, more importantly,
browser parse time and memory.

Normalization interns every string once into a shared pool and references it by
index. Node relationships reference other nodes by their ordinal in the ``nodes``
array. All label arrays are dropped entirely: the front-end ``hydrate()`` in
``view-runtime.js`` rebuilds them from ids + the pool, reproducing the exact
``data`` shape the Cytoscape templates expect.

View modules intern their overlay strings into the *same* :class:`StringPool`,
so a per-node anatomical-structure name shared by hundreds of nodes is stored
once for the whole file.
"""

from __future__ import annotations

from typing import Any


class StringPool:
    """Deduplicating string interner producing a compact index table."""

    def __init__(self) -> None:
        self._items: list[str] = []
        self._index: dict[str, int] = {}

    def intern(self, value: str) -> int:
        idx = self._index.get(value)
        if idx is None:
            idx = len(self._items)
            self._index[value] = idx
            self._items.append(value)
        return idx

    def intern_list(self, values: list[str]) -> list[int]:
        return [self.intern(v) for v in values]

    @property
    def table(self) -> list[str]:
        return self._items


def normalize_payload(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    pool: StringPool | None = None,
) -> dict[str, Any]:
    """Compact a rich node/edge payload into deduplicated wire form.

    Each node may carry a pre-compacted ``data['overlay']`` block (a plain dict
    of small values or pool indices produced by the view module). Overlay values
    are copied through verbatim; string interning of overlay content is the
    view module's responsibility so the same pool is shared.
    """
    pool = pool or StringPool()

    # node id -> ordinal, so relationships reference nodes compactly.
    ordinal: dict[str, int] = {
        node["data"]["id"]: i for i, node in enumerate(nodes)
    }

    def refs(ids: list[str]) -> list[int]:
        # Preserve only ids present in this tree; foreign refs are dropped.
        return [ordinal[i] for i in ids if i in ordinal]

    out_nodes: list[dict[str, Any]] = []
    for node in nodes:
        data = node["data"]
        pos = node.get("position", {})
        compact: dict[str, Any] = {
            "id": pool.intern(data["id"]),
            "label": pool.intern(data.get("label", data["id"])),
            "depth": data.get("depth", 0),
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "status": data.get("terminalStatus", "neutral"),
            "isRoot": bool(data.get("isRoot", False)),
            "parents": refs(data.get("parentIds", [])),
            "children": refs(data.get("childIds", [])),
            "path": refs(data.get("primaryPathIds", [])),
            "sources": pool.intern_list(data.get("sources", [])),
            "terminalSources": pool.intern_list(data.get("terminalSources", [])),
            "labelVariants": pool.intern_list(data.get("labelVariants", [])),
        }
        primary_parent_id = data.get("primaryParentId") or ""
        compact["primaryParent"] = (
            ordinal[primary_parent_id]
            if primary_parent_id in ordinal
            else -1
        )
        overlay = data.get("overlay")
        if overlay:
            compact["overlay"] = overlay
        # Cytoscape selectors and mapData() only read top-level data keys, so a
        # view can promote the few fields it styles on via "styleData".
        style_data = data.get("styleData")
        if style_data:
            compact["st"] = style_data
        out_nodes.append(compact)

    out_edges: list[dict[str, Any]] = []
    for edge in edges:
        d = edge["data"]
        src, tgt = d["source"], d["target"]
        if src not in ordinal or tgt not in ordinal:
            continue
        out_edges.append(
            {
                "s": ordinal[src],
                "t": ordinal[tgt],
                "rowCount": d.get("rowCount", 1),
                "primary": bool(d.get("isPrimary", False)),
            }
        )

    return {
        "strings": pool.table,
        "nodes": out_nodes,
        "edges": out_edges,
        "summary": summary,
    }

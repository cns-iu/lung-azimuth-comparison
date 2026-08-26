"""Overlay readers: per-view values keyed by ontology node id.

Overlays never define topology — they annotate the shared reference tree by
ontology id (the forest-wide join key). This module holds the HRApop population
reader used by the population view.

The reader is the streamlined form: it collects per-cell-type tool metadata and
the set of ids each tool directly output. The heavy per-node AS x sex comparison
tables from the original builder are intentionally omitted (see the streamlined
port decision) since they dominated payload size and are not shown.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .ontology import normalize_ontology_id

HRAPOP_REQUIRED = {
    "organ", "as", "as_label", "sex", "tool", "modality",
    "cell_id", "cell_label", "cell_count", "cell_percentage", "dataset_count",
}


@dataclass
class HrapopOverlay:
    metadata: dict[str, dict[str, dict[str, set[str]]]]
    lung_ids: set[str]
    pan_ids: set[str]
    filtered_row_count: int = 0
    blank_id_row_count: int = 0
    input_file: str = ""

    def meta_for(self, side: str, cell_id: str) -> dict[str, list[str]]:
        item = self.metadata[side].get(cell_id)
        if not item:
            return {"labels": [], "sexes": [], "asLabels": [], "datasetCounts": []}
        s = lambda v: sorted(v, key=str.casefold)
        return {
            "labels": s(item["labels"]),
            "sexes": s(item["sexes"]),
            "asLabels": s(item["as_labels"]),
            "datasetCounts": s(item["dataset_counts"]),
        }


def read_hrapop(
    path: Path,
    *,
    organ: str,
    lung_tool: str,
    pan_tool: str,
    modality: str,
) -> HrapopOverlay:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = HRAPOP_REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Missing required HRApop columns in {path}: {sorted(missing)}"
            )
        rows = list(reader)

    organ_key = organ.strip().casefold()
    lung_key = lung_tool.strip().casefold()
    pan_key = pan_tool.strip().casefold()
    modality_key = modality.strip().casefold()

    def new_item() -> dict[str, set[str]]:
        return {"labels": set(), "sexes": set(), "as_labels": set(), "dataset_counts": set()}

    metadata: dict[str, dict[str, dict[str, set[str]]]] = {
        "lung": defaultdict(new_item),
        "pan": defaultdict(new_item),
    }

    filtered = 0
    blank = 0
    for row in rows:
        if (row.get("organ") or "").strip().casefold() != organ_key:
            continue
        if (row.get("modality") or "").strip().casefold() != modality_key:
            continue
        tool = (row.get("tool") or "").strip().casefold()
        if tool not in {lung_key, pan_key}:
            continue

        filtered += 1
        side = "lung" if tool == lung_key else "pan"

        cell_id = normalize_ontology_id(row.get("cell_id"))
        if not cell_id:
            blank += 1
            continue

        item = metadata[side][cell_id]
        cell_label = (row.get("cell_label") or "").strip()
        as_label = (row.get("as_label") or "").strip()
        sex = (row.get("sex") or "").strip() or "Unknown"
        dataset_count = (row.get("dataset_count") or "").strip()
        if cell_label:
            item["labels"].add(cell_label)
        if as_label:
            item["as_labels"].add(as_label)
        if dataset_count:
            item["dataset_counts"].add(dataset_count)
        item["sexes"].add(sex)

    if filtered == 0:
        raise ValueError(
            f"No HRApop rows matched organ={organ!r}, modality={modality!r}, "
            f"tools {lung_tool!r}/{pan_tool!r}."
        )

    return HrapopOverlay(
        metadata=metadata,
        lung_ids=set(metadata["lung"]),
        pan_ids=set(metadata["pan"]),
        filtered_row_count=filtered,
        blank_id_row_count=blank,
        input_file=path.name,
    )


# --------------------------------------------------------------------------- #
# HLCA exact-node comparison overlay
# --------------------------------------------------------------------------- #

HLCA_COUNT_COLUMNS = (
    "azimuth_count", "pan_human_count", "both_same_cell_count",
    "azimuth_only_count", "pan_human_only_count", "union_count",
)


def _nonneg_int(value: str | None) -> int:
    raw = (value or "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return 0


def _status_from_counts(azimuth: int, pan: int) -> str:
    if azimuth > 0 and pan > 0:
        return "shared"
    if azimuth > 0:
        return "azimuth_only"
    if pan > 0:
        return "pan_only"
    return "neutral"


@dataclass
class HlcaOverlay:
    aggregates: dict[str, dict[str, Any]]  # clid -> aggregate, pooled over all rows
    mapping_status_counts: dict[str, int] = field(default_factory=dict)
    outside_clids: set[str] = field(default_factory=set)
    row_count: int = 0
    input_file: str = ""
    # Individual mapped rows, kept so the view can rebuild aggregates under the
    # sex / author-label filters the front-end applies.
    mapped_rows: list[dict[str, Any]] = field(default_factory=list)


def read_comparison(path: Path) -> HlcaOverlay:
    """Read the HLCA aggregate comparison CSV and aggregate counts per CLID."""
    from collections import Counter

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    status_counts: Counter[str] = Counter()
    by_clid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mapped_rows: list[dict[str, Any]] = []
    for row in rows:
        mapping = (row.get("mapping_status") or "").strip()
        status_counts[mapping] += 1
        if mapping != "mapped_clid":
            continue
        clid = normalize_ontology_id(row.get("clid"))
        if not clid:
            continue
        parsed = {c: _nonneg_int(row.get(c)) for c in HLCA_COUNT_COLUMNS}
        parsed["clid"] = clid
        parsed["sex"] = (row.get("sex") or "").strip()
        parsed["ann_finest_level"] = (row.get("ann_finest_level") or "").strip()
        parsed["author_cohort_size"] = _nonneg_int(row.get("author_cohort_size"))
        by_clid[clid].append(parsed)
        mapped_rows.append(parsed)

    aggregates: dict[str, dict[str, Any]] = {}
    for clid, group in by_clid.items():
        cohort_sizes: dict[tuple[str, str], int] = {}
        totals = dict.fromkeys(HLCA_COUNT_COLUMNS, 0)
        for row in group:
            if row["azimuth_count"] <= 0 and row["pan_human_count"] <= 0:
                continue
            cohort_sizes[(row["sex"], row["ann_finest_level"])] = row["author_cohort_size"]
            for col in HLCA_COUNT_COLUMNS:
                totals[col] += row[col]
        aggregates[clid] = {
            "azimuth": totals["azimuth_count"],
            "pan": totals["pan_human_count"],
            "both": totals["both_same_cell_count"],
            "azimuthOnly": totals["azimuth_only_count"],
            "panOnly": totals["pan_human_only_count"],
            "union": totals["union_count"],
            "cohortCount": len(cohort_sizes),
            "cohortCellCount": sum(cohort_sizes.values()),
            "status": _status_from_counts(totals["azimuth_count"], totals["pan_human_count"]),
        }

    return HlcaOverlay(
        aggregates=aggregates,
        mapping_status_counts=dict(status_counts),
        row_count=len(rows),
        input_file=path.name,
        mapped_rows=mapped_rows,
    )


# --------------------------------------------------------------------------- #
# CTann tool-agreement overlay
# --------------------------------------------------------------------------- #


@dataclass
class ToolCalls:
    """Which CTann tools output each cell type, pooled across AS x sex groups."""

    by_clid: dict[str, set[str]]
    tools: list[str]
    labels: dict[str, str] = field(default_factory=dict)
    row_count: int = 0
    group_count: int = 0
    zero_count_rows: int = 0
    input_file: str = ""


def read_hrapop_tool_calls(
    path: Path,
    *,
    organ: str,
    modality: str,
    tools: Iterable[str] | None = None,
) -> ToolCalls:
    """Read HRApop and record, per cell type, the set of tools that call it.

    A tool "calls" a cell type when it reports a nonzero cell count for it in at
    least one anatomical-structure x sex group (presence, pooled across groups).
    """
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = HRAPOP_REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Missing required HRApop columns in {path}: {sorted(missing)}"
            )
        rows = list(reader)

    organ_key = organ.strip().casefold()
    modality_key = modality.strip().casefold()
    wanted = {t.strip().casefold() for t in tools} if tools else None

    by_clid: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    seen_tools: set[str] = set()
    groups: set[tuple[str, str]] = set()
    kept = 0
    zero_rows = 0

    for row in rows:
        if (row.get("organ") or "").strip().casefold() != organ_key:
            continue
        if (row.get("modality") or "").strip().casefold() != modality_key:
            continue

        tool = (row.get("tool") or "").strip()
        if wanted is not None and tool.casefold() not in wanted:
            continue

        clid = normalize_ontology_id(row.get("cell_id"))
        if not clid:
            continue

        kept += 1
        seen_tools.add(tool)
        label = (row.get("cell_label") or "").strip()
        if label:
            labels.setdefault(clid, label)
        groups.add(((row.get("as") or "").strip(), (row.get("sex") or "").strip()))

        raw = (row.get("cell_count") or "").strip()
        try:
            count = float(raw) if raw else 0.0
        except ValueError:
            count = 1.0  # unparseable but present
        if count <= 0:
            zero_rows += 1
            continue

        by_clid[clid].add(tool)

    if not kept:
        raise ValueError(
            f"No HRApop rows matched organ={organ!r}, modality={modality!r} in {path}."
        )

    return ToolCalls(
        by_clid=dict(by_clid),
        tools=sorted(seen_tools, key=str.casefold),
        labels=labels,
        row_count=kept,
        group_count=len(groups),
        zero_count_rows=zero_rows,
        input_file=path.name,
    )

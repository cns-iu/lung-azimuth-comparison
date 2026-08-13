"""Shared layout constants for the column/row tree diagram.

Every view lays the reference tree out identically, so these constants live in
one place. ``x`` is driven by a node's depth from the root; ``y`` by a recursive
leaf-ordering walk (see :mod:`sitegen.reference_tree`).
"""

from __future__ import annotations

# Deepest ontology path level read from the CSV (AS/1 .. AS/N).
MAX_PATH_LEVEL = 12

# Pixel spacing used when materializing node positions.
COLUMN_DX = 292.5   # horizontal distance between depth columns
ROW_DY = 8.5        # vertical distance between layout rows
LEAF_STEP = 3.0     # rows consumed by each leaf in the recursive layout
ROOT_GAP = 2.0      # extra rows inserted between separate roots

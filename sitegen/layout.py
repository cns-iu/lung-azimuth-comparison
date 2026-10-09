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
ROW_DY = 10.5  # vertical distance between layout rows
ROOT_GAP = 2.0      # extra rows inserted between separate roots

# A node's label hangs below it and wraps, so a leaf has to reserve room for as
# many lines as its label takes. Without this the row pitch is a flat 25.5 units
# while a one-line label already reaches ~23 below the node's centre, and a
# two-line label runs straight through the node beneath it.
LABEL_WRAP_CHARS = 38   # characters per line at font-size 10 in 200 units
LABEL_LINE_ROWS = 1.3   # extra rows for each line after the first
LEAF_MIN_ROWS = 4.0     # rows a single-line leaf needs: node + gap + one line

"""Shared ontology-identifier and CSV-delimiter helpers.

Extracted verbatim from the original standalone builders, which each carried
their own copy. Keeping a single implementation is the reason the reference
tree parsed here is guaranteed identical across every view.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

_OBO_PREFIXES = (
    "https://purl.obolibrary.org/obo/",
    "http://purl.obolibrary.org/obo/",
)

_CURIE_RE = re.compile(r"([A-Za-z][A-Za-z0-9-]*)[_:]([A-Za-z0-9_.-]+)")


def normalize_ontology_id(value: str | None) -> str:
    """Normalize common OBO URI, underscore, and CURIE identifiers.

    ``http://purl.obolibrary.org/obo/CL_0000583`` and ``CL:0000583`` both
    collapse to the canonical CURIE ``CL:0000583``. Non-OBO identifiers are
    preserved unchanged so foreign namespaces still round-trip.
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    for prefix in _OBO_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break

    match = _CURIE_RE.fullmatch(raw)
    if match:
        return f"{match.group(1).upper()}:{match.group(2)}"

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

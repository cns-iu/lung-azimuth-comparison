"""Design-config cascade: deep-merge a view's design down its ``extends`` chain.

This is dimension 2/3 of the inheritance model. A view names a parent via
``extends``; its resolved design is the parent's resolved design deep-merged
with the view's own overrides, child keys winning. Unspecified keys fall
through from the parent, so common design lives once in the ``base`` config and
each view carries only its delta.

The ``extends`` axis is independent of the data ``base`` axis (see
:mod:`sitegen.manifest`), so several data roots can share one design base.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base``; ``override`` wins.

    Nested dicts merge key-by-key. Any non-dict value (including lists) is
    replaced wholesale — lists are treated as atomic design values, not merged,
    so a child that specifies ``colors`` or a legend order replaces it cleanly.
    """
    result = deepcopy(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = deep_merge(existing, value)
        else:
            result[key] = deepcopy(value)
    return result


def resolve_design(
    view_id: str,
    designs: dict[str, dict[str, Any]],
    extends: dict[str, str | None],
) -> dict[str, Any]:
    """Resolve the fully-merged design for ``view_id``.

    ``designs`` maps view id -> that view's own (delta) design block.
    ``extends`` maps view id -> parent id (or ``None`` for a root). The chain is
    walked to the root and merged root-first so leaves override ancestors.
    """
    chain: list[str] = []
    seen: set[str] = set()
    current: str | None = view_id
    while current is not None:
        if current in seen:
            raise ValueError(
                f"Cyclic 'extends' chain detected at view '{current}'."
            )
        seen.add(current)
        chain.append(current)
        current = extends.get(current)

    resolved: dict[str, Any] = {}
    for node_id in reversed(chain):  # root -> leaf
        resolved = deep_merge(resolved, designs.get(node_id, {}))
    return resolved

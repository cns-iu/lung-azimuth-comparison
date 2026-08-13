"""Load the site manifest and resolve the view dependency forest.

``site.json`` is the single place you edit to add a tab. It lists views in tab
order; each entry references a ``config/<id>.json`` file that declares the two
independent inheritance edges:

* ``extends`` -> parent view id for the **design** cascade (may be a pure design
  base that renders nothing itself).
* ``base``    -> parent view id(s) for **data** composition, i.e. which
  reference tree(s) this view overlays. A list enables cross-tree views.

A view with neither a ``base`` nor a ``treeData`` root in its chain is invalid;
a view that supplies ``treeData`` *is* a data root (a reference tree).

The manifest is compiled into a topological order so parents build before
children, which also gives change-propagation for free: rebuild descendants
whenever an ancestor's inputs change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class View:
    """One resolved view entry from the manifest + its config file."""

    id: str
    title: str                     # page title / header, from the view config
    tab_title: str                 # shell tab label, from the manifest entry
    kind: str                      # "reference" | "population" | "hlca" | ...
    show_tab: bool = True
    extends: str | None = None     # design-cascade parent
    base: list[str] = field(default_factory=list)  # data-composition parents
    tree_data: str | None = None   # raw CSV path if this view is a data root
    overlay: dict[str, Any] = field(default_factory=dict)  # overlay inputs
    design: dict[str, Any] = field(default_factory=dict)   # design delta
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_data_root(self) -> bool:
        return self.tree_data is not None


@dataclass
class Manifest:
    views: list[View]
    order: list[str]               # topologically sorted view ids

    def by_id(self, view_id: str) -> View:
        for view in self.views:
            if view.id == view_id:
                return view
        raise KeyError(view_id)

    @property
    def tabs(self) -> list[View]:
        """Views that appear as tabs, in manifest (author) order."""
        return [v for v in self.views if v.show_tab]

    def extends_map(self) -> dict[str, str | None]:
        return {v.id: v.extends for v in self.views}

    def design_map(self) -> dict[str, dict[str, Any]]:
        return {v.id: v.design for v in self.views}


def _load_config(config_dir: Path, ref: str) -> dict[str, Any]:
    path = config_dir / ref
    if not path.exists():
        raise FileNotFoundError(f"Config file referenced by manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(manifest_path: Path) -> Manifest:
    """Load ``site.json`` and every referenced config into a :class:`Manifest`."""
    root = manifest_path.parent
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    config_dir = root / spec.get("configDir", "config")

    views: list[View] = []
    for entry in spec["views"]:
        cfg = _load_config(config_dir, entry["config"])
        base = cfg.get("base", [])
        if isinstance(base, str):
            base = [base]
        # The view config owns the page title; the manifest entry owns the tab
        # label, so a tab can be renamed without touching the page heading.
        view_title = cfg.get("title", cfg["id"])
        views.append(
            View(
                id=cfg["id"],
                title=view_title,
                tab_title=entry.get("title", view_title),
                kind=cfg.get("kind", cfg["id"]),
                show_tab=entry.get("tab", cfg.get("tab", True)),
                extends=cfg.get("extends"),
                base=list(base),
                tree_data=cfg.get("treeData"),
                overlay=cfg.get("overlay", {}),
                design=cfg.get("design", {}),
                raw=cfg,
            )
        )

    order = _topo_sort(views)
    return Manifest(views=views, order=order)


def _topo_sort(views: list[View]) -> list[str]:
    """Order views so every ``extends``/``base`` parent precedes its children.

    Both inheritance edges constrain build order: a design parent must resolve
    first, and a data parent's tree must exist before an overlay composes on it.
    """
    ids = {v.id for v in views}
    deps: dict[str, set[str]] = {}
    for view in views:
        parents: set[str] = set(view.base)
        if view.extends is not None:
            parents.add(view.extends)
        unknown = parents - ids
        if unknown:
            raise ValueError(
                f"View '{view.id}' references unknown parents: {sorted(unknown)}"
            )
        deps[view.id] = parents

    order: list[str] = []
    placed: set[str] = set()
    # Stable Kahn-style sort: preserve manifest order among ready nodes.
    manifest_order = [v.id for v in views]
    while len(order) < len(views):
        ready = [
            vid for vid in manifest_order
            if vid not in placed and deps[vid] <= placed
        ]
        if not ready:
            remaining = [vid for vid in manifest_order if vid not in placed]
            raise ValueError(
                f"Cyclic dependency among views: {remaining}"
            )
        for vid in ready:
            order.append(vid)
            placed.add(vid)
    return order

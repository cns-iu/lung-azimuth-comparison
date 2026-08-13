#!/usr/bin/env python3
"""Single entrypoint: build the static comparison site into ``docs/``.

Run without arguments::

    python3 build.py

Flow
----
1. Load ``site.json`` (the manifest / dependency forest).
2. Topologically sort the views so every ``extends``/``base`` parent builds
   before its children.
3. Parse each reference tree once (a data root) and cache it.
4. For each renderable view: resolve its design down the ``extends`` chain,
   build + normalize its data payload, and emit ``docs/data/<id>.json`` and
   ``docs/views/<id>.html``.
5. Copy shared assets and emit the registry-driven ``docs/index.html`` shell.

A view is *renderable* when it is a data root (supplies ``treeData``) or has at
least one data ``base``. Pure design bases (e.g. ``base.json``) are resolved for
the cascade but never emitted.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from sitegen.cascade import resolve_design
from sitegen.manifest import load_manifest
from sitegen.reference_tree import build_reference_tree
from sitegen.render import render_app, view_config
from sitegen.views import BuildContext, get_builder

SCRIPT_DIR = Path(__file__).resolve().parent


def build(manifest_path: Path, output_dir: Path, assets_dir: Path) -> None:
    manifest = load_manifest(manifest_path)
    root = manifest_path.parent
    site_spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    site_meta = site_spec.get("site", {})
    cytoscape_cdn = site_spec.get(
        "cytoscapeCdn",
        "https://cdn.jsdelivr.net/npm/cytoscape@3.33.1/dist/cytoscape.min.js",
    )

    data_out = output_dir / "data"
    for directory in (output_dir, data_out):
        directory.mkdir(parents=True, exist_ok=True)

    context = BuildContext(root=root, data_dir=data_out)
    extends = manifest.extends_map()
    designs = manifest.design_map()

    built: list[str] = []
    view_configs: list[dict] = []
    for view_id in manifest.order:
        view = manifest.by_id(view_id)

        # A data root's tree is parsed once and cached for its descendants.
        if view.is_data_root:
            tree_path = root / view.tree_data
            sources_cfg = view.raw.get("sources", {})
            context.trees[view.id] = build_reference_tree(
                tree_path,
                exclude_sources=sources_cfg.get("exclude", ()),
                compare_specs=sources_cfg.get("compare", ()),
            )

        renderable = view.is_data_root or bool(view.base)
        if not renderable:
            continue

        resolved = resolve_design(view.id, designs, extends)

        payload = get_builder(view.kind)(view, context)
        (data_out / f"{view.id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        if view.show_tab:
            view_configs.append(view_config(view, resolved))
        built.append(view.id)
        print(f"  built view '{view.id}' ({view.kind})")

    # Shared front-end assets.
    if assets_dir.exists():
        shutil.copytree(assets_dir, output_dir / "assets", dirs_exist_ok=True)

    # Serve files verbatim on GitHub Pages (skip Jekyll processing).
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")

    app = render_app(manifest, site_meta, view_configs, cytoscape_cdn)
    (output_dir / "index.html").write_text(app, encoding="utf-8")
    print(f"  built app 'index.html' with {len(manifest.tabs)} tab(s)")
    print(f"Done. {len(built)} view(s) written to {output_dir}/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=SCRIPT_DIR / "site.json",
        help="Path to the site manifest (default: site.json).",
    )
    parser.add_argument(
        "--output", type=Path, default=SCRIPT_DIR / "docs",
        help="Output directory for the static site (default: docs/).",
    )
    parser.add_argument(
        "--assets", type=Path, default=SCRIPT_DIR / "assets",
        help="Shared front-end assets directory (default: assets/).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build(args.manifest, args.output, args.assets)


if __name__ == "__main__":
    main()

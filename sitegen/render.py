"""Emit the single-document application page.

The site is one HTML document: a sidebar carrying the brand, the active view's
header, search, and its panels; and a main column carrying the tab bar and one
graph pane per view. Panes are empty at build time — ``app.js`` builds each on
first activation and keeps it, so switching tabs preserves graph state.

All per-view configuration (title, subtitle, resolved design, data URL) is
injected as ``window.SITE_CONFIG``; per-view rendering lives in the kind module
for that view's ``kind``.
"""

from __future__ import annotations

import html
import json
from typing import Any

from .manifest import Manifest, View


def _json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def view_config(view: View, resolved_design: dict[str, Any]) -> dict[str, Any]:
    """The per-view object handed to the front-end."""
    return {
        "id": view.id,
        "kind": view.kind,
        "title": view.title,
        "subtitle": view.raw.get("subtitle", ""),
        "tabTitle": view.tab_title,
        "dataUrl": f"data/{view.id}.json",
        "design": resolved_design,
        "params": view.raw.get("params", {}),
    }


def render_app(
    manifest: Manifest,
    site_meta: dict[str, Any],
    view_configs: list[dict[str, Any]],
    cytoscape_cdn: str,
    asset_version: str = "",
) -> str:
    """Return the complete application document (``docs/index.html``)."""
    tabs = manifest.tabs
    title = site_meta.get("title", "CTs SuperTree")

    # Browsers (and GitHub Pages) cache JS and CSS aggressively. Stamping every
    # local asset URL with a hash of the asset contents means a rebuild that
    # changes an asset changes its URL, so viewers never see a stale mix.
    ver = f"?v={asset_version}" if asset_version else ""


    tab_buttons = "\n".join(
        f'    <button class="tab" role="tab" data-view="{html.escape(v.id)}">'
        f"{html.escape(v.tab_title)}</button>"
        for v in tabs
    )

    panes = "\n".join(
        f"""    <section class="graph-pane" id="pane-{html.escape(v.id)}"
             role="tabpanel" aria-label="{html.escape(v.tab_title)}">
      <div class="cy-host" id="cy-{html.escape(v.id)}"></div>
      <canvas class="node-overlay"></canvas>
      <div class="status-badge"></div>
      <div class="minimap" title="Drag the box to pan · drag elsewhere to zoom to that region · click to centre · double-click to fit">
        <canvas role="img" aria-label="Overview of the whole graph with the current viewport marked"></canvas>
        <button type="button" class="minimap-reset" title="Reset" aria-label="Reset the view to fit the whole graph">
          <img src="assets/icons/reset.png{ver}" alt="" width="14" height="14" />
        </button>
      </div>
      <div class="legend"></div>
      <div class="view-status">Loading view…</div>
    </section>"""
        for v in tabs
    )

    kinds = sorted({v.kind for v in tabs})
    kind_scripts = "\n".join(
        f'<script src="assets/kinds/{html.escape(kind)}.js{ver}"></script>'
        for kind in kinds
    )

    site_config = {"title": title, "views": view_configs}

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="assets/app.css{ver}" />
<script src="{html.escape(cytoscape_cdn)}"></script>
</head>
<body>

<aside id="sidebar">
  <div id="brandBar"><span id="siteTitle">{html.escape(title)}</span></div>

  <div id="viewHeader">
    <h1 id="viewTitle"></h1>
    <p id="viewDescription"></p>
  </div>

  <div id="searchWrap">
    <input id="searchInput" type="search"
           placeholder="Search cell type, ID, source" autocomplete="off"
           aria-label="Search the graph" />
    <button id="searchButton" title="Search" aria-label="Search">⌕</button>
  </div>

  <!-- Per-view controls (e.g. scope filters); empty for views without any. -->
  <div id="viewFilters"></div>

  <!-- Details first: it responds to clicks, so it sits at the scroller's
       default position. The static summary cards follow underneath. -->
  <div id="panelScroller">
    <div id="detailsPanel" class="empty-state">Select a node to inspect its details.</div>
    <div id="summaryPanel"></div>
  </div>
</aside>

<main id="main">
  <nav id="tabBar" role="tablist">
{tab_buttons}
  </nav>
  <div id="paneStack">
{panes}
  </div>
</main>

<div id="tooltip"></div>

<script>window.SITE_CONFIG = {_json_for_script(site_config)};</script>
<script src="assets/view-utils.js{ver}"></script>
{kind_scripts}
<script src="assets/app.js{ver}"></script>
</body>
</html>
"""

# CTs Supertree (lung-azimuth-comparison)

Interactive comparison of **Azimuth** and **Pan-human Azimuth** cell-type
annotations for human lung datasets, rendered on the CTann v10 cell-type
supertree and published as a static site on GitHub Pages.

The site has five tabs. The first is a text page; the rest are interactive
Cytoscape views:

0. **Overview** — what the supertree is and what each other tab shows. The
   landing page; its copy lives in `config/overview.json`.
1. **Reference Supertree** — the CTann v10 cell-type supertree (the base every
   other view is built on), with each node drawn as a ten-slot bar showing which
   sources name that cell type.
2. **HRApop Comparison** — HRApop v1.1 lung Azimuth vs Pan-human Azimuth
   populations overlaid on the tree.
3. **HLCA Node Comparison** — Azimuth vs Pan-human Azimuth exact-CLID
   predictions across paired HLCA lung partitions.
4. **Tool Agreement** — where five CTann tools agree or disagree on lung
   cell-type labels (see below).

## Tool agreement

Built from the same HRApop CSV as tab 2, using all five CTann tools for
`organ=lung`, `modality=sc_transcriptomics`: `azimuth`, `celltypist`, `frmatch`,
`pan-human-azimuth`, `popv`. All five cover all 31 anatomical-structure x sex
groups, so a tool not calling a cell type is real signal rather than missing
data. Calls are pooled across groups (presence, any nonzero cell count).

Counting tools per exact CLID is misleading on its own: all five tools see
macrophages, but only one uses the generic `macrophage` label — the rest scatter
into `lung macrophage`, `elicited macrophage`, and so on. That is a disagreement
about *granularity*, which only the hierarchy reveals. So each node carries two
independent measures:

- **coverage** — how many tools annotate this cell type *or anything beneath it*
- **consensus** — of those tools, how many use this exact label

```
score = (2 * exact - coverage) / coverage        in [-1, +1]
```

`+1` every tool that annotates the population uses this label; `0` half use more specific
labels; `-1` none use it. Nodes no tool proposes at all (every high-level
ancestor, e.g. `cell`) are drawn hollow rather than as maximal disagreement.

Encodings: **shape** = expert-curated band (diamond easy to annotate, square
difficult to annotate, circle not curated), **color** = score on a diverging
brown/teal scale, **size** = coverage, so a cell type annotated by a single tool
cannot look like consensus.

Curated bands live in `config/agreement.json` as subtree roots and are inherited
by descendants; a CLID listed explicitly keeps its own band, so aerocyte stays
"easy" even though it sits inside the difficult capillary-endothelial subtree.

## Source filtering

The supertree is built from the **included** `CT/1 - Sources` only. The held-out
names live in `config/reference-lung.json`:

```json
"sources": {
  "exclude": ["(blank)"]
}
```

Blank-source rows carry no attribution, since their assertions cannot be
attributed to any resource. Held-out rows are parsed but contribute no nodes or
edges.

The current `data/ctann-v10.csv` has no blank-source rows, so nothing is held
out: all ten sources build the tree and **every one of the 1,192 rows
contributes**.

Result: **695** cell types, 694 relationships, 559 terminal — from all 1,192
rows.

Because the three comparison tabs are built on this tree (`base:
reference-lung`), the filtering propagates to them automatically; all four graph
views share the same 695-node supertree.

### Source slots

Each node is a fixed-width bar of ten slots, one per included source, in the
order declared by `sources.palette`. A slot is filled in that source's colour
when the source names the cell type *anywhere* in its paths — including as an
ancestor — and left pale when it does not. Slot *position* carries identity, so
colour is reinforcement rather than the only channel.

Membership is stored as a bitmask: with ten sources that is one integer per node
rather than an array of strings. The bars are painted on the pane's overlay
canvas, not as graph elements, so they never enter `successors()`, search, or
hit-testing.

The palette groups the ten sources by modality — five SC-Transcriptomics, five
SC-Spatial Proteomics & SC-Spatial Omics — and carries a display label per
source, so the sidebar table reads like the published CTann tool table rather
than like the CSV's own keys.

### Curated-list overlay

The curated cell-type lists this project validates the tree against are **not
present in this repository at all**, and the tabs that compare them against the
tree live in a separate internal repository. `data/ctann-v10.csv` here carries
only the ten annotation sources; it is checked on every build that no row
attributes itself to one of the curated lists.

Holding them out never changed the tree: those rows were always excluded from
tree construction, so the supertree is the same with or without them.

## Build

One command builds the entire site into `docs/` (served by GitHub Pages):

```bash
python3 build.py
```

No third-party Python dependencies. The output is a static site:

```
docs/
├── index.html          # the whole application (sidebar + tab bar + graph panes)
├── data/<id>.json      # normalized, deduplicated data (fetched on demand)
└── assets/             # shared CSS + JS runtime + per-kind modules
```

Only the active tab's data is fetched, so first paint loads the page plus one
view instead of the whole site. Switching to a tab builds it once and keeps it,
so returning to a tab preserves its zoom, pan, and selection.

## Layout

One document, two columns:

* **Sidebar** (`clamp(240px, 15%, 320px)`) — the site title, then the active
  view's header and description, a search box, and its panels.
* **Main** — a tab bar aligned with the site title band, and below it nothing
  but the graph pane. Legend, status badge, and tooltip float over the canvas.

Each view owns a persistent `.graph-pane`; the sidebar is shared chrome that
swaps to the active view's content.

## Architecture

The build is driven by a **manifest + dependency forest**. Each view declares
two independent inheritance edges:

- `extends` → the **design** cascade parent (deep-merged config; child overrides
  win). Common design lives once in `config/base.json`.
- `base` / `treeData` → the **data** parent. A view with `treeData` is a
  reference-tree data root; a view with `base` overlays that tree by ontology id.

`build.py` topologically sorts the views (parents before children), parses each
reference tree once, resolves each view's design, composes + normalizes its
data, and emits the single application document.

```
site.json           manifest: ordered views, tab titles  (add a tab = one entry)
config/*.json       per-view config: extends / base / treeData / overlay / design
sitegen/            build package
  manifest.py         load manifest, build DAG, topo-sort
  cascade.py          deep-merge design down the extends chain
  reference_tree.py   parse a CTann CSV into the canonical tree (a data root)
  ontology.py         shared id / delimiter helpers
  layout.py           shared layout constants
  overlays.py         read HRApop / HLCA overlays keyed by node id
  normalize.py        intern strings + drop redundant fields (compact JSON)
  render.py           emit the single application document
  views/*.py          per-view data prep (sources / population / hlca / agreement)
                      a "static": true view (the Overview tab) needs none
assets/             shared front-end
  app.js              view lifecycle, pane swapping, Cytoscape, interactions
  view-utils.js       shared helpers
  app.css             layout + component styles
  kinds/*.js          per-view legend / summary / node-detail panels,
                      registered on window.ViewKinds by `kind`
data/               raw CSV inputs
```

### Adding a view / tab

1. Add `config/<id>.json` (`extends` a design parent, `base` a data root, and an
   `overlay` if it annotates the tree).
2. Add a `sitegen/views/<kind>.py` builder (data prep) and register it in
   `sitegen/views/__init__.py`.
3. Add `assets/kinds/<kind>.js` registering on `window.ViewKinds["<kind>"]`
   (legend + panels), unless it reuses an existing kind. A kind that exposes
   `documentHtml` renders a text page instead of a graph — see `doc.js`.
4. Add one entry to `site.json`.

A second reference tree is just another data root (`treeData`) that shares
`config/base.json`; the forest and build order handle it automatically.

## Generative AI usage

All code in this repository — the build pipeline, the front-end, and the four
visualizations — was written using [Claude](https://claude.ai) (Anthropic),
directed and reviewed by the maintainers. Claude is used as a development tool
and is not credited as an author. The datasets, curation decisions (which
sources build the supertree, which cell types are held out, the easy/difficult
cell-type lists), and all scientific interpretation are the maintainers' own.

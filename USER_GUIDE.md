# CTs Supertree — User Guide

How to read the **Reference Supertree** and **HRApop Comparison** views: what
they show, how they are built, what they cannot tell you, and how they are
verified.

*Data: CTann v10 · HRApop v1.1 · lung, single-cell transcriptomics.
Repository: [cns-iu/lung-azimuth-comparison](https://github.com/cns-iu/lung-azimuth-comparison).
Last updated 9 October 2026.*

---

## Contents

- [1. Terminology](#1-terminology)
- [2. Reference Supertree](#2-reference-supertree)
  - [2.1 Dataset](#21-dataset)
  - [2.2 Purpose](#22-purpose)
  - [2.3 How the view is built](#23-how-the-view-is-built)
  - [2.4 Navigating](#24-navigating)
  - [2.5 How to interpret, with examples](#25-how-to-interpret-with-examples)
  - [2.6 Design decisions](#26-design-decisions)
  - [2.7 Test cases](#27-test-cases)
- [3. HRApop Comparison](#3-hrapop-comparison)
  - [3.1 Dataset](#31-dataset)
  - [3.2 Purpose](#32-purpose)
  - [3.3 How the view is built](#33-how-the-view-is-built)
  - [3.4 Navigating](#34-navigating)
  - [3.5 How to interpret, with examples](#35-how-to-interpret-with-examples)
  - [3.6 Design decisions](#36-design-decisions)
  - [3.7 Test cases](#37-test-cases)
- [4. To do: remaining views](#4-to-do-remaining-views)

---

## 1. Terminology

**AS / CT columns** — In `ctann-v10.csv`, `AS/n/ID` and `AS/n/LABEL` hold each
row's chain of cell types from general to specific. `CT/1 - Sources` names the
resource the row came from.

**AS × sex group** — One anatomical structure paired with one donor sex: the
unit HRApop reports in. Lung has 31.

**Azimuth** — A reference-based cell-type annotation tool. In HRApop, the
lung-specific reference.

**CL / CLID** — The Cell Ontology, and an identifier within it (`CL:0000097`).
The shared key that lets different sources and tools be compared.

**CT** — Cell type.

**CT/1 source** — The resource a row in `ctann-v10.csv` came from, e.g.
`celltypist`, `azimuth`, `popv`. All ten build the tree.

**CTann** — Cell-type annotation: the family of tools that assign a cell type to
each cell in a dataset.

**Exact-name match** — Two sources match only when they name the *same* cell
type, not a parent or a child of it. The basis for node colour in the HRApop
Comparison.

**Held-out source** — A source present in the CSV but deliberately excluded from
tree construction, so it can be compared against the tree afterwards.

**HRApop** — The Human Reference Atlas population dataset: cell-type
compositions per anatomical structure, produced by several CTann tools.

**Modality** — The measurement type. Both views use `sc_transcriptomics`
(single-cell RNA).

**Pan-human Azimuth** — The whole-body Azimuth reference, as opposed to the
lung-specific one.

**Primary parent** — When a cell type has more than one parent, the one chosen
to position it on screen. A layout device only; every relationship is kept.

**Supertree** — The merged hierarchy formed by overlaying every included
source's cell-type paths into a single tree.

**Source slot** — One of the ten segments making up every node's bar, each
standing for one included source, in a fixed left-to-right order. Filled means
that source names the cell type somewhere in its paths.

**Terminal cell type** — A cell type that is the last, most specific entry in at
least one source row. 559 of the 695 in this tree. Shown as *Leaf nodes* in the
summary.

**Tool** — A CTann method that produced annotations in HRApop: `azimuth`,
`celltypist`, `frmatch`, `pan-human-azimuth`, `popv`.

---

## 2. Reference Supertree

### 2.1 Dataset

[`data/ctann-v10.csv`](https://github.com/cns-iu/lung-azimuth-comparison/blob/main/data/ctann-v10.csv)
— 1,192 rows. This is CTann v10 **with the two curated-list sources removed**
(see [2.6](#26-design-decisions)); the unmodified file lives in the internal
repository.

Each row describes one cell type's place in a hierarchy, as a chain across
`AS/1/ID` … `AS/12/ID` (with matching `AS/n/LABEL` columns), plus a
`CT/1 - Sources` column naming the resource that asserted it.

**Every one of the 1,192 rows builds the tree**: all ten sources are included
and no row is held out.

The ten sources that build it, grouped by modality as the sidebar lists them:

| | Source | Rows | Cell types |
|---|---|---:|---:|
| **SC-Transcriptomics** | Azimuth | 297 | 418 |
| | CellTypist | 257 | 393 |
| | FR-Match | 51 | 100 |
| | Pan-Human Azimuth | 227 | 353 |
| | popV | 149 | 243 |
| **SC-Spatial Proteomics & SC-Spatial Omics** | CDE Spatial Omics⁺ (`vccf`) | 115 | 169 |
| | DeepCell Types | 26 | 52 |
| | DeepCell Types-HuBMAP | 36 | 65 |
| | RIBCA | 14 | 32 |
| | STELLAR | 20 | 55 |

*Cell types* counts every node that source names anywhere in a path, so the
column sums well past 695: that overlap is what the view is for.

### 2.2 Purpose

Assemble one cell-type hierarchy from ten annotation resources and make it
navigable: what each resource asserts, where a cell type sits, and which
resources agree on naming it.

It answers: *when we merge what these resources say, what hierarchy results?*

Every node carries its own provenance: the ten-slot bar says which sources name
that cell type. Tabs 2–4 supply the tool comparisons; this is the base tree they
are all drawn on.

It does **not** judge whether any resource is correct, and it says nothing about
how many cells exist of any type.

### 2.3 How the view is built

**Each row is a path, not a single cell type.** A row lists a chain from general
to specific — for example *cell → hematopoietic cell → leukocyte → macrophage*.
Every entry becomes a node; every consecutive pair becomes a parent→child
relationship. Merging all rows from all included sources produces the supertree.

**Position.** Horizontal position is **depth**: Vertical
position groups siblings under their parent, so each branch reads as a block.

**Terminal cell type.** A cell type that is the *last* entry in at least one row
— the most specific thing that row asserts. 

**One parent for layout.** A cell type may legitimately have several parents. The
tree keeps every relationship but picks one *primary parent* to position each
node; additional relationships draw as dashed lines. With the current ten
sources there are **no multi-parent cell types**, so every relationship shown is
a primary one.

**Source slots.** Every node is drawn as a fixed-width bar of ten slots, one per
included source, always in the same left-to-right order: the five
SC-Transcriptomics sources first, then the five SC-Spatial ones. A slot is
filled in that source's colour when the source names the cell type *anywhere* in
its paths — including as an ancestor it merely passes through — and left pale
when it does not.

Because slot *position* is fixed, position identifies the source and colour only
reinforces it. That is what lets the palette carry ten hues without the bars
becoming unreadable.

The bars appear as you zoom in. At the fitted view ten slots cannot be told
apart, so each node is drawn as a single mark instead.

**Result:** 695 cell types, 694 relationships, one root, 559 terminal cell types.

### 2.4 Navigating

| Action | Result |
|---|---|
| **Hover** a node | Traces its path to the root (solid) and every branch beneath it (dotted) |
| **Click** a node | Fills the details panel: ontology ID, depth, parents, children, and the sources that name it |
| **Click** empty space | Clears the selection |
| **Search** (sidebar) | Matches label, ontology ID, or source name; matches ring violet, everything else dims |
| **Esc** in the search box | Clears the search and refits the graph |

**Minimap** (top-right of the graph):

| Action | Result |
|---|---|
| Drag the blue box | Pan — the box marks your current viewport |
| Drag anywhere else | Draw a rectangle to zoom into it |
| Click | Centre the view there, keeping zoom |
| Double-click, or the ↺ button | Reset to the whole tree |

At full zoom-out the blue box fills the minimap, so every drag draws a zoom
rectangle instead of panning. 

### 2.5 How to interpret, with examples

Three channels carry meaning:

- **Column** = depth. Everything the same number of steps from the root shares a
  column, so generality reads left-to-right.
- **Block** = branch. Siblings are grouped under their parent, so a subtree reads
  as a contiguous band.
- **Bar** = provenance. How many slots are filled says how widely the cell type
  is recognised; *which* slots are filled says by whom. Because the five
  transcriptomics sources occupy the left half of every bar and the five spatial
  sources the right half, a bar that is solid on one side and pale on the other
  is a cell type one modality sees and the other does not.

Hover traces the path to the root (solid) and everything beneath it (dotted).
Click opens the full provenance: every source that names it, its parents and
children, and its label variants.

**Example — pulmonary alveolar type 2 cell (`CL:0002063`).** Search for it, then
zoom in until the bar resolves. Six of ten slots are filled: all five
transcriptomics sources plus CDE Spatial Omics⁺, with DeepCell Types, DeepCell
Types-HuBMAP, RIBCA and STELLAR pale. The bar is solid on the left and almost
empty on the right — an alveolar epithelial cell type the transcriptomics
references all name and the spatial-proteomics panels largely do not.

**Example — macrophage (`CL:0000235`).** All ten slots filled: every source names
it somewhere. Compare with **mast cell (`CL:0000097`)**, where eight are filled
and only RIBCA and STELLAR are pale.

**Example — how rare consensus is.** Only **26** of the 695 cell types are named
by all ten sources, while **296** — over two in five — are named by exactly one.
A full bar is the exception, not the norm, which is the main thing this view has
to say about how much these ten resources actually share.

### 2.6 Design decisions

**The curated-list sources are absent from the CSV entirely.** Their rows, and
the tabs that compare them against the tree, live in a separate internal
repository — this repository carries neither. `data/ctann-v10.csv` here holds
only the ten annotation sources, and no row attributes itself to a curated list.

The tree would be unaffected either way, because those rows were always held out
of tree construction. Their names stay listed in the `exclude` array even though
they now match nothing, so that a future data drop cannot quietly build them in.

**`vccf` is a single source in v10.** CTann v9 carried both `vccf` and
`vccf-expert-slim-hierarchy` and this view had to choose between them; v10 ships
one consolidated `vccf` (113 rows, 166 cell types), so the choice no longer
arises and nothing is dropped on its account. It is shown as **CDE Spatial
Omics⁺**.

**Rows with a blank source would be dropped,** since their assertions cannot be
attributed to any resource. The current file has none, so nothing is held out
and the sidebar shows no *Excluded* block.

**Sources are shown under display names, grouped by modality.** The sidebar table
and the legend read `Pan-Human Azimuth` and `CDE Spatial Omics⁺` rather than the
CSV's `pan-human-azimuth` and `vccf`, and are split into SC-Transcriptomics and
SC-Spatial, so the list matches the published CTann tool table. The mapping lives
in `sources.palette`; the CSV keys are untouched, and the details panel still
shows them verbatim.

**Where this is configured:** [`config/reference-lung.json`](https://github.com/cns-iu/lung-azimuth-comparison/blob/main/config/reference-lung.json)
→ `sources`. Changing a source filter changes the tree for **every** view, since
all views are built on it.

### 2.7 Test cases

| Test | Asserts | Status |
|---|---|---|
| **Tree structure** | `nodes == edges + roots`; no cell type has more than one parent; exactly one root | ✅ Passing — 695 = 694 + 1, 0 multi-parent nodes, 1 root |
| **Parity with the internal build** | This tab and the Reference Supertree tab of `hra-supertree-internal` render the same tree from the same rows | ⚠️ Last verified 7 Oct 2026 on the previous CSV (694/694 nodes identical, pixel-identical render). Re-verify after the 9 Oct data drop — the internal repository is still on the older file. |
| **Expert review** | A domain expert confirms the cell types and their placement in the hierarchy are biologically correct | ⏳ **Pending** |

**Expert review record**

| Reviewer | Date | Data version | Scope reviewed | Findings | Status |
|---|---|---|---|---|---|
| — | — | CTann v10 | — | — | ⏳ Pending |

---

## 3. HRApop Comparison

### 3.1 Dataset

[`data/cell-types-in-anatomical-structurescts-per-as.csv`](https://github.com/cns-iu/lung-azimuth-comparison/blob/main/data/cell-types-in-anatomical-structurescts-per-as.csv)
— 3.4 MB.

Filtered to:

| Filter | Value |
|---|---|
| Organ | `lung` |
| Modality | `sc_transcriptomics` |
| Tools | `azimuth`, `pan-human-azimuth` |

That leaves **2,392 rows** spanning **31 anatomical-structure × sex groups**.
Both tools report in all 31 groups, so a tool never naming a cell type is a real
absence rather than missing data.

### 3.2 Purpose

Show which cell types **Azimuth** and **Pan-human Azimuth** actually output for
lung tissue, drawn on the same hierarchy as [section 2](#2-reference-supertree).

It answers: *which cell types does each tool name, where do they agree, and where
does one tool name something the other never does?*

It compares **labels, not biology**, and reflects presence only — not how many
cells were assigned.

### 3.3 How the view is built

**The tree is inherited unchanged** from [2.3](#23-how-the-view-is-built) — same
695 cell types in the same positions, so a cell type sits in the same place in
both views.

**The overlay joins on CLID.** Each HRApop row names a cell type by ontology ID;
that ID is matched against the tree. Matching is on the exact identifier, not on
ancestors or descendants.

**Counts are pooled across all 31 groups.** A tool "outputs" a cell type if it
names it in at least one AS × sex group. A cell type reported in one group and
one reported in all 31 are treated identically.

**Each node also carries subtree tallies:** how many cell types beneath it each
tool outputs. These are what distinguish a real disagreement from a difference in
naming granularity — see [3.5](#35-how-to-interpret-with-examples).

### 3.4 Navigating

| Action | Result |
|---|---|
| **Hover** a node | Traces its path to the root (solid) and every branch beneath it (dotted), and shows how many labels each tool used for this cell type |
| **Click** a node | Fills the details panel: the labels each tool used, and the subtree tallies you need for interpretation |
| **Click** empty space | Clears the selection |
| **Search** (sidebar) | Matches label, ontology ID, or source name; matches ring violet, everything else dims |
| **Esc** in the search box | Clears the search and refits the graph |

**Minimap** (top-right of the graph):

| Action | Result |
|---|---|
| Drag the blue box | Pan — the box marks your current viewport |
| Drag anywhere else | Draw a rectangle to zoom into it |
| Click | Centre the view there, keeping zoom |
| Double-click, or the ↺ button | Reset to the whole tree |

At full zoom-out the blue box fills the minimap, so every drag draws a zoom
rectangle instead of panning. The cursor tells you which you will get: a grab
hand over the box, crosshairs elsewhere.

**The details panel** shows *Reference Supertree Label* (the tree's own name for
the cell type), then **Tool outputs** — each method with its label count and the
labels themselves — then the subtree tallies.

### 3.5 How to interpret, with examples

**Node colour**

| Colour | Meaning | Nodes |
|---|---|---:|
| 🟣 Purple | Both tools output this exact cell type | 12 |
| 🔴 Red | Azimuth only | 35 |
| 🔵 Blue | Pan-human Azimuth only | 75 |
| ⚪ Grey | Neither tool outputs it directly | 534 |

Coloured nodes are drawn larger. Colour reflects the **exact** cell type: a tool
counts only if it names *that* cell type, not a broader or narrower one.

**Label rays**

Short bars radiate from every coloured node — **one ray per label**. Azimuth's
rays fan to the **right**, Pan-human Azimuth's to the **left**, on single-tool
nodes as well as shared ones, so a node's fan direction tells you which tool
split it before you read the colour.

Rays exist because **one CLID can carry several labels from one tool**: a tool
often resolves a population more finely than the ontology term it maps to. A
node is therefore a cell type *identifier*, not necessarily a single population.
See [3.6](#36-design-decisions) for how common this is.

Hover a node for the cell type label counts; click it for the labels themselves.

**Examples**

*Mast cell (`CL:0000097`) — clean agreement.* Purple, one ray each side. Both
tools name it, it has no descendants, and both subtree counts are 1. Nothing is
hidden beneath it.

*Brush cell of tracheobronchial tree (`CL:0002075`) — a genuine difference.* Red,
one ray to the right. Azimuth names it, Pan-human Azimuth does not, and it has no
descendants — so Pan-human Azimuth is not using a more specific label instead. A real
disagreement.

*Fibroblast (`CL:0000057`) — one node, five populations.* Blue with **five rays
fanning left**: Pan-human Azimuth reports five marker-defined fibroblast
populations — CFD+MGP+, G0S2+PPP1R14A+, IGFBP6+APOD+, POSTN, and SCN7A — all
mapped onto the single generic `fibroblast` term. Treating this node as one
population would be wrong.

*Macrophage (`CL:0000235`) — looks like disagreement, is not.* Blue, so only
Pan-human Azimuth outputs "macrophage". But the details panel reads
**Azimuth 5, Pan-human 6** in the subtree: Azimuth names five macrophage subtypes
beneath this node without ever using the parent label. Both tools see
macrophages; they disagree about *how specifically to name them*.

> **The habit to build:** before calling a red or blue node a disagreement,
> check the subtree counts in the details panel.

### 3.6 Design decisions

**Only two of the five available tools.** HRApop's lung transcriptomics data
carries five CTann tools (`azimuth`, `celltypist`, `frmatch`,
`pan-human-azimuth`, `popv`). This view compares the lung-specific Azimuth
reference against the whole-body one; the other three are out of scope here.

**Only sc_trascriptomics rows are included.** HRApop's `sc_proteomics` rows are excluded and only `sc_transcriptomics` is used. 

**Matching is on the exact CLID, not ancestors.** A tool counts at a node only if
it names that cell type.

**One CLID can carry several labels.** Tools resolve populations more finely
than the Cell Ontology terms they map to, so several distinct labels can land on
one identifier. Across the 132 cell types in this view:

| Labels per CLID | Azimuth | Pan-human Azimuth |
|---:|---:|---:|
| 1 | 45 | 89 |
| 2 | 4 | 4 |
| 3 | 0 | 1 |
| 5 | 0 | 1 |
| **Total** | **49** | **95** |

Case and whitespace normalisation collapses none of these — they are genuinely
distinct labels. The two tools also collapse differently: Azimuth merges
**anatomical** distinctions (nasal vs non-nasal club cells; pulmonary vs systemic
venous EC), while Pan-human Azimuth merges **marker-defined subpopulations and
cell states** (five fibroblast populations; three erythroblast maturation stages;
G2/M vs S phase myeloid cells). Rays surface the count; the details panel lists
the labels.

**Counts are pooled, not per-structure.** A cell type named in 1 of 31 groups
looks identical to one named in all 31. Neither the colour nor the summary
breaks down by anatomical structure or sex.

**Ten cell types cannot be drawn.** The two tools produce 132 distinct cell types
for lung; **122** exist in the tree and **10 do not**, so they appear as no node.
They are listed in the sidebar under *Outside the Reference Supertree*. Among
them are cell types Pan-human Azimuth reports in lung that look non-pulmonary,
such as hippocampal neurons.

**Two summary figures count more than the graph draws.** The KPIs read
Azimuth-only **37** and Pan-human-only **83**, while only **35** and **75** nodes
are drawn. The difference is exactly the 10 undrawable cell types (2 Azimuth,
8 Pan-human): the KPIs count cell types, the graph draws tree nodes.

**Where this is configured:** [`config/population.json`](https://github.com/cns-iu/lung-azimuth-comparison/blob/main/config/population.json)
→ `overlay`.

### 3.7 Test cases

| Test | Asserts | Status |
|---|---|---|
| **Expert review** | A domain expert confirms that the visual encoding provide data provenance and meaningful insights | ⏳ **Pending** |

**Expert review record**

| Reviewer | Date | Data version | Scope reviewed | Findings | Status |
|---|---|---|---|---|---|
| — | — | HRApop v1.1 | — | — | ⏳ Pending |

---

## 4. To do: remaining views

Two further views are live in the application but not yet documented here.

| View | State | Documentation blocked on |
|---|---|---|
| **HLCA Node Comparison** (tab 3) | Complete — filter-scoped fill, the comparison ring, and author-label projection are all restored | Documentation only |
| **Tool Agreement** (tab 4) | Complete and in use | Confirm the curated easy/difficult cell-type lists, then document using the same seven sub-sections as sections 2 and 3 |

Both should follow the structure used above: Dataset · Purpose · How the view is
built · Navigating · How to interpret · Design decisions · Test cases.

# CTs SuperTree — User Guide

How to read the **Reference SuperTree** and **HRApop Comparison** views: what
they show, how they are built, what they cannot tell you, and how they are
verified.

*Data: CTann v9 · HRApop v1.1 · lung, single-cell transcriptomics.
Repository: [cns-iu/lung-azimuth-comparison](https://github.com/cns-iu/lung-azimuth-comparison).
Last updated 26 August 2026.*

---

## Contents

- [1. Terminology](#1-terminology)
- [2. Reference SuperTree](#2-reference-supertree)
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

**AS / CT columns** — In `ctann-v9.csv`, `AS/n/ID` and `AS/n/LABEL` hold each
row's chain of cell types from general to specific. `CT/1 - Sources` names the
resource the row came from.

**AS × sex group** — One anatomical structure paired with one donor sex: the
unit HRApop reports in. Lung has 31.

**Azimuth** — A reference-based cell-type annotation tool. In HRApop, the
lung-specific reference.

**CL / CLID** — The Cell Ontology, and an identifier within it (`CL:0000097`).
The shared key that lets different sources and tools be compared.

**CT** — Cell type.

**CT/1 source** — The resource a row in `ctann-v9.csv` came from, e.g.
`celltypist`, `azimuth`, `popv`. Ten build the tree; two are held out.

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

**Terminal cell type** — A cell type that is the last, most specific entry in at
least one source row. 510 of the 656 in this tree.

**Tool** — A CTann method that produced annotations in HRApop: `azimuth`,
`celltypist`, `frmatch`, `pan-human-azimuth`, `popv`.

---

## 2. Reference SuperTree

### 2.1 Dataset

[`data/ctann-v9.csv`](https://github.com/cns-iu/lung-azimuth-comparison/blob/main/data/ctann-v9.csv)
— 1,424 rows. This is CTann v9 **with two sources removed** (see
[2.6](#26-design-decisions)); the unmodified file lives in the internal
repository.

Each row describes one cell type's place in a hierarchy, as a chain across
`AS/1/ID` … `AS/12/ID` (with matching `AS/n/LABEL` columns), plus a
`CT/1 - Sources` column naming the resource that asserted it.

Of the 1,424 rows, **1,304 build the tree** and **120 are held out** (see
[2.6](#26-design-decisions)).

### 2.2 Purpose

Assemble one cell-type hierarchy from ten annotation resources and make it
navigable: what each resource asserts, where a cell type sits, and which
resources agree on naming it.

It answers: *when we merge what these resources say, what hierarchy results?*

This view carries **no overlay** — every node is drawn the same. Tabs 2–4 supply
the comparisons; this is the base tree they are all drawn on.

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

**Result:** 656 cell types, 655 relationships, one root, 510 terminal cell types.

### 2.4 Navigating

| Action | Result |
|---|---|
| **Hover** a node | Traces its path to the root (solid) and every branch beneath it (dotted) |
| **Click** a node | Fills the details panel: ontology ID, depth, parents, children, which sources use it, and which treat it as terminal |
| **Click** empty space | Clears the selection |
| **Search** (sidebar) | Matches label, ontology ID, or source name; matches ring green, everything else dims |
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

**There is no colour encoding.** Every cell type is drawn in the same neutral
grey, so position and connection carry the meaning, not fill. Reading the tree
is therefore about *where* a cell type sits and *who asserts it*:

- **Column** = depth. Everything the same number of steps from the root shares a
  column, so generality reads left-to-right.
- **Block** = branch. Siblings are grouped under their parent, so a subtree reads
  as a contiguous band.
- **Hover** traces the path to the root (solid) and everything beneath it
  (dotted) — the fastest way to see what a cell type generalises to.
- **Click** opens provenance: which sources name it anywhere in a path, and which
  treat it as terminal.

**Example — mast cell (`CL:0000097`).** Search for it, then click. The panel
shows depth, its parents and children, its primary path to the root, and the
sources that name it. *Is terminal in rows from* tells you which resources treat
it as a most-specific cell type rather than a step on the way to one — the
distinction behind the 510 terminal cell types in the summary.

**Example — an intermediate node.** Click something high in the tree, e.g.
`cell`. Its *Is terminal in rows from* list is empty: no resource ends a row
there. That is what separates the 510 terminal cell types from the other 146.

### 2.6 Design decisions

**Two curated-list sources were removed from the CSV entirely.** Their rows,
and the validation overlay that compared them against the tree, live in a
separate internal repository — this repository carries neither. The file here is
CTann v9 with every row whose `CT/1 - Sources` was one of those two sources
dropped: **1,700 → 1,424 rows**, 276 removed. The tree is unaffected, because
those rows were already held out of tree construction: the same **1,304** rows
build it either way, giving the same 656 cell types.

**`vccf` is dropped in favour of `vccf-expert-slim-hierarchy`.** The two overlap
almost entirely, and `vccf-expert-slim-hierarchy` is the expert-curated form:

| | Rows | Distinct CTs | Terminal CTs |
|---|---:|---:|---:|
| `vccf` | 118 | 169 | 115 |
| `vccf-expert-slim-hierarchy` | 304 | 163 | 104 |

Every one of the slim hierarchy's 163 cell types also appears in `vccf`; the
slim form uses 2.6× as many rows to express them, meaning it encodes more
explicit hierarchy paths over the same vocabulary. `vccf` adds 6 cell types, of
which 4 arrive via other sources anyway — so dropping it costs the tree exactly
**two** cell types: `CL:0000442` (follicular dendritic cell) and `CL:0002329`
(basal epithelial cell of tracheobronchial tree).
> ⚠️ **Needs verification.** Confirm the slim hierarchy is intended to supersede
> `vccf`.

**Rows with a blank source are dropped.** Two rows carry no `CT/1 - Sources`
value, so their assertions cannot be attributed to any resource.

**Where this is configured:** [`config/reference-lung.json`](https://github.com/cns-iu/lung-azimuth-comparison/blob/main/config/reference-lung.json)
→ `sources`. Changing a source filter changes the tree for **every** view, since
all views are built on it.

### 2.7 Test cases

| Test | Asserts | Status |
|---|---|---|
| **Tree structure** | `nodes == edges + roots`; no cell type has more than one parent; exactly one root | ✅ Passing — 656 = 655 + 1, 0 multi-parent nodes, 1 root |
| **Expert review** | A domain expert confirms the cell types and their placement in the hierarchy are biologically correct | ⏳ **Pending** |

**Expert review record**

| Reviewer | Date | Data version | Scope reviewed | Findings | Status |
|---|---|---|---|---|---|
| — | — | CTann v9 | — | — | ⏳ Pending |

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
656 cell types in the same positions, so a cell type sits in the same place in
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
| **Search** (sidebar) | Matches label, ontology ID, or source name; matches ring green, everything else dims |
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

**The details panel** shows *Reference SuperTree Label* (the tree's own name for
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

Hover a node for the label counts; click it for the labels themselves.

**Examples**

*Mast cell (`CL:0000097`) — clean agreement.* Purple, one ray each side. Both
tools name it, it has no descendants, and both subtree counts are 1. Nothing is
hidden beneath it.

*Brush cell of tracheobronchial tree (`CL:0002075`) — a genuine difference.* Red,
one ray to the right. Azimuth names it, Pan-human Azimuth does not, and it has no
descendants — so Pan-human Azimuth is not using a finer label instead. A real
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
They are listed in the sidebar under *Outside the Reference SuperTree*. Among
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

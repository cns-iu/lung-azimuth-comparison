/* HLCA exact-node comparison view.
 *
 * Filter-scoped, as in the original standalone build. Three encodings:
 *
 *   node fill  — which method assigns this exact CLID *in the current scope*
 *                (sex and author-label filters), recomputed client-side
 *   size       — the CLID occurs somewhere in the matched-partition
 *                comparison. Global and deliberately filter-independent, so a
 *                node can read "in the comparison, but empty in this scope"
 *   opacity    — author-label projection: selecting one author label raises the
 *                exact CLIDs its cells were assigned to, plus the path back to
 *                the root, and leaves the rest faint but drawn and interactive
 */
(function () {
  "use strict";
  const { formatNumber, escapeHtml } = window.ViewUtil;

  const ALL = "all";

  const indexOf = (summary) => (summary && summary.filterIndex) || { sexes: [], labels: [], clids: [], rows: [] };
  const sexOf = (filters) => (filters && filters.sex) || ALL;
  const authorOf = (filters) => (filters && filters.author) || ALL;

  /* Grey means two different things, and the panel says which. A cell type the
     comparison never covered is simply not in it. One that IS in the comparison
     but drew no assignments under the current Sex / Author label is a scope
     result, not an exclusion — calling that "not included" would contradict the
     Comparison row directly beneath it. At full scope every one of the 115
     comparison nodes is colored, so the second case only arises while filtering. */
  function statusText(status, ctx, data) {
    if (status === "azimuth_only") return "Azimuth only";
    if (status === "pan_only") return "Pan-human Azimuth only";
    if (status === "shared") return "Exact CT ID in both";
    return data && data.isComparison
      ? "No direct output in current scope"
      : "Not included in comparison";
  }

  function statusFromCounts(azimuth, pan) {
    if (azimuth > 0 && pan > 0) return "shared";
    if (azimuth > 0) return "azimuth_only";
    if (pan > 0) return "pan_only";
    return "neutral";
  }

  /* Aggregate the index under the active filters, returning per-CLID totals
     plus the cohort tally used for the scope line. */
  function aggregate(summary, filters) {
    const idx = indexOf(summary);
    const sex = sexOf(filters);
    const author = authorOf(filters);
    const sexI = sex === ALL ? -1 : idx.sexes.indexOf(sex);
    const authI = author === ALL ? -1 : idx.labels.indexOf(author);

    const byClid = new Map();
    const cohorts = new Map();
    for (const r of idx.rows) {
      if (sexI >= 0 && r[0] !== sexI) continue;
      if (authI >= 0 && r[1] !== authI) continue;
      cohorts.set(r[0] + "\u0000" + r[1], r[9]);
      let a = byClid.get(r[2]);
      if (!a) { a = { az: 0, pan: 0, both: 0, azOnly: 0, panOnly: 0, union: 0 }; byClid.set(r[2], a); }
      a.az += r[3]; a.pan += r[4]; a.both += r[5];
      a.azOnly += r[6]; a.panOnly += r[7]; a.union += r[8];
    }
    let cells = 0;
    cohorts.forEach((v) => { cells += v; });
    return { byClid, cohortCount: cohorts.size, cohortCells: cells, idx };
  }

  function scopeText(summary, filters) {
    const sex = sexOf(filters), author = authorOf(filters);
    const parts = [];
    parts.push(sex === ALL ? "All sexes" : sex);
    parts.push(author === ALL ? "all author labels" : `“${author}”`);
    return parts.join(" · ");
  }

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["hlca"] = {
    statusText,

    minimapColors(colors) {
      return {
        shared: colors.shared || "#7B1FA2",
        azimuth_only: colors.azimuth_only || "#E53935",
        pan_only: colors.pan_only || "#1565C0",
        neutral: colors.neutral || "#8A8F98",
      };
    },

    statusStyles(colors) {
      const neutral = colors.neutral || "#8A8F98";
      const fill = (s) => ({
        selector: `node.scope-${s}`,
        style: { "background-color": colors[s] || neutral },
      });
      return [
        { selector: "node[isComparison = 1]", style: {
            "width": 28, "height": 28, "font-weight": 700,
            "z-index-compare": "manual", "z-index": 30 } },
        { selector: "node[isComparison = 0]", style: { "width": 14, "height": 14 } },
        fill("shared"), fill("azimuth_only"), fill("pan_only"),
        { selector: "node.scope-neutral", style: { "background-color": neutral } },
        /* Two tiers, matching what a text search does in the other tabs: the
           context (destinations plus the path back to the root) at full
           strength, and everything else faint but still drawn — so the tree's
           shape survives and every node stays hoverable and clickable.
           There is no middle "partially faded" tier. */
        { selector: ".projectionDestination", style: { "opacity": 1, "text-opacity": 1 } },
        { selector: ".projectionAncestor", style: { "opacity": 1, "text-opacity": 1 } },
        { selector: ".projectionMuted", style: { "opacity": 0.1, "text-opacity": 0.03 } },
        { selector: "edge.projectionEdge", style: { "line-color": "#6B7280", "width": 1.35, "opacity": 0.55 } },
        { selector: "edge.projectionMutedEdge", style: { "opacity": 0.045 } },
      ];
    },

    // ---- scope controls -----------------------------------------------------
    controlsHtml(config, summary, filters) {
      const idx = indexOf(summary);
      const sex = sexOf(filters), author = authorOf(filters);
      const opt = (value, label, current) =>
        `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}>${escapeHtml(label)}</option>`;
      const sexOpts = [opt(ALL, "All sexes", sex)]
        .concat(idx.sexes.map((s) => opt(s, s, sex))).join("");
      const authorOpts = [opt(ALL, `All author labels (${idx.labels.length})`, author)]
        .concat(idx.labels.map((l) => opt(l, l, author))).join("");
      const agg = aggregate(summary, filters);
      /* Only worth a line while an author label is projected, where it says what
         the projection resolved to. With no projection the tally restated what
         the summary card already shows. */
      const note = author === ALL
        ? ""
        : `Projecting “${escapeHtml(author)}” · ${formatNumber(agg.byClid.size)} destination CLIDs`;
      return `
        <div class="filter-field">
          <label for="hlcaSex">Sex</label>
          <select id="hlcaSex">${sexOpts}</select>
        </div>
        <div class="filter-field">
          <label for="hlcaAuthor">Author label</label>
          <select id="hlcaAuthor">${authorOpts}</select>
        </div>
        ${note ? `<div class="filter-note">${note}</div>` : ""}`;
    },

    bindControls(root, config, summary, filters, onChange) {
      const sexEl = root.querySelector("#hlcaSex");
      const authEl = root.querySelector("#hlcaAuthor");
      if (sexEl) sexEl.addEventListener("change", () => { filters.sex = sexEl.value; onChange(); });
      if (authEl) authEl.addEventListener("change", () => { filters.author = authEl.value; onChange(); });
    },

    // ---- recolor + project --------------------------------------------------
    applyFilters(cy, config, summary, filters) {
      const { byClid, idx } = aggregate(summary, filters);
      const author = authorOf(filters);
      const projecting = author !== ALL;

      // clid string -> totals, for direct lookup by node id
      const totals = new Map();
      byClid.forEach((v, clidIndex) => totals.set(idx.clids[clidIndex], v));

      cy.batch(() => {
        cy.elements().removeClass(
          "scope-shared scope-azimuth_only scope-pan_only scope-neutral " +
          "projectionDestination projectionAncestor projectionMuted");
        cy.edges().removeClass("projectionEdge projectionMutedEdge");

        cy.nodes().forEach((node) => {
          if (node.data("label") === undefined) return; // ring
          const t = totals.get(node.id());
          const status = t ? statusFromCounts(t.az, t.pan) : "neutral";
          node.data("status", status);
          node.addClass("scope-" + status);
        });

        if (!projecting) return;

        // Destinations: CLIDs this author label actually lands on, in the tree.
        const destinations = new Set();
        totals.forEach((t, clid) => {
          if (t.az > 0 || t.pan > 0) {
            const n = cy.getElementById(clid);
            if (n && n.nonempty()) destinations.add(clid);
          }
        });

        /* The path from the root down to each destination is kept, exactly as
           search keeps predecessors(), so a destination is never a dot floating
           with no hierarchy around it. */
        const ancestors = new Set();
        const pathEdges = new Set();
        destinations.forEach((clid) => {
          const path = cy.getElementById(clid).data("primaryPathIds") || [];
          path.forEach((id) => ancestors.add(id));
          for (let i = 1; i < path.length; i += 1) {
            pathEdges.add(path[i - 1] + "\u0000" + path[i]);
          }
        });
        destinations.forEach((clid) => ancestors.delete(clid));

        cy.nodes().forEach((node) => {
          const id = node.data("logicalId") || node.id();
          node.addClass(
            destinations.has(id) ? "projectionDestination"
            : ancestors.has(id) ? "projectionAncestor"
            : "projectionMuted"
          );
        });
        cy.edges().forEach((edge) => {
          const key = edge.data("source") + "\u0000" + edge.data("target");
          edge.addClass(pathEdges.has(key) ? "projectionEdge" : "projectionMutedEdge");
        });
      });

      /* No badge: the scope it restated is already on screen in the sidebar
         filters and the summary card, and it sat over the graph. The badge is
         left to answer searches, as on every other tab. */
    },

    legendHtml(config) {
      const c = (config.design && config.design.colors) || {};
      /* Each key names its own color or size before the meaning, so the legend
         reads without relying on the swatch alone. */
      const key = (mark, name, text) =>
        `<div class="legend-row">${mark}<span><b>${name}:</b> ${escapeHtml(text)}</span></div>`;
      const dot = (color) => `<span class="dot" style="background:${color}"></span>`;
      return `
        <div class="legend-title">Node fill — current filter scope</div>
        ${key(dot(c.azimuth_only || "#E53935"), "Red", "Azimuth only")}
        ${key(dot(c.pan_only || "#1565C0"), "Blue", "Pan-human Azimuth only")}
        ${key(dot(c.shared || "#7B1FA2"), "Purple", "Exact cell-type ID identified by both methods")}
        ${key(dot(c.neutral || "#8A8F98"), "Gray", "No direct prediction within the current filter scope")}
        <div class="legend-subhead">Node size</div>
        ${key('<span class="swatch size-big"></span>', "Large", "Cell type predicted by at least one method")}
        ${key('<span class="swatch size-small"></span>', "Small", "Supertree node with no prediction from either method")}
        <div class="legend-note">Node size indicates whether a cell type was predicted by either method. Node fill shows which method(s) predicted the cell type for the currently selected sex and author label.</div>`;
    },

    summaryHtml(summary, ctx) {
      const c = (ctx && ctx.design && ctx.design.colors) || {};
      /* Status colors, in text-safe form. The red node fill only reaches 3.9:1
         on the KPI tint, so panel type gets a darkened variant of the same hue;
         the nodes keep their own. Mirrors the HRApop tab. */
      const tint = {
        azimuth_only: "#D32F2F",
        pan_only: c.pan_only || "#1565C0",
        shared: c.shared || "#7B1FA2",
      };
      const kpi = (value, label, status) => {
        const style = status ? ` style="color:${tint[status]}"` : "";
        return `<div class="kpi">
          <div class="kpi-value"${style}>${formatNumber(value)}</div>
          <div class="kpi-label"${style}>${label}</div>
        </div>`;
      };

      /* Comparison CLIDs the supertree has no node for. Empty in the current
         data, so nothing renders; kept so a future drop cannot lose them
         silently. Titled like the same card on the HRApop tab. */
      const outside = (summary.outsideTree || [])
        .map((id) => `<tr><td class="mono">${escapeHtml(id)}</td></tr>`).join("");

      return `
        <div class="card">
          <div class="card-title">Comparison summary</div>
          <div class="kpi-grid">
            ${kpi(summary.azimuthOnlyCount, "Azimuth only", "azimuth_only")}
            ${kpi(summary.panOnlyCount, "Pan-human Azimuth only", "pan_only")}
            ${kpi(summary.sharedCount, "Both methods", "shared")}
            ${kpi(summary.comparisonNodeCount, "Compared CLIDs")}
          </div>
        </div>
        ${outside ? `<div class="card">
          <div class="card-title with-count">
            <span>Not represented in tree</span>
            <span class="title-count">${formatNumber(summary.outsideTreeCount)}</span>
          </div>
          <div class="scroll-box short"><table class="panel-table nowrap"><tbody>${outside}</tbody></table></div>
        </div>` : ""}`;
    },

    nodeDetailsHtml(data, ctx) {
      const summary = (ctx && ctx.summary) || {};
      const filters = (ctx && ctx.filters) || {};
      const { byClid, idx } = aggregate(summary, filters);
      let t = null;
      const ci = idx.clids.indexOf(data.id);
      if (ci >= 0 && byClid.has(ci)) t = byClid.get(ci);
      const c = (ctx && ctx.design && ctx.design.colors) || {};
      const status = t ? statusFromCounts(t.az, t.pan) : "neutral";
      const swatch = c[status] || c.neutral || "#8A8F98";

      const counts = t ? `
        <div class="card">
          <div class="card-title">Exact-node cell assignments</div>
          <div class="subcard-label">${escapeHtml(scopeText(summary, filters))}</div>
          <div class="detail-grid">
            <div class="detail-key">Azimuth cells</div><div class="detail-value">${formatNumber(t.az)}</div>
            <div class="detail-key">Pan-human cells</div><div class="detail-value">${formatNumber(t.pan)}</div>
            <div class="detail-key">Both agree</div><div class="detail-value">${formatNumber(t.both)}</div>
            <div class="detail-key">Azimuth only</div><div class="detail-value">${formatNumber(t.azOnly)}</div>
            <div class="detail-key">Pan-human Azimuth only</div><div class="detail-value">${formatNumber(t.panOnly)}</div>
            <div class="detail-key">Union</div><div class="detail-value">${formatNumber(t.union)}</div>
          </div>
        </div>`
        : `<div class="card"><div class="card-title">Exact-node cell assignments</div>
             <div class="empty-state">${data.isComparison
               ? "In the comparison globally, but no rows match the current scope."
               : "This node is not part of the comparison."}</div></div>`;

      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
            <div class="detail-key">Ontology ID</div><div class="detail-value">${escapeHtml(data.id)}</div>
            <div class="detail-key">Scope status</div>
            <div class="detail-value"><span class="dot" style="display:inline-block;vertical-align:middle;background:${swatch}"></span> ${escapeHtml(statusText(status, ctx, data))}</div>
            <div class="detail-key">Comparison</div><div class="detail-value">${data.isComparison ? "Included in comparison" : "Not in the comparison"}</div>
            <div class="detail-key">Depth</div><div class="detail-value">${formatNumber(data.depth)}</div>
          </div>
          <div class="path-box"><strong>Reference Supertree Path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>
        ${counts}`;
    },
  };
})();

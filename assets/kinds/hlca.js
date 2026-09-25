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
  const { formatNumber, escapeHtml, listText } = window.ViewUtil;

  const ALL = "all";

  const indexOf = (summary) => (summary && summary.filterIndex) || { sexes: [], labels: [], clids: [], rows: [] };
  const sexOf = (filters) => (filters && filters.sex) || ALL;
  const authorOf = (filters) => (filters && filters.author) || ALL;

  function statusText(status) {
    if (status === "azimuth_only") return "Azimuth only";
    if (status === "pan_only") return "Pan-human Azimuth only";
    if (status === "shared") return "Exact CT ID in both";
    return "No direct output in current scope";
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
      const note = author === ALL
        ? `${formatNumber(agg.cohortCount)} cohorts · ${formatNumber(agg.byClid.size)} CLIDs with direct assignments`
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
        <div class="filter-note">${note}</div>`;
    },

    bindControls(root, config, summary, filters, onChange) {
      const sexEl = root.querySelector("#hlcaSex");
      const authEl = root.querySelector("#hlcaAuthor");
      if (sexEl) sexEl.addEventListener("change", () => { filters.sex = sexEl.value; onChange(); });
      if (authEl) authEl.addEventListener("change", () => { filters.author = authEl.value; onChange(); });
    },

    // ---- recolour + project -------------------------------------------------
    applyFilters(cy, config, summary, filters, api) {
      const { byClid, cohortCount, idx } = aggregate(summary, filters);
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

      if (api && api.setBadge) {
        const base = `${summary.inputFile} • ${scopeText(summary, filters)}`;
        api.setBadge(`${base} • ${formatNumber(cohortCount)} cohorts • ${formatNumber(totals.size)} CLIDs in scope`);
      }
    },

    legendHtml(config, summary) {
      const c = (config.design && config.design.colors) || {};
      const partitions = summary.partitionCount || 47;
      const row = (color, text) =>
        `<div class="legend-row"><span class="dot" style="background:${color}"></span><span>${text}</span></div>`;
      return `
        <div class="legend-title">Node fill — current filter scope</div>
        ${row(c.azimuth_only || "#E53935", "Azimuth only")}
        ${row(c.pan_only || "#1565C0", "Pan-human only")}
        ${row(c.shared || "#7B1FA2", "Exact CT ID in both")}
        ${row(c.neutral || "#8A8F98", "No direct output in current scope")}
        <div class="legend-row"><span class="swatch size-big"></span><span>Large — a cell type one of the methods predicted</span></div>
        <div class="legend-row"><span class="swatch size-small"></span><span>Small — supertree structure, never predicted</span></div>
        <div class="legend-note"><strong>Size</strong> marks whether a cell type appears anywhere in the comparison across ${formatNumber(partitions)} matched partitions; it is membership, not a count. <strong>Fill</strong> answers, for the Sex and Author label currently selected, which method assigned cells to that exact cell type — so it changes as you change the filters, and grey means neither did within that scope. Selecting a single <strong>Author label</strong> highlights the cell types that label's cells were actually assigned to, together with the path from the root down to each one; the rest of the tree stays faintly drawn for context and remains clickable. Hover or click a node for the per-method cell counts.</div>`;
    },

    summaryHtml(summary) {
      const ms = summary.mappingStatusCounts || {};
      const outside = (summary.outsideTree || [])
        .map((id) => `<tr><td class="mono">${escapeHtml(id)}</td></tr>`).join("");
      return `
        <div class="card">
          <div class="card-title">Comparison summary</div>
          <div class="subcard-label">Pooled over all cohorts; the graph reflects the current scope.</div>
          <div class="kpi-grid">
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.sharedCount)}</div><div class="kpi-label">Both methods</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.azimuthOnlyCount)}</div><div class="kpi-label">Azimuth only</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.panOnlyCount)}</div><div class="kpi-label">Pan-human only</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.comparisonNodeCount)}</div><div class="kpi-label">Comparison nodes</div></div>
          </div>
          <div class="detail-grid" style="margin-top:10px;">
            <div class="detail-key">Cohorts</div><div class="detail-value">${formatNumber(summary.cohortCount)}</div>
            <div class="detail-key">Cohort cells</div><div class="detail-value">${formatNumber(summary.cohortCellCount)}</div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Mapping of comparison rows</div>
          <div class="detail-grid">
            <div class="detail-key">Mapped CLID</div><div class="detail-value">${formatNumber(ms.mapped_clid || 0)}</div>
            <div class="detail-key">Prediction absent</div><div class="detail-value">${formatNumber(ms.method_prediction_absent || 0)}</div>
            <div class="detail-key">Non-CL ID</div><div class="detail-value">${formatNumber(ms.unmapped_non_cl_id || 0)}</div>
          </div>
          ${outside ? `<div class="subcard-label" style="margin-top:10px;">Mapped CLIDs outside the supertree (${formatNumber(summary.outsideTreeCount)})</div>
          <div class="scroll-box short"><table class="panel-table nowrap"><tbody>${outside}</tbody></table></div>` : ""}
        </div>`;
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
            <div class="detail-key">Pan-human only</div><div class="detail-value">${formatNumber(t.panOnly)}</div>
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
            <div class="detail-value"><span class="dot" style="display:inline-block;vertical-align:middle;background:${swatch}"></span> ${escapeHtml(statusText(status))}</div>
            <div class="detail-key">Comparison</div><div class="detail-value">${data.isComparison ? "Predicted in the matched-partition comparison" : "Not in the comparison"}</div>
            <div class="detail-key">Depth</div><div class="detail-value">${formatNumber(data.depth)}</div>
          </div>
          <div class="path-box"><strong>Primary ontology path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>
        ${counts}
        <div class="card">
          <div class="card-title">Hierarchy provenance</div>
          <div class="detail-key">Used anywhere in paths from</div><div class="list-box">${escapeHtml(listText(data.sources))}</div>
          <div class="detail-key" style="margin-top:9px;">Terminal cell type by</div><div class="list-box">${escapeHtml(listText(data.terminalSources))}</div>
        </div>`;
    },
  };
})();

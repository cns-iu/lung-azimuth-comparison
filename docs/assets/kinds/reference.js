/* CTs SuperTree reference view.
 *
 * The supertree merged from the included CT/1 sources. Each node is drawn as a
 * fixed-width stacked bar with one slot per source, in a constant order: a slot
 * is filled in that source's colour when the source names the cell type
 * anywhere in its paths, and left pale when it does not.
 *
 * Slot POSITION carries identity, so colour is reinforcement rather than the
 * only channel — which is what lets the palette use ten hues, four of which sit
 * below 3:1 against the graph surface.
 *
 * Bars are painted on the pane's overlay canvas, not as graph elements, so they
 * never enter successors(), search, or hit-testing. Because that canvas sits
 * above the Cytoscape canvas, the hover/selection ring is drawn here too —
 * anything Cytoscape drew would be hidden beneath the bar.
 *
 * The curated-list validation overlay lives in a separate internal repository,
 * together with the source rows it compares against.
 */
(function () {
  "use strict";
  const { formatNumber, escapeHtml, listText } = window.ViewUtil;

  // Model-space bar geometry: 10 slots of 5 with 1 between them, 59 x 13 total.
  // Column spacing is 292.5 and row spacing ~25.5, so this clears both.
  const SLOT = 5, GAP = 1, SLOTS = 10;
  const BAR_W = SLOTS * SLOT + (SLOTS - 1) * GAP;   // 59
  const BAR_H = 13;
  const MIN_SLOT_PX = 1.8;      // below this a slot cannot be read — see semantic zoom
  const EMPTY = "#dfe4ec";      // an unfilled slot
  const SURFACE = "#f7f9fc";    // the gap between slots

  const paletteOf = (ctx) => ((ctx && ctx.summary && ctx.summary.palette) || []);

  function sourcesCardHtml(summary) {
    const inventory = summary.sourceInventory || [];
    const palette = summary.palette || [];
    const textOf = {};
    palette.forEach((p) => { textOf[p.source.toLowerCase()] = p.text; });

    // Slot index per source, so this table can be ordered like the bars rather
    // than alphabetically — the row order IS the left-to-right slot order.
    const slotOf = {};
    palette.forEach((p, i) => { slotOf[p.source.toLowerCase()] = i + 1; });

    const included = inventory
      .filter((s) => s.included)
      .slice()
      .sort((a, b) => (slotOf[a.source.toLowerCase()] || 99) - (slotOf[b.source.toLowerCase()] || 99));
    const excluded = inventory.filter((s) => !s.included);

    // Source names wear their own colour, darkened to 4.5:1 on white.
    const includedRows = included
      .map((s) => {
        const key = s.source.toLowerCase();
        const colour = textOf[key];
        const style = colour ? ` style="color:${colour};font-weight:650"` : "";
        return `<tr>
          <td class="num slot-no">${slotOf[key] || ""}</td>
          <td${style}>${escapeHtml(s.source)}</td>
          <td class="num">${formatNumber(s.rowCount)}</td>
          <td class="num">${formatNumber(s.nodeCount)}</td>
        </tr>`;
      })
      .join("");

    /* Held-out sources are still parsed, so we can report exactly which cell
       types the tree lacks as a result. That coverage gap is worth surfacing
       whatever the reason for holding a source out. */
    const excludedBlocks = excluded
      .map((s) => {
        const missing = s.missing || [];
        const body = missing.length
          ? `<div class="scroll-box short">
               <table class="panel-table nowrap">
                 <thead><tr><th>CLID</th><th>Label</th></tr></thead>
                 <tbody>${missing
                   .map(
                     (m) =>
                       `<tr><td class="mono">${escapeHtml(m.id)}</td><td>${escapeHtml(m.label)}</td></tr>`
                   )
                   .join("")}</tbody>
               </table>
             </div>`
          : `<div class="details-empty">Every cell type from this source is already in the supertree.</div>`;
        return `<details class="source-details">
            <summary>
              <span>${escapeHtml(s.source)}</span>
              <span class="tag exc">${formatNumber(s.missingCount || 0)} missing</span>
            </summary>
            ${body}
          </details>`;
      })
      .join("");

    return `
      <div class="card">
        <div class="card-title">CT/1 sources</div>
        <div class="subcard-label">
          <span class="tag inc">Included</span> built into the supertree, in slot order
        </div>
        <div class="scroll-box">
          <table class="panel-table">
            <thead><tr><th class="num">#</th><th>Source</th><th class="num">Rows</th><th class="num">Nodes</th></tr></thead>
            <tbody>${includedRows}</tbody>
          </table>
        </div>
        <div class="subcard-label" style="margin-top:12px;">
          <span class="tag exc">Held out</span> expand for cell types absent from the supertree
        </div>
        ${excludedBlocks}
      </div>`;
  }

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["reference"] = {
    /* A fixed-size rectangle matching the bar, so the hit area is what you see.
       This rule runs after the shared hover/selected/search rules in app.js, so
       it deliberately wins on size — those states are re-expressed as rings in
       drawNodeOverlay, which paints above the Cytoscape canvas. */
    statusStyles(colors) {
      return [
        { selector: "node", style: {
            "shape": "rectangle",
            "width": BAR_W, "height": BAR_H,
            // Only visible when zoomed out past the bar threshold, where it
            // reads as a speck the way a plain node used to.
            "background-color": colors.neutral || "#8a93a3",
            "background-opacity": 1,
        } },
      ];
    },

    /* Painted after every viewport change by app.js. */
    drawNodeOverlay(ctx, cy, config) {
      const palette = paletteOf(config);
      if (!palette.length) return;
      const n = palette.length;
      const search = (config.design && config.design.colors && config.design.colors.search) || "#00A651";

      cy.nodes().forEach((node) => {
        const w = node.renderedWidth();
        const h = node.renderedHeight();
        const gap = Math.min(3, Math.max(1, (w / BAR_W) * GAP));
        const slotW = (w - (n - 1) * gap) / n;

        // Semantic zoom: ten slots cannot be read at the fitted view, so below
        // the threshold the plain node stands in and nothing is painted here.
        if (slotW < MIN_SLOT_PX) return;

        const p = node.renderedPosition();
        const x0 = p.x - w / 2;
        const y0 = p.y - h / 2;

        ctx.save();
        ctx.globalAlpha = node.hasClass("dimmed") ? 0.08 : 1;

        // Ground first, so the gaps between slots read as surface.
        ctx.fillStyle = SURFACE;
        ctx.fillRect(x0, y0, w, h);

        const mask = node.data("srcMask") || 0;
        for (let i = 0; i < n; i += 1) {
          ctx.fillStyle = mask & (1 << i) ? palette[i].bar : EMPTY;
          ctx.fillRect(x0 + i * (slotW + gap), y0, slotW, h);
        }

        // Interaction ring, drawn here because Cytoscape's own would sit under
        // the bar. Priority mirrors the shared style order in app.js.
        let ring = null, width = 1;
        if (node.selected()) { ring = "#155eef"; width = 2.5; }
        else if (node.hasClass("hover-focus-node")) { ring = "#111827"; width = 2.5; }
        else if (node.hasClass("search-hit")) { ring = search; width = 2.5; }
        else if (node.hasClass("hover-root-path-node")) { ring = "#111827"; width = 1.8; }
        else { ring = "#9aa3b0"; width = 1; }
        ctx.strokeStyle = ring;
        ctx.lineWidth = width;
        ctx.strokeRect(x0 - width / 2, y0 - width / 2, w + width, h + width);

        ctx.restore();
      });
    },

    legendHtml(config, summary) {
      const palette = summary.palette || [];
      const rows = palette
        .map(
          (p, i) =>
            `<div class="legend-row">
               <span class="slot-no">${i + 1}</span>
               <span class="swatch slot" style="background:${p.bar}"></span>
               <span>${escapeHtml(p.source)}</span>
             </div>`
        )
        .join("");
      return `
        <div class="legend-title">Source slots — left to right on every node</div>
        ${rows}
        <div class="legend-note">Each node is a ten-slot bar, one slot per included source in the order above. A slot is filled when that source names the cell type <em>anywhere</em> in its paths, including as an ancestor, and pale when it does not. Slot position identifies the source, so the bars stay readable regardless of colour. Bars appear as you zoom in; at the fitted view each node is a single mark.</div>`;
    },

    summaryHtml(summary) {
      return `
        <div class="card">
          <div class="card-title">Supertree summary</div>
          <div class="kpi-grid">
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.nodeCount)}</div><div class="kpi-label">Nodes</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.edgeCount)}</div><div class="kpi-label">Edges</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.terminalNodeCount)}</div><div class="kpi-label">Terminal nodes</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.multiParentNodeCount)}</div><div class="kpi-label">Multi-parent nodes</div></div>
          </div>
        </div>

        ${sourcesCardHtml(summary)}`;
    },

    nodeDetailsHtml(data, ctx) {
      const palette = paletteOf(ctx);
      const mask = data.srcMask || 0;
      // Which slots are filled, in slot order, with their colours.
      const slots = palette
        .map((p, i) => ({ ...p, on: !!(mask & (1 << i)) }))
        .filter((p) => p.on)
        .map(
          (p) =>
            `<span class="src-chip"><span class="swatch slot" style="background:${p.bar}"></span>${escapeHtml(p.source)}</span>`
        )
        .join("");

      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
            <div class="detail-key">Ontology ID</div><div class="detail-value">${escapeHtml(data.id)}</div>
            <div class="detail-key">Sources</div><div class="detail-value">${formatNumber(data.srcCount || 0)} of ${formatNumber(palette.length)}</div>
            <div class="detail-key">Depth</div><div class="detail-value">${formatNumber(data.depth)}</div>
            <div class="detail-key">Parents</div><div class="detail-value">${formatNumber(data.parentCount)}</div>
            <div class="detail-key">Children</div><div class="detail-value">${formatNumber(data.childCount)}</div>
          </div>
          <div class="path-box"><strong>Primary layout path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>
        <div class="card">
          <div class="card-title">Contributing sources</div>
          <div class="chip-row">${slots || '<span class="details-empty">None.</span>'}</div>
          <div class="detail-key" style="margin-top:9px;">Is terminal in rows from</div><div class="list-box">${escapeHtml(listText(data.terminalSources))}</div>
        </div>
        <div class="card">
          <div class="card-title">Hierarchy relationships</div>
          <div class="detail-key">Parent nodes</div><div class="list-box">${escapeHtml(listText(data.parentLabels))}</div>
          <div class="detail-key" style="margin-top:9px;">Child nodes</div><div class="list-box">${escapeHtml(listText(data.childLabels))}</div>
        </div>
        <div class="card"><div class="card-title">Label variants</div><div class="list-box">${escapeHtml(listText(data.labelVariants))}</div></div>`;
    },
  };
})();

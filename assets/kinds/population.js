/* Population view — HRApop lung Azimuth vs Pan-human Azimuth (streamlined).
 * Recolors nodes by tool provenance and shows a per-node detail panel with
 * tool outputs and subtree tallies. No comparison drawer (streamlined port). */
(function () {
  "use strict";
  const { formatNumber, escapeHtml, listText } = window.ViewUtil;
  // Tool display names come from the view config, so several population-kind
  // views can coexist in one document with different tool pairs.
  function toolsOf(ctx) {
    const p = (ctx && ctx.params) || {};
    return {
      LUNG: p.lungToolDisplay || "Azimuth",
      PAN: p.panToolDisplay || "Pan-human Azimuth",
    };
  }

  function statusText(status, ctx) {
    const { LUNG, PAN } = toolsOf(ctx);
    if (status === "lung_only") return `${LUNG} only`;
    if (status === "pan_only") return `${PAN} only`;
    if (status === "shared") return "Exact CT ID in both tools";
    return "Not directly output by either tool";
  }
  function statusColor(status, ctx) {
    const c = (ctx && ctx.design && ctx.design.colors) || {};
    return c[status] || c.neutral || "#8A8F98";
  }

  /* Cell types the tools output that the supertree has no node for. Reported
     as a table so the coverage gap can be inspected, not just counted. */
  function unmappedCardHtml(summary, LUNG, PAN) {
    const rows = summary.unmapped || [];
    if (!rows.length) return "";
    const sideLabel = (s) =>
      s === "both" ? "both" : s === "lung" ? escapeHtml(LUNG) : escapeHtml(PAN);
    const body = rows
      .map(
        (r) => `<tr>
          <td class="mono">${escapeHtml(r.id)}</td>
          <td>${escapeHtml(r.label || "—")}</td>
          <td>${sideLabel(r.side)}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="card">
        <div class="card-title">Outside the Reference SuperTree</div>
        <div class="subcard-label">
          <span class="tag exc">${formatNumber(rows.length)}</span>
          Output by ${escapeHtml(LUNG)} or ${escapeHtml(PAN)} in HRApop, but absent in the
          Reference SuperTree — so they cannot be drawn.
        </div>
        <div class="scroll-box">
          <table class="panel-table nowrap">
            <thead><tr><th>CLID</th><th>Label</th><th>Output by</th></tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>`;
  }

  /* Label counts are drawn as rays protruding from the node.
   *
   * A CLID can carry several labels from one tool, because a tool may resolve a
   * population more finely than the ontology term it maps to. One ray per label.
   * Each tool keeps its own side — Azimuth right, Pan-human left — so a node's
   * fan direction tells you which tool split it, before you read the colour.
   *
   * Rays are painted on an overlay canvas rather than as graph elements, so they
   * never appear in successors(), search, or neighbourhood traversals.
   */
  const RIGHT = [0, Math.PI];              // 12 o'clock -> 6 o'clock, clockwise
  const LEFT = [Math.PI, 2 * Math.PI];

  function fanAngles(n, [from, to]) {
    // Evenly spaced within the arc, centred, so a single ray points straight out.
    const step = (to - from) / n;
    return Array.from({ length: n }, (_, i) => from + (i + 0.5) * step);
  }

  function drawRays(ctx, cx, cy, radius, count, arc, color, alpha) {
    if (count <= 0) return;
    // Absolute floors keep rays visible when the whole tree is fitted and each
    // node renders barely a pixel across; they scale up as you zoom in.
    const gap = Math.max(1.2, radius * 0.18);
    const len = Math.max(3.2, radius * 1.05);
    const inner = radius + gap;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(0.9, radius * 0.26);
    ctx.lineCap = "round";
    for (const a of fanAngles(count, arc)) {
      // Screen angles run clockwise from 12 o'clock.
      const sx = Math.sin(a);
      const sy = -Math.cos(a);
      ctx.beginPath();
      ctx.moveTo(cx + sx * inner, cy + sy * inner);
      ctx.lineTo(cx + sx * (inner + len), cy + sy * (inner + len));
      ctx.stroke();
    }
    ctx.restore();
  }

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["population"] = {
    statusText,

    statusStyles(colors) {
      const rule = (k) => ({ selector: `node[status = "${k}"]`, style: {
        "background-color": colors[k], "width": 19, "height": 19,
        "border-width": 2, "border-color": "#ffffff", "border-opacity": 0.95,
        "font-weight": 700, "z-index": 10 } });
      return [rule("lung_only"), rule("pan_only"), rule("shared")];
    },

    /* Painted on the pane's overlay canvas after every viewport change. */
    drawNodeOverlay(ctx, cy, config) {
      const c = (config.design && config.design.colors) || {};
      const red = c.lung_only || "#E53935";
      const blue = c.pan_only || "#1565C0";
      cy.nodes().forEach((n) => {
        if (n.data("status") === "neutral") return;
        const a = n.data("aLabels") || 0;
        const b = n.data("bLabels") || 0;
        if (!a && !b) return;
        const p = n.renderedPosition();
        const r = n.renderedWidth() / 2;
        if (r < 0.5) return;                     // degenerate zoom only
        const alpha = n.hasClass("dimmed") ? 0.07 : 1;
        drawRays(ctx, p.x, p.y, r, a, RIGHT, red, alpha);
        drawRays(ctx, p.x, p.y, r, b, LEFT, blue, alpha);
      });
    },

    // Extra tooltip rows: how many labels each tool used for this exact CLID.
    tooltipExtraHtml(data, ctx) {
      const { LUNG, PAN } = toolsOf(ctx);
      const c = (ctx && ctx.design && ctx.design.colors) || {};
      const a = data.aLabels || 0;
      const b = data.bLabels || 0;
      if (!a && !b) return "";
      const row = (n, name, color) => n
        ? `<div style="color:${color}">${formatNumber(n)} ${escapeHtml(name)} label${n === 1 ? "" : "s"}</div>`
        : "";
      return row(b, PAN, c.pan_only || "#7fb2f0") + row(a, LUNG, c.lung_only || "#f28b88");
    },

    legendHtml(config) {
      const { LUNG, PAN } = toolsOf(config);
      const c = (config.design && config.design.colors) || {};
      const red = c.lung_only || "#E53935";
      const blue = c.pan_only || "#1565C0";
      const purple = c.shared || "#7B1FA2";
      const row = (style, text) =>
        `<div class="legend-row"><span class="dot" style="${style}"></span><span>${text}</span></div>`;
      // Right half is Azimuth, left half Pan-human, matching the wedge order.
      // A dot with three short rays fanning right, mirroring a 3-label node.
      const rayed = `background:${red};position:relative;` +
        `box-shadow:11px -5px 0 -5.2px ${red}, 12px 0 0 -5.2px ${red}, 11px 5px 0 -5.2px ${red};`;
      return `
        <div class="legend-title">Tool provenance legend</div>
        ${row(`background:${purple}`, "Exact CT ID output by both tools")}
        ${row(`background:${red}`, escapeHtml(LUNG) + " only")}
        ${row(`background:${blue}`, escapeHtml(PAN) + " only")}
        ${row(`background:${c.neutral || "#8A8F98"}`, "Not directly output by either tool")}
        ${row(rayed, "One ray per label — " + escapeHtml(LUNG) + " right, " + escapeHtml(PAN) + " left")}
        <div class="legend-note">Node colour marks whether the exact cell-type ID was directly output by ${escapeHtml(LUNG)}, ${escapeHtml(PAN)}, both, or neither. One CLID can carry several labels from a tool, because a tool may resolve a population more finely than the ontology term it maps to — rays show one per label, fanning right for ${escapeHtml(LUNG)} and left for ${escapeHtml(PAN)}. Hover for the label counts; click for the labels themselves.</div>`;
    },

    summaryHtml(summary, ctx) {
      const { LUNG, PAN } = toolsOf(ctx);
      return `
        <div class="card">
          <div class="card-title">Comparison summary</div>
          <div class="kpi-grid">
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.sharedCount)}</div><div class="kpi-label">Shared exact IDs</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.lungOnlyCount)}</div><div class="kpi-label">${escapeHtml(LUNG)} only</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.panOnlyCount)}</div><div class="kpi-label">${escapeHtml(PAN)} only</div></div>
            <div class="kpi"><div class="kpi-value">${formatNumber(summary.nodeCount)}</div><div class="kpi-label">Tree nodes</div></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Direct tool outputs</div>
          <div class="detail-grid">
            <div class="detail-key">${escapeHtml(LUNG)} IDs</div><div class="detail-value">${formatNumber(summary.lungCount)}</div>
            <div class="detail-key">${escapeHtml(PAN)} IDs</div><div class="detail-value">${formatNumber(summary.panCount)}</div>
            <div class="detail-key">Mapped to tree</div><div class="detail-value">${formatNumber(summary.mappedComparisonCount)}</div>
            <div class="detail-key">Outside the tree</div><div class="detail-value">${formatNumber(summary.unmappedComparisonCount)}</div>
          </div>
        </div>
        ${unmappedCardHtml(summary, LUNG, PAN)}`;
    },

    nodeDetailsHtml(data, ctx) {
      const { LUNG, PAN } = toolsOf(ctx);
      const o = data.overlay || {};
      const lung = o.lungMeta || { labels: [], sexes: [], asLabels: [], datasetCounts: [] };
      const pan = o.panMeta || { labels: [], sexes: [], asLabels: [], datasetCounts: [] };
      // Labels for this exact CLID, comma-separated under the method that used them.
      const toolBlock = (name, direct, meta, color) => {
        const labels = meta.labels || [];
        return `
        <div class="detail-key" style="margin-top:9px;">
          <strong>${escapeHtml(name)}</strong>
          ${direct ? `<span style="color:${color}"> — ${formatNumber(labels.length)} label${labels.length === 1 ? "" : "s"}</span>`
                   : `<span style="color:#98a2b3"> — no direct output</span>`}
        </div>
        ${direct && labels.length ? `<div class="list-box">${escapeHtml(labels.join(", "))}</div>` : ""}`;
      };
      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Reference SuperTree Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
            <div class="detail-key">Ontology ID</div><div class="detail-value">${escapeHtml(data.id)}</div>
            <div class="detail-key">Status</div>
            <div class="detail-value"><span class="dot" style="display:inline-block;vertical-align:middle;background:${statusColor(data.status, ctx)}"></span> ${escapeHtml(statusText(data.status, ctx))}</div>
            <div class="detail-key">Depth</div><div class="detail-value">${formatNumber(data.depth)}</div>
            <div class="detail-key">Node type</div><div class="detail-value">${o.isLeaf ? "Leaf" : "Non-leaf · " + formatNumber(o.descendantCount) + " descendants"}</div>
          </div>
          <div class="path-box"><strong>Primary ontology path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>
        <div class="card">
          <div class="card-title">Tool outputs</div>
          ${toolBlock(LUNG, o.inLung, lung, statusColor("lung_only", ctx))}
          ${toolBlock(PAN, o.inPan, pan, statusColor("pan_only", ctx))}
        </div>
        <div class="card">
          <div class="card-title">Directly predicted CTs in this subtree</div>
          <div class="detail-grid">
            <div class="detail-key">${escapeHtml(LUNG)}</div><div class="detail-value">${formatNumber(o.subtreeLungCount)}</div>
            <div class="detail-key">${escapeHtml(PAN)}</div><div class="detail-value">${formatNumber(o.subtreePanCount)}</div>
            <div class="detail-key">Exact shared</div><div class="detail-value">${formatNumber(o.subtreeSharedCount)}</div>
            <div class="detail-key">Tool-specific</div><div class="detail-value">${formatNumber(o.subtreeDifferenceCount)}</div>
          </div>
        </div>`;
    },
  };
})();

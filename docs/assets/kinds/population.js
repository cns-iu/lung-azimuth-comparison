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

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["population"] = {
    statusText,

    statusStyles(colors) {
      const rule = (s) => ({ selector: `node[status = "${s}"]`, style: {
        "background-color": colors[s], "width": 19, "height": 19,
        "border-width": 2, "border-color": "#ffffff", "border-opacity": 0.95,
        "font-weight": 700, "z-index": 10 } });
      return [rule("lung_only"), rule("pan_only"), rule("shared")];
    },

    legendHtml(config) {
      const { LUNG, PAN } = toolsOf(config);
      const c = (config.design && config.design.colors) || {};
      const row = (color, text) =>
        `<div class="legend-row"><span class="dot" style="background:${color}"></span><span>${text}</span></div>`;
      return `
        <div class="legend-title">Tool provenance legend</div>
        ${row(c.shared || "#7B1FA2", "Exact CT ID output by both tools")}
        ${row(c.lung_only || "#E53935", escapeHtml(LUNG) + " only")}
        ${row(c.pan_only || "#1565C0", escapeHtml(PAN) + " only")}
        ${row(c.neutral || "#8A8F98", "Not directly output by either tool")}
        <div class="legend-note">Node color marks whether the exact cell-type ID was directly output by ${escapeHtml(LUNG)}, ${escapeHtml(PAN)}, both, or neither. Hover to trace the root path and descendant subtree.</div>`;
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
            <div class="detail-key">Unmapped IDs</div><div class="detail-value">${formatNumber(summary.unmappedComparisonCount)}</div>
          </div>
        </div>`;
    },

    nodeDetailsHtml(data, ctx) {
      const { LUNG, PAN } = toolsOf(ctx);
      const o = data.overlay || {};
      const lung = o.lungMeta || { labels: [], sexes: [], asLabels: [], datasetCounts: [] };
      const pan = o.panMeta || { labels: [], sexes: [], asLabels: [], datasetCounts: [] };
      const toolBlock = (name, direct, meta) => `
        <div class="detail-key" style="margin-top:9px;">
          <strong>${escapeHtml(name)}</strong> —
          <span style="color:${direct ? "#1a7f37" : "#98a2b3"}">${direct ? "Direct output" : "Not direct"}</span>
        </div>
        ${direct ? `<div class="list-box">${escapeHtml(listText(meta.labels))}${meta.sexes.length ? " · Sex: " + escapeHtml(meta.sexes.join(", ")) : ""}</div>` : ""}`;
      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
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
          ${toolBlock(LUNG, o.inLung, lung)}
          ${toolBlock(PAN, o.inPan, pan)}
        </div>
        <div class="card">
          <div class="card-title">Directly predicted CTs in this subtree</div>
          <div class="detail-grid">
            <div class="detail-key">${escapeHtml(LUNG)}</div><div class="detail-value">${formatNumber(o.subtreeLungCount)}</div>
            <div class="detail-key">${escapeHtml(PAN)}</div><div class="detail-value">${formatNumber(o.subtreePanCount)}</div>
            <div class="detail-key">Exact shared</div><div class="detail-value">${formatNumber(o.subtreeSharedCount)}</div>
            <div class="detail-key">Tool-specific</div><div class="detail-value">${formatNumber(o.subtreeDifferenceCount)}</div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Hierarchy provenance</div>
          <div class="detail-key">Used anywhere in paths from</div><div class="list-box">${escapeHtml(listText(data.sources))}</div>
          <div class="detail-key" style="margin-top:9px;">Terminal cell type by</div><div class="list-box">${escapeHtml(listText(data.terminalSources))}</div>
        </div>`;
    },
  };
})();

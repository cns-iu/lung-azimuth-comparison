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
    if (status === "shared") return "Exact CT ID in both";
    return "Not directly annotated by either tool";
  }
  function statusColor(status, ctx) {
    const c = (ctx && ctx.design && ctx.design.colors) || {};
    return c[status] || c.neutral || "#8A8F98";
  }

  /* Panel text in a status colour, so a figure wears the colour of the nodes it
     counts. Node fills are tuned for marks on the graph surface, and the panel
     sets them in 10–16px type, where the red only reaches 3.9:1 on the KPI
     tint — so small text gets a darkened variant of the same hue (4.6:1) while
     the nodes keep their own. Same split as the sources palette's bar/text. */
  const TEXT_OVERRIDE = { lung_only: "#D32F2F" };
  function statusTextColor(status, ctx) {
    return TEXT_OVERRIDE[status] || statusColor(status, ctx);
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
        <div class="card-title with-count">
          <span>Not represented in tree</span>
          <span class="title-count">${formatNumber(rows.length)}</span>
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
        const alpha = n.hasClass("dimmed") ? 0.1 : 1;
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
        ? `<div style="color:${color}">${formatNumber(n)} ${escapeHtml(name)} cell type label${n === 1 ? "" : "s"}</div>`
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
        ${/* Order and wording are shared with the HLCA tab, so the two legends
              can be read against each other without re-learning them. */ ""}
        ${row(`background:${red}`, escapeHtml(LUNG) + " only")}
        ${row(`background:${blue}`, escapeHtml(PAN) + " only")}
        ${row(`background:${purple}`, "Exact CT ID in both")}
        ${row(`background:${c.neutral || "#8A8F98"}`, "Not directly annotated by either tool")}
        ${row(rayed, "One ray per cell type label — " + escapeHtml(LUNG) + " right, " + escapeHtml(PAN) + " left")}
        <div class="legend-note">Node color indicates whether the exact cell-type ID was output by ${escapeHtml(LUNG)}, ${escapeHtml(PAN)}, both, or neither. Rays represent multiple cell-type labels associated with a CLID, fanning right for ${escapeHtml(LUNG)} and left for ${escapeHtml(PAN)}.</div>`;
    },

    summaryHtml(summary, ctx) {
      const { LUNG, PAN } = toolsOf(ctx);
      const tint = (status) => `color:${statusTextColor(status, ctx)}`;

      /* A KPI whose figure and caption both wear the colour of the nodes they
         count, so the panel and the graph can be read against each other
         without consulting the legend. */
      const kpi = (value, label, status) => {
        const style = status ? ` style="${tint(status)}"` : "";
        return `<div class="kpi">
          <div class="kpi-value"${style}>${formatNumber(value)}</div>
          <div class="kpi-label"${style}>${label}</div>
        </div>`;
      };

      const row = (key, value, status) => {
        const style = status ? ` style="${tint(status)}"` : "";
        return `<div class="detail-key"${style}>${key}</div>` +
          `<div class="detail-value"${style}>${formatNumber(value)}</div>`;
      };

      return `
        <div class="card">
          <div class="card-title">Comparison summary</div>
          <div class="kpi-grid">
            ${kpi(summary.lungOnlyCount, escapeHtml(LUNG) + " only", "lung_only")}
            ${kpi(summary.panOnlyCount, escapeHtml(PAN) + " only", "pan_only")}
            ${kpi(summary.sharedCount, "Shared exact IDs", "shared")}
            ${/* Deliberately uncoloured: this is the population the three
                  coloured figures are drawn from, not a fourth category of
                  node. Tinting it grey would read as "neither tool". */ ""}
            ${kpi(summary.nodeCount, "Total CTs in Supertree")}
          </div>
        </div>
        <div class="card">
          <div class="card-title">Direct tool outputs</div>
          <div class="detail-grid key-fit">
            ${row(escapeHtml(LUNG) + " IDs", summary.lungCount, "lung_only")}
            ${row(escapeHtml(PAN) + " IDs", summary.panCount, "pan_only")}
            ${row("Mapped to tree", summary.mappedComparisonCount)}
            ${row("Not represented in tree", summary.unmappedComparisonCount)}
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
          ${direct ? `<span style="color:${color}"> — ${formatNumber(labels.length)} cell type label${labels.length === 1 ? "" : "s"}</span>`
                   : `<span style="color:#98a2b3"> — no direct output</span>`}
        </div>
        ${direct && labels.length ? `<div class="list-box">${escapeHtml(labels.join(", "))}</div>` : ""}`;
      };
      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Reference Supertree Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
            <div class="detail-key">Ontology ID</div><div class="detail-value">${escapeHtml(data.id)}</div>
            <div class="detail-key">Status</div>
            <div class="detail-value"><span class="dot" style="display:inline-block;vertical-align:middle;background:${statusColor(data.status, ctx)}"></span> ${escapeHtml(statusText(data.status, ctx))}</div>
            <div class="detail-key">Depth</div><div class="detail-value">${formatNumber(data.depth)}</div>
          </div>
          <div class="path-box"><strong>Reference Supertree Path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>
        <div class="card">
          <div class="card-title">Tool outputs</div>
          ${toolBlock(LUNG, o.inLung, lung, statusColor("lung_only", ctx))}
          ${toolBlock(PAN, o.inPan, pan, statusColor("pan_only", ctx))}
        </div>
        <div class="card">
          <div class="card-title as-written">Directly predicted CTs in this subtree</div>
          <div class="detail-grid key-fit">
            <div class="detail-key">${escapeHtml(LUNG)}</div><div class="detail-value">${formatNumber(o.subtreeLungCount)}</div>
            <div class="detail-key">${escapeHtml(PAN)}</div><div class="detail-value">${formatNumber(o.subtreePanCount)}</div>
            <div class="detail-key">Exact shared</div><div class="detail-value">${formatNumber(o.subtreeSharedCount)}</div>
            <div class="detail-key">Tool-specific</div><div class="detail-value">${formatNumber(o.subtreeDifferenceCount)}</div>
          </div>
        </div>`;
    },
  };
})();

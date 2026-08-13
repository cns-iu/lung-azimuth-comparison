/* CTs SuperTree reference view.
 *
 * The supertree is built from the included CT/1 sources only. Held-out sources
 * (Martin, Chenchen, vccf, blank) contribute no nodes; instead each is compared
 * against the finished tree. Node color marks supertree *terminal* nodes that
 * Martin and/or Chenchen also reference.
 */
(function () {
  "use strict";
  const { formatNumber, escapeHtml, listText } = window.ViewUtil;

  // Compare-source labels come from the payload summary carried on the config.
  const comparesOf = (ctx) => ((ctx && ctx.summary && ctx.summary.compareSources) || []);

  function statusText(status, ctx) {
    const compare = comparesOf(ctx);
    if (status === "shared") {
      return compare.length === 2
        ? `Terminal node in both ${compare[0].label} and ${compare[1].label}`
        : "Terminal node in multiple compared sources";
    }
    if (status === "neutral") return "Other supertree node";
    const spec = compare.find((c) => c.id === status);
    return `Terminal node also in ${spec ? spec.label : status}`;
  }

  function sourcesCardHtml(summary) {
    const inventory = summary.sourceInventory || [];
    const included = inventory.filter((s) => s.included);
    const excluded = inventory.filter((s) => !s.included);

    const includedRows = included
      .map(
        (s) => `<tr>
          <td>${escapeHtml(s.source)}</td>
          <td class="num">${formatNumber(s.rowCount)}</td>
          <td class="num">${formatNumber(s.nodeCount)}</td>
        </tr>`
      )
      .join("");

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
        <div class="subcard-label"><span class="tag inc">Included</span> built into the supertree</div>
        <div class="scroll-box">
          <table class="panel-table">
            <thead><tr><th>Source</th><th class="num">Rows</th><th class="num">Nodes</th></tr></thead>
            <tbody>${includedRows}</tbody>
          </table>
        </div>
        <div class="subcard-label" style="margin-top:12px;">
          <span class="tag exc">Excluded</span> expand for cell types absent from the supertree
        </div>
        ${excludedBlocks}
      </div>`;
  }

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["reference"] = {
    statusText,

    // Minimap dots mirror the main graph: a split dot for the shared status.
    minimapColors(colors) {
      const martin = colors.martin || "#1E90FF";
      const chenchen = colors.chenchen || "#E31A1C";
      return { martin, chenchen, shared: [martin, chenchen] };
    },

    statusStyles(colors) {
      const martin = colors.martin || "#1E90FF";
      const chenchen = colors.chenchen || "#E31A1C";
      return [
        { selector: 'node[status = "martin"]', style: { "background-color": martin } },
        { selector: 'node[status = "chenchen"]', style: { "background-color": chenchen } },
        { selector: 'node[status = "shared"]', style: {
            "background-color": "#ffffff", "pie-size": "100%",
            "pie-1-background-color": martin, "pie-1-background-size": "50%",
            "pie-2-background-color": chenchen, "pie-2-background-size": "50%" } },
      ];
    },

    legendHtml(config, summary) {
      const c = (config.design && config.design.colors) || {};
      const gray = c.neutral || "#7A7B78";
      const blue = c.martin || "#1E90FF";
      const red = c.chenchen || "#E31A1C";
      const shared = `linear-gradient(90deg, ${blue} 0 50%, ${red} 50% 100%)`;
      const specs = summary.compareSources || [];
      const a = specs[0] ? specs[0].label : "Martin";
      const b = specs[1] ? specs[1].label : "Chenchen";
      const excluded = (summary.sourceInventory || [])
        .filter((s) => !s.included)
        .map((s) => s.source)
        .join(", ");
      return `
        <div class="legend-title">CTs SuperTree legend</div>
        <div class="legend-row"><span class="dot" style="background:${gray}"></span><span>All other supertree nodes</span></div>
        <div class="legend-row"><span class="dot" style="background:${blue}"></span><span>Terminal node also in ${escapeHtml(a)}</span></div>
        <div class="legend-row"><span class="dot" style="background:${red}"></span><span>Terminal node also in ${escapeHtml(b)}</span></div>
        <div class="legend-row"><span class="dot" style="background:${shared}"></span><span>Terminal node in both</span></div>
        <div class="legend-note">The supertree is built from the included CT/1 sources; ${escapeHtml(excluded)} are held out. Colored nodes are <strong>terminal</strong> nodes of the built supertree that ${escapeHtml(a)} and/or ${escapeHtml(b)} also reference. Hover a node to trace its primary root path (solid) and every descendant branch (dotted).</div>`;
    },

    summaryHtml(summary) {
      const specs = summary.compareSources || [];
      const coverageRows = specs
        .map(
          (c) => `<tr>
            <td>${escapeHtml(c.label)}</td>
            <td class="num">${formatNumber(c.nodeCount)}</td>
            <td class="num">${formatNumber(c.terminalMatchCount)}</td>
            <td class="num">${formatNumber(c.inTreeNonTerminalCount)}</td>
            <td class="num">${formatNumber(c.missingCount)}</td>
          </tr>`
        )
        .join("");

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

        ${sourcesCardHtml(summary)}

        <div class="card">
          <div class="card-title">Held-out source coverage</div>
          <div class="subcard-label">How each held-out source maps onto the built supertree.</div>
          <div class="scroll-box">
            <table class="panel-table">
              <thead><tr><th>Source</th><th class="num">Nodes</th><th class="num">Terminal</th><th class="num">Non-terminal</th><th class="num">Missing</th></tr></thead>
              <tbody>${coverageRows}</tbody>
            </table>
          </div>
          <div class="detail-grid" style="margin-top:10px;">
            <div class="detail-key">${escapeHtml(specs[0] ? specs[0].label : "Martin")} only</div><div class="detail-value">${formatNumber(summary.martinTerminalCount)}</div>
            <div class="detail-key">${escapeHtml(specs[1] ? specs[1].label : "Chenchen")} only</div><div class="detail-value">${formatNumber(summary.chenchenTerminalCount)}</div>
            <div class="detail-key">Both sources</div><div class="detail-value">${formatNumber(summary.sharedTerminalCount)}</div>
            <div class="detail-key">All other nodes</div><div class="detail-value">${formatNumber(summary.otherNodeCount)}</div>
          </div>
        </div>`;
    },

    nodeDetailsHtml(data, ctx) {
      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
            <div class="detail-key">Ontology ID</div><div class="detail-value">${escapeHtml(data.id)}</div>
            <div class="detail-key">Status</div><div class="detail-value">${escapeHtml(statusText(data.status, ctx))}</div>
            <div class="detail-key">Depth</div><div class="detail-value">${formatNumber(data.depth)}</div>
            <div class="detail-key">Parents</div><div class="detail-value">${formatNumber(data.parentCount)}</div>
            <div class="detail-key">Children</div><div class="detail-value">${formatNumber(data.childCount)}</div>
          </div>
          <div class="path-box"><strong>Primary layout path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>
        <div class="card">
          <div class="card-title">Hierarchy relationships</div>
          <div class="detail-key">Parent nodes</div><div class="list-box">${escapeHtml(listText(data.parentLabels))}</div>
          <div class="detail-key" style="margin-top:9px;">Child nodes</div><div class="list-box">${escapeHtml(listText(data.childLabels))}</div>
        </div>
        <div class="card">
          <div class="card-title">Source provenance</div>
          <div class="detail-key">Appears anywhere in paths from</div><div class="list-box">${escapeHtml(listText(data.sources))}</div>
          <div class="detail-key" style="margin-top:9px;">Is terminal in rows from</div><div class="list-box">${escapeHtml(listText(data.terminalSources))}</div>
        </div>
        <div class="card"><div class="card-title">Label variants</div><div class="list-box">${escapeHtml(listText(data.labelVariants))}</div></div>`;
    },
  };
})();

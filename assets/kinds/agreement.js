/* CTann tool-agreement view.
 *
 * Three encodings, each carrying one fact:
 *   shape  — curated band: diamond = easy, square = difficult, circle = other
 *   colour — signed consensus on a diverging brown/teal scale
 *   size   — coverage: how many tools see this population at all
 *
 * Colour without size would be misleading: a cell type called by one tool has
 * consensus 1.0 but almost no evidence behind it. Size keeps that honest.
 */
(function () {
  "use strict";
  const { formatNumber, escapeHtml } = window.ViewUtil;

  const toolsOf = (ctx) => ((ctx && ctx.summary && ctx.summary.tools) || []);
  const paletteOf = (ctx) => ((ctx && ctx.design && ctx.design.colors) || {});

  function statusText(status) {
    if (status === "agree") return "Tools agree on this cell type label";
    if (status === "disagree") return "Tools annotate it, but mostly with more specific labels";
    if (status === "mixed") return "Tools split between this label and more specific ones";
    if (status === "unused") return "No tool uses this label; all use more specific ones";
    return "No tool annotates this cell type";
  }

  function scoreWord(score, coverage, exactCount) {
    if (!coverage) return "—";
    if (!exactCount) return "no tool uses this label";
    if (score >= 0.999) return "full agreement";
    if (score <= -0.999) return "no tool uses this label";
    return score >= 0 ? "partial agreement" : "mostly more specific labels";
  }

  /* Cell types a tool annotates that the supertree has no node for: they carry
     no score and cannot be drawn, so they are listed rather than silently
     dropped. */
  function unmappedCardHtml(summary) {
    const rows = summary.unmapped || [];
    if (!rows.length) return "";
    const body = rows
      .map(
        (r) => `<tr>
          <td class="mono">${escapeHtml(String(r.id).replace(/^https?:\/\/\S*?([^/]+)$/, "$1"))}</td>
          <td>${escapeHtml(r.label || "—")}</td>
          <td class="num">${formatNumber((r.tools || []).length)}</td>
          <td>${escapeHtml((r.tools || []).join(", "))}</td>
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
            <thead><tr><th>CLID</th><th>Cell type label</th><th class="num">Tools</th><th>Annotated by</th></tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>`;
  }

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["agreement"] = {
    statusText,

    // Coarse buckets for the minimap; the graph itself uses a continuous ramp.
    minimapColors(colors) {
      return {
        agree: colors.agree || "#018571",
        mixed: colors.mixed || "#e4d9c2",
        disagree: colors.disagree || "#a6611a",
        unused: "#ffffff",
        inactive: colors.neutral || "#b9bec7",
      };
    },

    statusStyles(colors) {
      const off = colors.neutral || "#b9bec7";
      const dis = colors.disagree || "#a6611a";
      const mid = colors.mixed || "#e4d9c2";
      const agr = colors.agree || "#018571";
      return [
        // Untouched structure: small, quiet, no border.
        { selector: "node[coverage = 0]", style: {
            "background-color": off, "width": 8, "height": 8,
            "border-width": 0, "opacity": 0.5, "z-index": 2 } },
        // Scored nodes: sized by how many tools see the population. The border
        // keeps the pale midpoint of the diverging ramp visible on a light page.
        { selector: "node[coverage > 0]", style: {
            "width": "mapData(coverage, 1, 5, 11, 26)",
            "height": "mapData(coverage, 1, 5, 11, 26)",
            "border-width": 1.2, "border-color": "#4b5563", "border-opacity": 0.85,
            "font-weight": 600, "z-index": 12 } },
        // Seen, but no tool proposes this label — hollow, not "max disagreement".
        { selector: "node[coverage > 0][exactCount = 0]", style: {
            "background-color": "#ffffff", "background-opacity": 0.85,
            "border-width": 1.4, "border-color": "#9aa3b0", "border-opacity": 0.9 } },
        { selector: "node[coverage > 0][exactCount > 0][score < 0]", style: {
            "background-color": `mapData(score, -1, 0, ${dis}, ${mid})` } },
        { selector: "node[coverage > 0][exactCount > 0][score >= 0]", style: {
            "background-color": `mapData(score, 0, 1, ${mid}, ${agr})` } },
        // Curated bands last, so the shape wins regardless of score. Shapes are
        // restricted to cell types a tool actually calls: banding an entire
        // subtree would mark hundreds of nodes that carry no measurement.
        { selector: 'node[band = "easy"][exactCount > 0]', style: { "shape": "diamond" } },
        { selector: 'node[band = "difficult"][exactCount > 0]', style: { "shape": "rectangle" } },
      ];
    },

    legendHtml(config, summary) {
      const c = paletteOf(config);
      const n = summary.toolCount || 5;
      const ramp = `linear-gradient(90deg, ${c.disagree} 0%, ${c.mixed} 50%, ${c.agree} 100%)`;
      /* Grouped by encoding channel, each key naming its own mark before the
         meaning, so the legend reads without decoding the swatch first. */
      const key = (mark, name, text) =>
        `<div class="legend-row">${mark}<span><b>${name}:</b> ${escapeHtml(text)}</span></div>`;
      return `
        <div class="legend-title">Node shape — expert curated</div>
        ${key('<span class="swatch diamond"></span>', "Diamond", "Easy to annotate")}
        ${key('<span class="swatch square"></span>', "Square", "Difficult to annotate")}
        ${key('<span class="swatch circle"></span>', "Circle", "Not curated")}
        ${key('<span class="swatch circle hollow"></span>', "Hollow", "No tool uses this label")}
        <div class="legend-subhead">Node size</div>
        ${key('<span class="swatch sizes"><i></i><i></i><i></i></span>', "Size",
              `Number of tools annotating it, from 1 to ${n}`)}
        <div class="legend-subhead">Node color</div>
        ${/* Each end sits beside the end of the scale it describes, so the
              direction of the ramp is read off the legend directly. */ ""}
        <div class="legend-row ramp-row">
          <span class="ramp-ends"><b>Disagreement</b> — tools use more specific labels</span>
          <span class="ramp" style="background:${ramp}"></span>
          <span class="ramp-ends"><b>Agreement</b> — tools use this label</span>
        </div>
        <div class="legend-note">A node is shown if at least one tool annotates this cell type or one of its subtypes. Color shows how many of those tools use this exact label. Shape shows the expert rating. Curated labels that no tool uses remain circles. Gray nodes are hierarchy labels that no tool annotates.</div>`;
    },

    summaryHtml(summary) {
      const b = summary.buckets || {};
      /* Status colors in text-safe form. The node fills are tuned for marks on
         the graph: teal reaches only 4.3:1 in panel type and the ramp midpoint
         is near-white by design, so each gets a darkened variant of its own hue
         while the nodes keep theirs. Same split as the other comparison tabs. */
      const TINT = { agree: "#017d6b", mixed: "#856d3b", disagree: "#a25e19" };
      const kpi = (value, label, status) => {
        const style = status ? ` style="color:${TINT[status]}"` : "";
        return `<div class="kpi">
          <div class="kpi-value"${style}>${formatNumber(value)}</div>
          <div class="kpi-label"${style}>${label}</div>
        </div>`;
      };
      const bm = summary.bandMeanScore || {};
      const toolRows = (summary.toolClidCounts || [])
        .map((t) => `<tr><td>${escapeHtml(t.tool)}</td><td class="num">${formatNumber(t.clidCount)}</td></tr>`)
        .join("");
      const scored = summary.bandScoredCounts || {};
      const curated = summary.bandCounts || {};
      const bandRow = (key, label) => `<tr>
          <td>${label}</td>
          <td class="num">${formatNumber(curated[key] || 0)}</td>
          <td class="num">${formatNumber(scored[key] || 0)}</td>
          <td class="num">${bm[key] === null || bm[key] === undefined ? "—" : bm[key].toFixed(2)}</td>
        </tr>`;
      return `
        <div class="card">
          <div class="card-title">Agreement summary</div>
          <div class="kpi-grid">
            ${kpi(b.agree || 0, "Agree", "agree")}
            ${kpi(b.mixed || 0, "Split", "mixed")}
            ${kpi(b.disagree || 0, "Disagree", "disagree")}
            ${/* The population the three scored buckets come from, so it stays
                  uncolored rather than reading as a fourth bucket. */ ""}
            ${kpi(summary.proposedNodeCount || 0, "Cell type labels used")}
          </div>
        </div>

        <div class="card">
          <div class="card-title">Curated bands</div>
          <div class="subcard-label">Scored = annotated by at least one tool. Mean score: +1 agree, −1 disagree.</div>
          <div class="scroll-box">
            <table class="panel-table wrap-head">
              <thead><tr><th>Band</th><th class="num">In band</th><th class="num">Scored</th><th class="num">Mean</th></tr></thead>
              <tbody>
                ${bandRow("easy", "◆ Easy")}
                ${bandRow("difficult", "■ Difficult")}
                ${bandRow("other", "● Not curated")}
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="card-title">Cell types annotated per tool</div>
          <div class="scroll-box">
            <table class="panel-table">
              <thead><tr><th>Tool</th><th class="num">CLIDs</th></tr></thead>
              <tbody>${toolRows}</tbody>
            </table>
          </div>
          <div class="detail-grid key-fit" style="margin-top:10px;">
            <div class="detail-key">Distinct CLIDs</div><div class="detail-value">${formatNumber(summary.calledClidCount)}</div>
            <div class="detail-key">Mapped to tree</div><div class="detail-value">${formatNumber(summary.mappedClidCount)}</div>
            <div class="detail-key">Not represented in tree</div><div class="detail-value">${formatNumber(summary.unmappedClidCount)}</div>
          </div>
        </div>
        ${unmappedCardHtml(summary)}`;
    },

    nodeDetailsHtml(data, ctx) {
      const tools = toolsOf(ctx);
      const c = paletteOf(ctx);
      const o = data.overlay || {};
      const exact = new Set(o.exact || []);
      const sub = new Set(o.subtree || []);
      const coverage = data.coverage || 0;
      const score = data.score || 0;

      const bandLabel = data.band === "easy" ? "◆ Easy (curated)"
        : data.band === "difficult" ? "■ Difficult (curated)" : "● Not curated";

      const rows = tools.map((t, i) => {
        const verdict = exact.has(i)
          ? '<span style="color:#1a7f37">this exact label</span>'
          : sub.has(i)
            ? '<span style="color:#b45309">a more specific label below</span>'
            : '<span style="color:#98a2b3">not annotated</span>';
        return `<tr><td>${escapeHtml(t)}</td><td>${verdict}</td></tr>`;
      }).join("");

      const swatch = !coverage ? c.neutral
        : !(data.exactCount || 0) ? "#ffffff"
        : score >= 0 ? c.agree : c.disagree;

      return `
        <div class="card">
          <div class="card-title">Selected node</div>
          <div class="detail-grid">
            <div class="detail-key">Label</div><div class="detail-value"><strong>${escapeHtml(data.label)}</strong></div>
            <div class="detail-key">Ontology ID</div><div class="detail-value">${escapeHtml(data.id)}</div>
            <div class="detail-key">Band</div><div class="detail-value">${bandLabel}</div>
            <div class="detail-key">Agreement</div>
            <div class="detail-value">
              <span class="dot" style="display:inline-block;vertical-align:middle;background:${swatch};border:1px solid #9aa3b0"></span>
              ${coverage && data.exactCount ? score.toFixed(2) : "—"} · ${escapeHtml(scoreWord(score, coverage, data.exactCount || 0))}
            </div>
            <div class="detail-key">Tools annotating it</div><div class="detail-value">${formatNumber(coverage)} of ${formatNumber(tools.length)}</div>
            <div class="detail-key">Using this label</div><div class="detail-value">${formatNumber(data.exactCount || 0)}</div>
          </div>
          <div class="path-box"><strong>Reference Supertree Path</strong><br />${escapeHtml(data.primaryPathText || data.label)}</div>
        </div>

        <div class="card">
          <div class="card-title">Per-tool verdict</div>
          <div class="scroll-box">
            <table class="panel-table">
              <thead><tr><th>Tool</th><th>Annotates with</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </div>`;
    },
  };
})();

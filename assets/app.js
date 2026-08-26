/* CTs SuperTree — application runtime.
 *
 * One document holds every view. Each view owns a persistent graph pane; the
 * sidebar is shared chrome that swaps to the active view's header and panels.
 *
 * A view is built lazily on first activation (fetch payload -> hydrate ->
 * create Cytoscape in its own pane) and then kept, so switching back preserves
 * zoom, pan, and selection.
 *
 * Per-view rendering (legend, summary cards, node details, status colors) comes
 * from a kind module registered on window.ViewKinds, keyed by `kind`.
 */
(function () {
  "use strict";

  const SITE = window.SITE_CONFIG || {};
  const VIEWS = SITE.views || [];
  const KINDS = window.ViewKinds || {};
  const { formatNumber, escapeHtml } = window.ViewUtil;

  const el = (id) => document.getElementById(id);
  const dom = {
    viewTitle: el("viewTitle"),
    viewDescription: el("viewDescription"),
    summaryPanel: el("summaryPanel"),
    detailsPanel: el("detailsPanel"),
    searchInput: el("searchInput"),
    searchButton: el("searchButton"),
    tooltip: el("tooltip"),
    panelScroller: el("panelScroller"),
    viewFilters: el("viewFilters"),
  };

  /** id -> { config, pane, cy, summary, ready } */
  const states = new Map();
  let activeId = null;

  const DETAILS_PLACEHOLDER = "Select a node to inspect its details.";

  // ---- payload hydration ---------------------------------------------------
  /* Expand the normalized payload into rich Cytoscape elements. Compact nodes
     reference strings by pool index and other nodes by ordinal; this rebuilds
     the exact `data` shape the interactions and kind hooks expect. */
  function hydrate(payload) {
    const S = payload.strings;
    const compact = payload.nodes;
    const idOf = (ord) => S[compact[ord].id];
    const labelOf = (ord) => S[compact[ord].label];

    const nodes = compact.map((n) => {
      const parentIds = n.parents.map(idOf);
      const childIds = n.children.map(idOf);
      const pathIds = n.path.map(idOf);
      const pathLabels = n.path.map(labelOf);
      const data = {
        id: S[n.id],
        label: S[n.label],
        status: n.status,
        depth: n.depth,
        isRoot: !!n.isRoot,
        parentIds,
        parentLabels: n.parents.map(labelOf),
        childIds,
        childLabels: n.children.map(labelOf),
        parentCount: parentIds.length,
        childCount: childIds.length,
        primaryParentId: n.primaryParent >= 0 ? idOf(n.primaryParent) : "",
        primaryPathIds: pathIds,
        primaryPathLabels: pathLabels,
        primaryPathText: pathLabels.join(" → "),
        sources: n.sources.map((i) => S[i]),
        terminalSources: n.terminalSources.map((i) => S[i]),
        labelVariants: n.labelVariants.map((i) => S[i]),
      };
      if (n.overlay) data.overlay = n.overlay;
      if (n.st) Object.assign(data, n.st); // fields the view styles on
      return { data, position: { x: n.x, y: n.y } };
    });

    const edges = payload.edges.map((e, index) => ({
      data: {
        id: `edge-${index}`,
        source: idOf(e.s),
        target: idOf(e.t),
        rowCount: e.rowCount,
        isPrimary: !!e.primary,
      },
      classes: e.primary ? "primary-edge" : "secondary-edge",
    }));

    return { nodes, edges, summary: payload.summary };
  }

  // ---- Cytoscape style: shared base + per-view status colors ---------------
  function buildStyle(kind, design) {
    const colors = (design && design.colors) || {};
    const neutral = colors.neutral || "#7A7B78";
    const search = colors.search || "#00A651";

    const base = [
      { selector: "node", style: {
          "width": 14, "height": 14, "background-color": neutral,
          "border-width": 0, "label": "data(label)", "font-size": 10,
          "font-family": "Inter, system-ui, sans-serif", "color": "#111111",
          "text-valign": "bottom", "text-halign": "center", "text-margin-y": 4,
          "text-wrap": "wrap", "text-max-width": 200, "min-zoomed-font-size": 4,
          "z-index": 3 } },
      { selector: "edge", style: {
          "curve-style": "straight", "line-color": "#4a4a4a", "width": 0.8,
          "opacity": 0.22, "z-index": 1 } },
      { selector: "edge.primary-edge", style: { "width": 1.0, "opacity": 0.56 } },
      { selector: "edge.secondary-edge", style: { "line-style": "dashed", "opacity": 0.22 } },
      { selector: ".dimmed", style: { "opacity": 0.07, "text-opacity": 0.03 } },
      { selector: "node.search-hit", style: {
          "width": 22, "height": 22, "border-width": 4, "border-color": search,
          "border-opacity": 1, "z-index": 20, "font-size": 12, "font-weight": 700,
          "text-background-color": "#ffffff", "text-background-opacity": 0.9,
          "text-background-padding": 3, "text-background-shape": "roundrectangle" } },
      { selector: "node:selected", style: {
          "width": 22, "height": 22, "border-width": 4, "border-color": "#155eef",
          "border-opacity": 1, "z-index": 25, "font-size": 12, "font-weight": 700,
          "text-background-color": "#ffffff", "text-background-opacity": 0.92,
          "text-background-padding": 3, "text-background-shape": "roundrectangle" } },
      { selector: "edge.hover-subtree-edge", style: {
          "line-style": "dotted", "line-color": "#657084", "width": 3.2, "opacity": 0.9, "z-index": 35 } },
      { selector: "edge.hover-root-path-edge", style: {
          "line-style": "solid", "line-color": "#111827", "width": 3.2, "opacity": 1, "z-index": 40 } },
      { selector: "node.hover-subtree-node", style: {
          "border-width": 2, "border-style": "dotted", "border-color": "#657084",
          "border-opacity": 0.95, "z-index": 34 } },
      { selector: "node.hover-root-path-node", style: {
          "width": 18, "height": 18, "border-width": 3, "border-style": "solid",
          "border-color": "#111827", "border-opacity": 1, "z-index": 41 } },
      { selector: "node.hover-focus-node", style: {
          "width": 26, "height": 26, "border-width": 5, "border-style": "solid",
          "border-color": "#111827", "border-opacity": 1, "font-size": 10, "font-weight": 700,
          "text-background-color": "#ffffff", "text-background-opacity": 0.94,
          "text-background-padding": 3, "text-background-shape": "roundrectangle", "z-index": 50 } },
    ];

    const handler = KINDS[kind];
    const statusStyles = handler && handler.statusStyles
      ? handler.statusStyles(colors)
      : Object.keys(colors)
          .filter((s) => !["neutral", "search"].includes(s))
          .map((s) => ({ selector: `node[status = "${s}"]`, style: { "background-color": colors[s] } }));

    return base.concat(statusStyles);
  }

  // ---- per-view construction ----------------------------------------------
  const HOVER_CLASSES = ["hover-root-path-node", "hover-root-path-edge",
    "hover-subtree-node", "hover-subtree-edge", "hover-focus-node"];

  function badgeText(summary) {
    return `${summary.inputFile} • ${formatNumber(summary.rowCount)} rows • ` +
      `${formatNumber(summary.nodeCount)} nodes • ${formatNumber(summary.edgeCount)} edges`;
  }

  function wireInteractions(state) {
    const { cy, config } = state;
    const handler = KINDS[config.kind] || {};
    const interactions = (config.design && config.design.interactions) || {};

    cy.on("tap", "node", (event) => {
      if (state.id !== activeId) return;
      if (event.target.data("label") === undefined) return; // decorative element
      state.selectedId = event.target.id();
      dom.detailsPanel.className = "";
      dom.detailsPanel.innerHTML = handler.nodeDetailsHtml
        ? handler.nodeDetailsHtml(event.target.data(), config)
        : `<div class="card"><div class="card-title">Node</div>${escapeHtml(event.target.data().label)}</div>`;
      // Bring the *top* of the details into view. Scrolling to scrollHeight
      // would land past it, hiding the label and ontology id.
      dom.panelScroller.scrollTop = Math.max(0, dom.detailsPanel.offsetTop - 8);
    });

    cy.on("tap", (event) => {
      if (event.target !== cy) return;
      cy.$(":selected").unselect();
      state.selectedId = null;
      resetDetails();
    });

    function clearHoverTrace() {
      HOVER_CLASSES.forEach((c) => cy.elements(`.${c}`).removeClass(c));
    }
    function tracePrimaryRootPath(node) {
      const pathIds = node.data("primaryPathIds") || [];
      pathIds.forEach((id) => {
        const n = cy.getElementById(id);
        if (n.nonempty()) n.addClass("hover-root-path-node");
      });
      for (let i = 0; i < pathIds.length - 1; i += 1) {
        cy.edges()
          .filter((e) => e.data("source") === pathIds[i] && e.data("target") === pathIds[i + 1])
          .addClass("hover-root-path-edge");
      }
    }
    function traceDescendantSubtrees(node) {
      const s = node.successors();
      s.nodes().addClass("hover-subtree-node");
      s.edges().addClass("hover-subtree-edge");
    }

    if (interactions.highlightSubtree !== false || interactions.highlightParentPath !== false) {
      cy.on("mouseover", "node", (event) => {
        const node = event.target;
        const data = node.data();
        clearHoverTrace();
        if (interactions.highlightSubtree !== false) traceDescendantSubtrees(node);
        if (interactions.highlightParentPath !== false) tracePrimaryRootPath(node);
        node.addClass("hover-focus-node");

        const statusText = handler.statusText ? handler.statusText(data.status, config) : data.status;
        dom.tooltip.innerHTML = `
          <div class="tooltip-title">${escapeHtml(data.label)}</div>
          <div>${escapeHtml(data.id)}</div>
          <div class="tooltip-muted">${escapeHtml(statusText)}</div>
          <div class="tooltip-muted">Root path: ${formatNumber((data.primaryPathIds || []).length)} nodes</div>
          <div class="tooltip-muted">Descendants: ${formatNumber(node.successors("node").length)} nodes • ${formatNumber(node.successors("edge").length)} edges</div>
          ${handler.tooltipExtraHtml ? handler.tooltipExtraHtml(data, config) : ""}`;
        dom.tooltip.style.display = "block";
      });
      cy.on("mousemove", "node", (event) => {
        const o = event.originalEvent;
        if (!o) return;
        dom.tooltip.style.left = `${o.clientX + 14}px`;
        dom.tooltip.style.top = `${o.clientY + 14}px`;
      });
      cy.on("mouseout", "node", () => {
        clearHoverTrace();
        dom.tooltip.style.display = "none";
      });
    }
  }

  // ---- minimap (overview + detail) ----------------------------------------
  /* A static picture of the whole graph plus a rectangle marking what the main
     pane currently shows. The base picture is drawn once into an offscreen
     canvas and blitted on every viewport change, so panning stays cheap.

     Drag a rectangle to zoom to it, click to centre, double-click to fit. */
  function buildMinimap(state) {
    const wrap = state.pane.querySelector(".minimap");
    if (!wrap) return null;
    const canvas = wrap.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const cy = state.cy;
    const colors = (state.config.design && state.config.design.colors) || {};
    const handler = KINDS[state.config.kind] || {};
    const paint = handler.minimapColors ? handler.minimapColors(colors) : {};
    const neutral = colors.neutral || "#8A8F98";

    const base = document.createElement("canvas");
    let W = 0, H = 0, scale = 1, ox = 0, oy = 0;

    const toCanvas = (x, y) => [x * scale + ox, y * scale + oy];
    const toModel = (x, y) => [(x - ox) / scale, (y - oy) / scale];

    function drawBase() {
      const dpr = window.devicePixelRatio || 1;
      W = wrap.clientWidth;
      H = wrap.clientHeight;
      if (!W || !H) return false;

      for (const c of [canvas, base]) {
        c.width = Math.round(W * dpr);
        c.height = Math.round(H * dpr);
      }
      canvas.style.width = base.style.width = `${W}px`;
      canvas.style.height = base.style.height = `${H}px`;

      const bb = cy.elements().boundingBox({ includeLabels: false, includeOverlays: false });
      const pad = 7;
      scale = Math.min((W - 2 * pad) / bb.w, (H - 2 * pad) / bb.h);
      ox = pad + (W - 2 * pad - bb.w * scale) / 2 - bb.x1 * scale;
      oy = pad + (H - 2 * pad - bb.h * scale) / 2 - bb.y1 * scale;

      const b = base.getContext("2d");
      b.setTransform(dpr, 0, 0, dpr, 0, 0);
      b.clearRect(0, 0, W, H);

      b.strokeStyle = "rgba(90, 100, 120, 0.28)";
      b.lineWidth = 0.5;
      b.beginPath();
      cy.edges().forEach((edge) => {
        const s = edge.source().position();
        const t = edge.target().position();
        const [x1, y1] = toCanvas(s.x, s.y);
        const [x2, y2] = toCanvas(t.x, t.y);
        b.moveTo(x1, y1);
        b.lineTo(x2, y2);
      });
      b.stroke();

      cy.nodes().forEach((node) => {
        const status = node.data("status");
        if (status === undefined) return; // decorative element, not a cell type
        const p = node.position();
        const [x, y] = toCanvas(p.x, p.y);
        const fill = paint[status] || colors[status] || neutral;
        const marked = status && status !== "neutral";
        const r = marked ? 2.3 : 1.3;
        if (Array.isArray(fill)) {
          // Mirrors the pie split used for multi-source nodes in the main graph.
          b.beginPath(); b.fillStyle = fill[0];
          b.arc(x, y, r, Math.PI / 2, -Math.PI / 2); b.fill();
          b.beginPath(); b.fillStyle = fill[1];
          b.arc(x, y, r, -Math.PI / 2, Math.PI / 2); b.fill();
        } else {
          b.beginPath(); b.fillStyle = fill;
          b.arc(x, y, r, 0, Math.PI * 2); b.fill();
        }
      });
      return true;
    }

    let preview = null; // rubber-band rect in canvas coords, while dragging
    let vp = null;      // current viewport indicator, in canvas coords

    function draw() {
      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.drawImage(base, 0, 0, W, H);

      const e = cy.extent();
      let [x1, y1] = toCanvas(e.x1, e.y1);
      let [x2, y2] = toCanvas(e.x2, e.y2);
      // Keep the indicator grabbable when zoomed deep into a tall graph.
      if (x2 - x1 < 8) { const m = (x1 + x2) / 2; x1 = m - 4; x2 = m + 4; }
      if (y2 - y1 < 8) { const m = (y1 + y2) / 2; y1 = m - 4; y2 = m + 4; }

      // Spotlight: dim everything *outside* the viewport, so the default
      // fitted state reads as a clean overview rather than a tinted one.
      x1 = Math.max(0, x1); y1 = Math.max(0, y1);
      x2 = Math.min(W, x2); y2 = Math.min(H, y2);
      ctx.fillStyle = "rgba(24, 33, 47, 0.20)";
      ctx.beginPath();
      ctx.rect(0, 0, W, H);
      ctx.rect(x1, y1, x2 - x1, y2 - y1);
      ctx.fill("evenodd");

      ctx.strokeStyle = "#155eef";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x1 + 0.5, y1 + 0.5, x2 - x1 - 1, y2 - y1 - 1);
      vp = { x1, y1, x2, y2 };

      if (preview) {
        ctx.strokeStyle = "#111827";
        ctx.setLineDash([4, 3]);
        ctx.lineWidth = 1;
        ctx.strokeRect(preview.x, preview.y, preview.w, preview.h);
        ctx.setLineDash([]);
      }
    }

    function refresh() { if (drawBase()) draw(); }

    // --- pointer interaction -------------------------------------------------
    const at = (event) => {
      const r = canvas.getBoundingClientRect();
      return [event.clientX - r.left, event.clientY - r.top];
    };

    function centreOn(mx, my) {
      const zoom = cy.zoom();
      cy.pan({
        x: cy.width() / 2 - zoom * mx,
        y: cy.height() / 2 - zoom * my,
      });
    }

    function zoomToModelRect(x1, y1, x2, y2) {
      const w = Math.abs(x2 - x1);
      const h = Math.abs(y2 - y1);
      if (w < 1 || h < 1) return;
      const zoom = Math.max(
        cy.minZoom(),
        Math.min(cy.maxZoom(), Math.min(cy.width() / w, cy.height() / h))
      );
      cy.viewport({
        zoom,
        pan: {
          x: cy.width() / 2 - zoom * (x1 + x2) / 2,
          y: cy.height() / 2 - zoom * (y1 + y2) / 2,
        },
      });
    }

    let start = null;
    let dragged = false;
    let mode = "zoom";     // "pan" = drag the indicator, "zoom" = rubber band
    let panOrigin = null;

    /* Grabbing only makes sense once the indicator is meaningfully smaller than
       the map. At full fit it covers everything, and treating drags as panning
       there would make it impossible to draw a zoom rectangle at all. */
    function grabbable() {
      if (!vp) return false;
      return (vp.x2 - vp.x1) * (vp.y2 - vp.y1) < 0.9 * W * H;
    }
    function inViewport(x, y) {
      return grabbable() && x >= vp.x1 && x <= vp.x2 && y >= vp.y1 && y <= vp.y2;
    }
    function restCursor(x, y) {
      canvas.style.cursor = inViewport(x, y) ? "grab" : "crosshair";
    }

    canvas.addEventListener("pointerdown", (event) => {
      const p = at(event);
      start = p;
      dragged = false;
      mode = inViewport(p[0], p[1]) ? "pan" : "zoom";
      if (mode === "pan") {
        const cur = cy.pan();
        panOrigin = { x: cur.x, y: cur.y };
      }
      canvas.setPointerCapture(event.pointerId);
    });

    canvas.addEventListener("pointermove", (event) => {
      const [x, y] = at(event);
      if (!start) { restCursor(x, y); return; }
      if (Math.abs(x - start[0]) > 4 || Math.abs(y - start[1]) > 4) dragged = true;
      if (!dragged) return;

      if (mode === "pan") {
        canvas.style.cursor = "grabbing";
        // Moving the indicator by d canvas px moves the view by d/scale model
        // units; cy.pan is in rendered px, hence the extra zoom factor.
        const z = cy.zoom();
        cy.pan({
          x: panOrigin.x - ((x - start[0]) / scale) * z,
          y: panOrigin.y - ((y - start[1]) / scale) * z,
        });
        return; // cy's "viewport" event redraws the minimap
      }

      preview = {
        x: Math.min(start[0], x), y: Math.min(start[1], y),
        w: Math.abs(x - start[0]), h: Math.abs(y - start[1]),
      };
      draw();
    });

    canvas.addEventListener("pointerup", (event) => {
      if (!start) return;
      const [x, y] = at(event);
      if (dragged && mode === "zoom") {
        const [mx1, my1] = toModel(Math.min(start[0], x), Math.min(start[1], y));
        const [mx2, my2] = toModel(Math.max(start[0], x), Math.max(start[1], y));
        preview = null;
        zoomToModelRect(mx1, my1, mx2, my2);
      } else if (!dragged) {
        const [mx, my] = toModel(x, y);
        centreOn(mx, my);
      }
      start = null;
      dragged = false;
      preview = null;
      draw();
      restCursor(x, y);
    });

    canvas.addEventListener("pointercancel", () => {
      start = null; dragged = false; preview = null; draw();
    });

    canvas.addEventListener("dblclick", () => {
      cy.fit(cy.elements(), 72);
    });

    // Reset both the graph and this overview to the full extent.
    const resetButton = wrap.querySelector(".minimap-reset");
    if (resetButton) {
      resetButton.addEventListener("click", (event) => {
        event.stopPropagation();
        cy.fit(cy.elements(), 72);   // cy's "viewport" event redraws the overview
      });
    }

    cy.on("viewport", draw);
    refresh();
    return { refresh };
  }

  /* A view can paint per-node decorations onto a transparent canvas layered
     over the graph. Kept out of the graph model so decorations never show up in
     successors(), search, or hit-testing. Repainted whenever the view changes. */
  function setupNodeOverlay(state) {
    const handler = KINDS[state.config.kind] || {};
    if (!handler.drawNodeOverlay) return;
    const canvas = state.pane.querySelector(".node-overlay");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    function paint() {
      const dpr = window.devicePixelRatio || 1;
      const w = state.pane.clientWidth;
      const h = state.pane.clientHeight;
      if (!w || !h) return;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      handler.drawNodeOverlay(ctx, state.cy, state.config);
    }

    state.repaintOverlay = paint;
    state.cy.on("render", paint);
    paint();
  }

  function buildView(state) {
    const { config, pane } = state;
    const statusEl = pane.querySelector(".view-status");

    return fetch(config.dataUrl)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} for ${config.dataUrl}`);
        return r.json();
      })
      .then((payload) => {
        const graph = hydrate(payload);
        state.summary = graph.summary;
        config.summary = graph.summary; // kind hooks read compare metadata from here
        config.filters = state.filters;  // same object, so hooks see live scope

        const handlerEarly = KINDS[config.kind] || {};
        const extra = handlerEarly.extraElements
          ? handlerEarly.extraElements(graph, config)
          : [];

        state.cy = cytoscape({
          container: pane.querySelector(".cy-host"),
          elements: [...graph.nodes, ...extra, ...graph.edges],
          layout: { name: "preset", fit: true, padding: 72 },
          minZoom: 0.03, maxZoom: 5, wheelSensitivity: 0.18, pixelRatio: "auto",
          style: buildStyle(config.kind, config.design),
        });

        const handler = KINDS[config.kind] || {};
        const legendEl = pane.querySelector(".legend");
        if (handler.legendHtml) legendEl.innerHTML = handler.legendHtml(config, graph.summary);
        else legendEl.style.display = "none";

        pane.querySelector(".status-badge").textContent = badgeText(graph.summary);

        wireInteractions(state);
        state.minimap = buildMinimap(state);
        setupNodeOverlay(state);
        state.ready = true;
        applyViewFilters(state);
        statusEl.classList.add("hidden");
      })
      .catch((err) => {
        statusEl.classList.remove("hidden");
        statusEl.classList.add("error");
        statusEl.textContent = `Failed to load view data: ${err.message}`;
        console.error(err);
      });
  }

  // ---- per-view filters -----------------------------------------------------
  /* A kind may declare scope controls (the HLCA view filters by sex and author
     label). Filter state lives on the view, so switching tabs and returning
     preserves the scope, and the controls are re-rendered into the shared
     sidebar slot on activation. */
  function applyViewFilters(state) {
    const handler = KINDS[state.config.kind] || {};
    if (!handler.applyFilters || !state.cy || !state.summary) return;
    const badge = state.pane.querySelector(".status-badge");
    handler.applyFilters(state.cy, state.config, state.summary, state.filters, {
      setBadge: (text) => { badge.textContent = text || badgeText(state.summary); },
      defaultBadge: () => badgeText(state.summary),
    });
    // Keep an already-open details panel in step with the new scope.
    if (state.selectedId && handler.nodeDetailsHtml) {
      const node = state.cy.getElementById(state.selectedId);
      if (node && node.nonempty()) {
        dom.detailsPanel.className = "";
        dom.detailsPanel.innerHTML = handler.nodeDetailsHtml(node.data(), state.config);
      }
    }
  }

  function renderViewControls(state) {
    const handler = KINDS[state.config.kind] || {};
    if (!handler.controlsHtml || !state.summary) {
      dom.viewFilters.innerHTML = "";
      return;
    }
    dom.viewFilters.innerHTML = handler.controlsHtml(state.config, state.summary, state.filters);
    if (handler.bindControls) {
      handler.bindControls(dom.viewFilters, state.config, state.summary, state.filters, () => {
        applyViewFilters(state);
        renderViewControls(state); // reflect derived text (e.g. scope counts)
      });
    }
  }

  // ---- sidebar / activation -------------------------------------------------
  function resetDetails() {
    dom.detailsPanel.className = "empty-state";
    dom.detailsPanel.textContent = DETAILS_PLACEHOLDER;
  }

  function renderSidebar(state) {
    const { config } = state;
    dom.viewTitle.textContent = config.title || "";
    dom.viewDescription.textContent = config.subtitle || "";

    const handler = KINDS[config.kind] || {};
    dom.summaryPanel.innerHTML =
      state.summary && handler.summaryHtml ? handler.summaryHtml(state.summary, config) : "";
    resetDetails();
    dom.panelScroller.scrollTop = 0;

    renderViewControls(state);

    const legendPos = (config.design && config.design.legend && config.design.legend.position) || "bottom";
    document.body.setAttribute("data-legend", legendPos);
  }

  function activate(id) {
    const state = states.get(id);
    if (!state) return;
    activeId = id;

    states.forEach((s) => {
      s.pane.classList.toggle("active", s.id === id);
      if (s.tab) s.tab.classList.toggle("active", s.id === id);
    });

    dom.searchInput.value = "";
    state.selectedId = null;
    renderSidebar(state);
    history.replaceState(null, "", `#${id}`);

    if (!state.ready) {
      // The pane is visible now, so Cytoscape can measure its container.
      buildView(state).then(() => renderSidebar(state));
    } else if (state.cy) {
      state.cy.resize();
      if (state.minimap) state.minimap.refresh();
      if (state.repaintOverlay) state.repaintOverlay();
    }
  }

  // ---- search (acts on the active view) --------------------------------------
  function activeState() { return states.get(activeId); }

  function clearSearch() {
    const state = activeState();
    if (!state || !state.cy) return;
    state.cy.elements().removeClass("dimmed search-hit");
    state.cy.$(":selected").unselect();
    dom.searchInput.value = "";
    state.pane.querySelector(".status-badge").textContent = badgeText(state.summary);
  }

  function runSearch() {
    const state = activeState();
    if (!state || !state.cy) return;
    const cy = state.cy;
    const badge = state.pane.querySelector(".status-badge");
    const query = dom.searchInput.value.trim().toLocaleLowerCase();
    cy.elements().removeClass("dimmed search-hit");

    if (!query) {
      clearSearch();
      cy.fit(cy.elements(), 72);
      return;
    }

    const matches = cy.nodes().filter((node) => {
      const d = node.data();
      return [d.id, d.label, ...(d.labelVariants || []), ...(d.sources || []), ...(d.terminalSources || [])]
        .join(" ").toLocaleLowerCase().includes(query);
    });

    if (!matches.length) {
      badge.textContent = `No nodes matched “${dom.searchInput.value.trim()}”.`;
      return;
    }

    const context = matches
      .union(matches.predecessors())
      .union(matches.connectedEdges())
      .union(matches.predecessors().connectedEdges());
    cy.elements().addClass("dimmed");
    context.removeClass("dimmed");
    matches.removeClass("dimmed").addClass("search-hit");
    cy.fit(context, 90);
    badge.textContent =
      `${formatNumber(matches.length)} matching node${matches.length === 1 ? "" : "s"} for “${dom.searchInput.value.trim()}”.`;
  }

  // ---- boot -----------------------------------------------------------------
  VIEWS.forEach((config) => {
    const pane = document.getElementById(`pane-${config.id}`);
    const tab = document.querySelector(`.tab[data-view="${config.id}"]`);
    if (!pane) return;
    const state = {
      id: config.id, config, pane, tab,
      cy: null, summary: null, minimap: null, ready: false,
      filters: {}, selectedId: null,
    };
    states.set(config.id, state);
    if (tab) tab.addEventListener("click", () => activate(config.id));
  });

  dom.searchButton.addEventListener("click", runSearch);
  dom.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") runSearch();
    if (event.key === "Escape") {
      clearSearch();
      const state = activeState();
      if (state && state.cy) state.cy.fit(state.cy.elements(), 72);
    }
  });

  window.addEventListener("resize", () => {
    const state = activeState();
    if (!state || !state.cy) return;
    state.cy.resize();
    if (state.minimap) state.minimap.refresh();
    if (state.repaintOverlay) state.repaintOverlay();
  });

  const initial = VIEWS.find((v) => v.id === location.hash.slice(1)) || VIEWS[0];
  if (initial) activate(initial.id);
})();

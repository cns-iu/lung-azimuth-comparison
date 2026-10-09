/* A text tab: no graph, just a scrollable page describing the app.
 *
 * Shared with the internal SWAT Supertree repository, which uses the same kind
 * for its own overview tab; only the copy in the view config differs.
 *
 * Everything it shows comes from the view's `params` in its config, except the
 * tab headings, which are read from the live SITE_CONFIG. Renaming a tab in
 * site.json therefore renames it here too, so this page cannot drift out of
 * step with the tabs it describes.
 */
(function () {
  "use strict";
  const { escapeHtml } = window.ViewUtil;

  /* Inline text with markdown-style links: [label](url). Escaping runs first,
     so the copy is still treated as text — only the link syntax is promoted to
     markup afterwards, and the href is escaped with it. */
  function inline(text) {
    return escapeHtml(text).replace(
      /\[([^\]]+)\]\(([^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>'
    );
  }

  // The tab's own title, as the tab bar shows it right now.
  function tabTitle(id, fallback) {
    const views = (window.SITE_CONFIG || {}).views || [];
    const view = views.find((v) => v.id === id);
    return (view && (view.tabTitle || view.title)) || fallback || id;
  }

  window.ViewKinds = window.ViewKinds || {};
  window.ViewKinds["doc"] = {
    /* app.js renders this instead of building a graph. */
    documentHtml(config) {
      const p = config.params || {};
      const sections = (p.sections || [])
        .map(
          (s) => `
        <section class="doc-item">
          <h3>${escapeHtml(tabTitle(s.view, s.label))}</h3>
          <p>${escapeHtml(s.text)}</p>
        </section>`
        )
        .join("");

      const repo = p.repo
        ? `<p class="doc-repo">Source and data at:
             <a href="${escapeHtml(p.repo)}" target="_blank" rel="noopener">${escapeHtml(p.repo.replace(/^https:\/\//, ""))}</a></p>`
        : "";

      return `
        <article class="doc">
          <h1>${escapeHtml(p.heading || config.title || "")}</h1>
          ${(p.intro || []).map((t) => `<p>${inline(t)}</p>`).join("")}
          ${repo}

          <h2>What this app contains</h2>
          ${sections}
        </article>`;
    },
  };
})();

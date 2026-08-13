/* Tiny shared helpers, loaded before the kind module and the runtime so both
 * can rely on window.ViewUtil being present at load time. */
(function () {
  "use strict";
  window.ViewUtil = {
    formatNumber(value) {
      return Number(value || 0).toLocaleString();
    },
    escapeHtml(value) {
      return String(value == null ? "" : value)
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    },
    listText(values, limit = 12) {
      const clean = Array.isArray(values) ? values : [];
      if (!clean.length) return "None";
      if (clean.length <= limit) return clean.join(", ");
      return `${clean.slice(0, limit).join(", ")} … (+${clean.length - limit} more)`;
    },
  };
})();

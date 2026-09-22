/* Shared, dependency-free table controller. OSM consumes the same initializer. */
(function (host) {
  "use strict";
  const controllers = new WeakMap();
  if (host.Tabular) return;
  const empty = () => Object.create(null);
  const year = (value) => /^\d{4}/.test(value) ? Number(value.slice(0, 4)) : null;
  const normalizeSearch = (value) => String(value).normalize("NFKC").toLowerCase();
  function intlLocale(locale, api = Intl.Collator) {
    try { return api.supportedLocalesOf([locale])[0] || "en"; }
    catch { return "en"; }
  }
  function formatMessage(message, values, locale = "en") {
    if (typeof message === "object" && message !== null) {
      const language = intlLocale(message.locale || locale, Intl.PluralRules);
      const category = new Intl.PluralRules(language).select(values[message.plural]);
      message = message.forms[category] ?? message.forms.other;
    }
    return String(message ?? "").replace(/{{|}}|\{([A-Za-z_][A-Za-z_0-9]*)\}/g,
      (token, name) => token === "{{" ? "{" : token === "}}" ? "}" : String(values[name]));
  }
  function componentI18n(element) {
    const root = element.closest("[data-i18n]");
    if (root) return JSON.parse(root.dataset.i18n);
    return { locale: element.closest("[lang]")?.lang || document.documentElement.lang || "en", words: {} };
  }

  function matches(record, state, filters) {
    if (!normalizeSearch(record.search).includes(normalizeSearch(state.q.trim()))) return false;
    return Object.entries(filters).every(([field, spec]) => {
      const values = record.values[field] || [""];
      if (spec.control === "year_range") {
        const range = state.ranges[field] || {};
        if (!range.from && !range.to) return true;
        return values.some((value) => {
          const y = year(value);
          return y !== null && (!range.from || y >= Number(range.from)) &&
            (!range.to || y <= Number(range.to));
        });
      }
      const selected = state.filters[field] || [];
      return !selected.length || (spec.match === "all"
        ? selected.every((v) => values.includes(v))
        : selected.some((v) => values.includes(v)));
    });
  }

  function compare(a, b, direction, locale = "en") {
    if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1;
    const delta = typeof a === "number" && typeof b === "number"
      ? a - b : new Intl.Collator(intlLocale(locale)).compare(String(a), String(b));
    return direction === "desc" ? -delta : delta;
  }

  function initialState(config) {
    return { q: "", filters: empty(), ranges: empty(),
      sort: config.sort || "", order: config.order || "asc" };
  }
  function param(config, key) {
    return config.queryPrefix ? `${config.queryPrefix}.${key}` : key;
  }
  function readState(config, url) {
    const state = initialState(config);
    const params = new URL(url).searchParams;
    state.q = params.get(param(config, "q")) || "";
    const sort = params.get(param(config, "sort"));
    if (sort === "" || config.sortFields.includes(sort)) state.sort = sort;
    const order = params.get(param(config, "order"));
    if (order === "asc" || order === "desc") state.order = order;
    Object.entries(config.filters).forEach(([field, spec]) => {
      if (spec.control === "year_range") {
        const range = {};
        ["from", "to"].forEach((edge) => {
          const value = params.get(param(config, `${field}.${edge}`));
          if (/^\d{4}$/.test(value || "")) range[edge] = value;
        });
        if (range.from && range.to && Number(range.from) > Number(range.to)) return;
        state.ranges[field] = range;
      } else {
        state.filters[field] = [...new Set(params.getAll(param(config, field)))]
          .filter((v) => spec.values.includes(v));
      }
    });
    return state;
  }
  function stateURL(config, state, href) {
    const url = new URL(href);
    const set = (key, values) => {
      key = param(config, key);
      url.searchParams.delete(key);
      values.forEach((value) => url.searchParams.append(key, value));
    };
    set("q", state.q ? [state.q] : []);
    // Explicit empty sorting overrides a configured initial sort.
    set("sort", state.sort !== (config.sort || "") ? [state.sort] : []);
    set("order", state.order !== (config.order || "asc") ? [state.order] : []);
    Object.entries(config.filters).forEach(([field, spec]) => {
      if (spec.control === "year_range") {
        ["from", "to"].forEach((edge) => {
          const value = (state.ranges[field] || {})[edge];
          set(`${field}.${edge}`, value ? [value] : []);
        });
      } else set(field, state.filters[field] || []);
    });
    return url.href;
  }

  function legacyValue(cell) {
    const value = (cell.dataset.sortValue ?? cell.textContent).trim();
    if (!value) return null;
    if (/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(value)) return Number(value);
    if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
      const number = Date.parse(value);
      if (Number.isFinite(number)) return number;
    }
    return value;
  }

  function initTable(table, options = {}) {
    if (controllers.has(table)) {
      const controller = controllers.get(table);
      Object.assign(controller.options, options);
      controller.update();
      return controller;
    }
    const root = table.closest(".tabular-view, .osm-place-list-wrapper") || table.parentElement;
    const modern = root.classList.contains("tabular-view");
    const component = componentI18n(root);
    const prefix = modern ? "tabular" : "osm";
    const body = table.tBodies[0];
    if (!body) return null;
    const columns = [...table.querySelectorAll("thead th")];
    const config = options.config || {
      records: [], filters: { tags: { control: "chips", match: "any", values: [] } },
      sortFields: columns.map((_, i) => String(i)), presets: [], querySync: false,
      words: component.words, locale: component.locale,
    };
    const records = new Map(config.records.map((r) => [r.id, r]));
    const entries = [], groups = [], blocks = [];
    const stack = [];
    let run = [];
    [...body.children].forEach((row) => {
      if (row.classList.contains(`${prefix}-group-header`)) {
        if (run.length) blocks.push(run);
        run = [];
        const depth = Number(row.dataset.depth || 0);
        stack.length = depth;
        const group = { row, depth, collapsed: false, parents: [...stack], entries: [] };
        groups.push(group);
        stack.push(group);
        blocks.push(group);
      } else if (!row.classList.contains("tabular-detail")) {
        const id = row.dataset.row ?? String(entries.length);
        const record = records.get(id) || {
          id, search: row.textContent.toLowerCase(),
          values: { tags: [...row.querySelectorAll(".osm-badge--tag")].map((b) => b.textContent.trim()) },
          sort: Object.fromEntries([...row.cells].map((cell, i) => [String(i), legacyValue(cell)])),
        };
        const next = row.nextElementSibling;
        const detail = next && next.classList.contains("tabular-detail") ? next : null;
        const entry = { row, detail, record, expandButton: row.querySelector("[data-expand]"), groups: [...stack],
          original: entries.length, weight: Number(row.dataset.rowWeight || 1) };
        stack.forEach((g) => g.entries.push(entry));
        entries.push(entry);
        run.push(entry);
      }
    });
    if (run.length) blocks.push(run);
    const groupOrder = new Map();
    entries.forEach((e) => {
      const key = JSON.stringify(e.record.group || []);
      if (!groupOrder.has(key)) groupOrder.set(key, groupOrder.size);
      e.groupOrder = groupOrder.get(key);
    });
    let state = config.querySync ? readState(config, location.href) : initialState(config);
    const count = modern ? root.querySelector("[data-count]") : root.querySelector(".osm-place-list-count");
    const expanded = new Set();
    const groupCounts = new Map(groups.map((g) => [g, g.row.querySelector(`.${prefix}-group-count`)]));
    const originalCounts = new Map(groups.map((g) => [g, groupCounts.get(g)?.textContent || ""]));
    let lastOrder = null;
    function update(writeURL = false) {
      const shown = entries.filter((e) => matches(e.record, state, config.filters));
      const matched = new Set(shown);
      entries.forEach((entry) => {
        const visible = matched.has(entry) && !entry.groups.some((g) => g.collapsed);
        entry.row.hidden = !visible;
        entry.row.classList.toggle(`${prefix}-row-hidden`, !visible);
        if (entry.detail) entry.detail.hidden = !visible || !expanded.has(entry.record.id);
        const button = entry.expandButton;
        if (button) {
          button.setAttribute("aria-expanded", String(expanded.has(entry.record.id)));
          button.textContent = expanded.has(entry.record.id) ? "−" : "＋";
        }
      });
      groups.forEach((g) => {
        const filtered = g.entries.filter((e) => matched.has(e));
        g.row.hidden = !filtered.length || g.parents.some((parent) => parent.collapsed);
        g.row.classList.toggle(`${prefix}-group-header--collapsed`, g.collapsed);
        g.row.setAttribute("aria-expanded", String(!g.collapsed));
        const label = groupCounts.get(g);
        if (label) {
          const n = filtered.reduce((sum, e) => sum + e.weight, 0);
          if (label.hasAttribute("data-count-message")) {
            label.textContent = formatMessage(JSON.parse(label.dataset.countMessage), { n }, config.locale);
          } else if (label.hasAttribute("data-count-template")) {
            // This is a trusted server-side settings template; only n varies.
            const markup = label.dataset.countTemplate.replaceAll("{n}", String(n));
            if (label.innerHTML !== markup) label.innerHTML = markup;
          } else label.textContent = originalCounts.get(g).replace(/\d+/, String(n));
        }
      });
      const orderKey = JSON.stringify([state.sort, state.order]);
      if (orderKey !== lastOrder) {
        const fragment = document.createDocumentFragment();
        blocks.forEach((block) => {
          if (!Array.isArray(block)) { fragment.append(block.row); return; }
          const ordered = [...block].sort((a, b) => a.groupOrder - b.groupOrder ||
            (state.sort ? compare(a.record.sort[state.sort], b.record.sort[state.sort], state.order, config.locale) : 0) ||
            a.original - b.original);
          ordered.forEach((e) => { fragment.append(e.row); if (e.detail) fragment.append(e.detail); });
        });
        body.append(fragment);
        lastOrder = orderKey;
      }
      if (count) {
        count.textContent = options.formatCount ? options.formatCount(shown.length)
          : formatMessage(modern ? config.words.count : config.words.row_count || "{n} rows",
              { n: shown.length, shown: shown.length, total: entries.length }, config.locale);
      }
      if (syncControls) syncControls(state, shown);
      columns.forEach((th, i) => {
        const key = modern ? th.dataset.column : String(i);
        const on = key === state.sort;
        th.setAttribute("aria-sort", on ? (state.order === "asc" ? "ascending" : "descending") : "none");
        const icon = th.querySelector(`.${prefix}-sort-icon`);
        if (icon) { icon.textContent = on ? (state.order === "asc" ? "▲" : "▼") : "⇅"; icon.dataset.active = on ? "1" : ""; }
      });
      if (writeURL && config.querySync) {
        history.replaceState(history.state, "", stateURL(config, state, location.href));
      }
    }
    function change() {
      update(true);
    }
    function toggleSort(key) {
      if (state.sort !== key) { state.sort = key; state.order = "asc"; }
      else if (state.order === "asc") state.order = "desc";
      else state.sort = "";
      change();
    }
    columns.forEach((th, i) => {
      const key = modern ? th.dataset.column : String(i);
      if (!config.sortFields.includes(key) || th.classList.contains("osm-list-image-col-header")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tabular-sort-button";
      button.append(...th.childNodes);
      const icon = document.createElement("span");
      icon.className = `${prefix}-sort-icon`;
      icon.setAttribute("aria-hidden", "true");
      button.append(icon);
      th.append(button);
      th.setAttribute("data-sortable", "");
      button.addEventListener("click", () => toggleSort(key));
    });
    groups.forEach((g) => {
      g.row.setAttribute("tabindex", "0");
      g.row.setAttribute("role", "button");
      const toggle = (e) => {
        if (e.target.closest("a")) return;
        g.collapsed = !g.collapsed;
        update();
      };
      g.row.addEventListener("click", toggle);
      g.row.addEventListener("keydown", (e) => {
        if (!e.target.closest("a") && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault(); toggle(e);
        }
      });
    });
    root.addEventListener("click", (event) => {
      if (!modern) {
        const badge = event.target.closest(".osm-badge--tag");
        if (badge && table.contains(badge)) {
          event.preventDefault();
          const tag = badge.textContent.trim();
          state.filters.tags = (state.filters.tags || []).includes(tag) ? [] : [tag];
          let chip = root.querySelector(".osm-tag-filter-chip");
          if (chip) chip.remove();
          if (state.filters.tags.length) {
            chip = document.createElement("button"); chip.type = "button";
            chip.className = "osm-tag-filter-chip"; chip.textContent = `${tag} ×`;
            chip.addEventListener("click", () => { state.filters.tags = []; chip.remove(); update(); });
            root.prepend(chip);
          }
          update();
        }
      }
    });
    function expandToHash() {
      let id;
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
      const target = document.getElementById(id);
      if (!target || !table.contains(target)) return;
      const group = groups.find((g) => g.row === target);
      const entry = entries.find((e) => e.row === target || e.detail === target);
      if (group) [group, ...group.parents].forEach((g) => { g.collapsed = false; });
      if (entry) {
        entry.groups.forEach((g) => { g.collapsed = false; });
        if (entry.detail === target) expanded.add(entry.record.id);
      }
      update();
    }
    if (config.querySync) host.addEventListener("popstate", () => { state = readState(config, location.href); update(); });
    host.addEventListener("hashchange", expandToHash);
    const syncControls = options.mountControls?.({
      root, config, getState: () => state, update, change, expanded,
    });
    const controller = { options, update, getState: () => state };
    controllers.set(table, controller);
    update(); expandToHash();
    return controller;
  }

  function init(root = document) {
    if (api.initViews) api.initViews(root);
    root.querySelectorAll(".osm-place-list").forEach((table) => initTable(table));
  }
  const api = { init, initTable, matches, compare, readState, stateURL, initialState,
    formatMessage, componentI18n, normalizeSearch };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document !== "undefined") {
    host.Tabular = api;
    const start = () => { init(); host.dispatchEvent(new Event("tabular:ready")); };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
    else start();
  }
})(globalThis);

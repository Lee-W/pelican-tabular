/* Optional database controls; plain tables only load tabular-core.js. */
(function (host) {
  "use strict";
  const api = host.Tabular;
  if (api.initViews) return;
  const initializedViews = new WeakSet();
  const empty = () => Object.create(null);

  function mountControls({ root, config, getState, update, change, expanded }) {
    const search = root.querySelector("[data-search]");
    const sort = root.querySelector("[data-sort]");
    const direction = root.querySelector("[data-direction]");
    const error = root.querySelector("[data-error]");
    const filterSets = [...root.querySelectorAll("fieldset[data-filter]")];

    root.addEventListener("click", (event) => {
      const state = getState();
      const button = event.target.closest("button");
      if (button && root.contains(button)) {
        const fieldset = button.closest("fieldset[data-filter]");
        if (fieldset) {
          const field = fieldset.dataset.filter;
          const selected = state.filters[field] || [];
          if (button.hasAttribute("data-any")) state.filters[field] = [];
          else if (button.hasAttribute("data-value")) {
            const v = button.dataset.value;
            state.filters[field] = selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v];
          }
          change();
        } else if (button.hasAttribute("data-expand")) {
          const id = button.dataset.expand;
          expanded.has(id) ? expanded.delete(id) : expanded.add(id);
          update();
        } else if (button.hasAttribute("data-filter-toggle")) {
          const panel = root.querySelector(".tabular-filters");
          panel.hidden = !panel.hidden;
          button.setAttribute("aria-expanded", String(!panel.hidden));
        } else if (button.hasAttribute("data-clear")) {
          state.q = ""; state.filters = empty(); state.ranges = empty(); change();
        } else if (button.hasAttribute("data-clear-search")) {
          state.q = ""; change(); search.focus();
        } else if (button.hasAttribute("data-direction")) {
          state.order = state.order === "asc" ? "desc" : "asc"; change();
        } else if (button.hasAttribute("data-preset")) {
          const preset = config.presets[Number(button.dataset.preset)];
          const on = button.getAttribute("aria-pressed") === "true";
          Object.entries(preset.filters).forEach(([f, v]) => { state.filters[f] = on ? [] : [...v]; });
          change();
        }
      }
    });
    if (search) search.addEventListener("input", () => { getState().q = search.value; change(); });
    if (sort) sort.addEventListener("change", () => { getState().sort = sort.value; change(); });
    filterSets.forEach((fieldset) => fieldset.querySelectorAll("[data-range]").forEach((select) => {
      select.addEventListener("change", () => {
        const state = getState();
        const field = fieldset.dataset.filter;
        const range = { ...state.ranges[field], [select.dataset.range]: select.value };
        if (range.from && range.to && Number(range.from) > Number(range.to)) {
          error.textContent = config.words.range_error; error.hidden = false;
          select.value = (state.ranges[field] || {})[select.dataset.range] || "";
          return;
        }
        state.ranges[field] = range; change();
      });
    }));

    return function syncControls(state, shown) {
      if (error) error.hidden = true;
      const noResults = root.querySelector("[data-empty]");
      if (noResults) noResults.hidden = shown.length !== 0;
      if (search && search.value !== state.q) search.value = state.q;
      if (sort) sort.value = state.sort;
      if (direction) {
        direction.textContent = state.order === "asc" ? "↑" : "↓";
        direction.dataset.order = state.order;
      }
      let active = state.q.trim() ? 1 : 0;
      filterSets.forEach((fieldset) => {
        const field = fieldset.dataset.filter;
        const selected = state.filters[field] || [];
        const range = state.ranges[field] || {};
        active += selected.length + (range.from || range.to ? 1 : 0);
        fieldset.querySelectorAll("button[data-value], button[data-any]").forEach((b) => {
          const on = b.hasAttribute("data-any") ? !selected.length : selected.includes(b.dataset.value);
          b.setAttribute("aria-pressed", String(on));
        });
        fieldset.querySelectorAll("[data-range]").forEach((select) => {
          const value = range[select.dataset.range] || "";
          // Deep links may use a valid boundary between the available years.
          if (value && ![...select.options].some((o) => o.value === value)) select.add(new Option(value, value));
          select.value = value;
        });
      });
      const filterCount = root.querySelector("[data-filter-count]");
      if (filterCount) filterCount.textContent = String(active);
      root.querySelectorAll("[data-preset]").forEach((button) => {
        const preset = config.presets[Number(button.dataset.preset)];
        const on = Object.entries(preset.filters).every(([f, v]) =>
          v.length === (state.filters[f] || []).length && v.every((s) => state.filters[f].includes(s)));
        button.setAttribute("aria-pressed", String(on));
      });
    };
  }
  api.initViews = function (root = document) {
    root.querySelectorAll(".tabular-view").forEach((view) => {
      if (initializedViews.has(view)) return;
      try {
        const config = JSON.parse(view.querySelector(".tabular-data").textContent);
        api.initTable(view.querySelector("table"), { config, mountControls });
        initializedViews.add(view);
        view.classList.add("tabular-ready");
        view.querySelector(".tabular-controls").hidden = false;
      } catch (error) { console.error("pelican-tabular: could not initialize view", error); }
    });
  };
  if (document.readyState !== "loading") api.initViews();
})(globalThis);

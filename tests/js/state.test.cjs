const { test } = require("node:test");
const assert = require("node:assert/strict");
const { initialState, matches, compare, readState, stateURL } = require("../../src/pelican/plugins/tabular/static/js/tabular-core.js");
const config = {
  queryPrefix: "works", sortFields: ["score"], sort: "score", order: "desc",
  filters: {
    status: { control: "chips", values: ["ongoing", "planned"], match: "any" },
    genres: { control: "chips", values: ["科幻", "日常"], match: "all" },
    year: { control: "year_range", years: [2020, 2026] },
  },
};
test("combined search, OR options, AND genres and inclusive year bounds", () => {
  const state = initialState(config);
  const record = { search: "星河 lin", values: { status: ["ongoing"], genres: ["科幻", "日常"], year: ["2020-01-01", "2026-07-01"] } };
  state.q = " LIN "; state.filters.status = ["ongoing", "planned"];
  state.filters.genres = ["科幻", "日常"]; state.ranges.year = { from: "2025", to: "2026" };
  assert.equal(matches(record, state, config.filters), true);
  assert.equal(matches({ ...record, values: { ...record.values, genres: ["日常"] } }, state, config.filters), false);
  assert.equal(matches({ ...record, values: { ...record.values, year: [""] } }, state, config.filters), false);
});
test("URL round trip preserves unrelated state, hash, repeated and empty values", () => {
  const base = "https://example.test/database?utm_source=book&other.status=planned#chapter";
  const state = initialState(config);
  state.q = "科幻 & 日常"; state.filters.status = ["planned", "ongoing"];
  state.ranges.year = { from: "2021", to: "2026" }; state.sort = "";
  const result = stateURL(config, state, base);
  const url = new URL(result);
  assert.equal(url.searchParams.get("utm_source"), "book");
  assert.equal(url.searchParams.get("other.status"), "planned");
  assert.equal(url.hash, "#chapter");
  const restored = readState(config, result);
  assert.equal(restored.sort, ""); assert.equal(restored.q, state.q);
  assert.deepEqual(restored.filters.status, state.filters.status);
  assert.deepEqual(restored.ranges.year, state.ranges.year);
});
test("unknown URL values and inverted ranges are ignored", () => {
  const state = readState(config, "https://example.test/?works.status=evil&works.sort=secret&works.year.from=2026&works.year.to=2020");
  assert.deepEqual(state.filters.status, []);
  assert.equal(state.sort, "score"); assert.equal(state.ranges.year, undefined);
});
test("nulls remain last in both sorting directions and numbers sort numerically", () => {
  for (const direction of ["asc", "desc"]) {
    assert.equal(compare(null, 9, direction), 1);
    assert.equal(compare(9, null, direction), -1);
  }
  assert.equal(compare(10, 2, "asc"), 8);
});

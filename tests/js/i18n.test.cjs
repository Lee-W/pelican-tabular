const { test } = require("node:test");
const assert = require("node:assert/strict");
const { formatMessage, normalizeSearch, compare } = require("../../src/pelican/plugins/tabular/static/js/tabular-core.js");

test("CLDR plural forms, fallback language and escaped braces", () => {
  const message = { plural: "n", locale: "en", forms: { one: "{n} row", other: "{n} rows" } };
  for (const n of [0, 1, 2, 21, 100]) {
    assert.equal(formatMessage(message, { n }, "ja"), `${n} ${n === 1 ? "row" : "rows"}`);
  }
  const ru = { plural: "n", forms: { one: "one {n}", few: "few {n}", many: "many {n}", other: "other {n}" } };
  assert.equal(formatMessage(ru, { n: 2 }, "ru"), "few 2");
  assert.equal(formatMessage({ ...message, locale: "ja-JP" }, { n: 1 }, "en"), "1 rows");
  assert.equal(formatMessage("{{{n}}}", { n: 1 }), "{1}");
  assert.equal(formatMessage("", { n: 1 }), "");
});

test("NFKC lowercase search and explicit collation locale", () => {
  assert.equal(normalizeSearch("ＡＢＣ ｶﾀｶﾅ E\u0301"), "abc カタカナ é");
  assert.notEqual(normalizeSearch("繁體"), normalizeSearch("繁体"));
  assert.ok(compare("ä", "z", "asc", "sv") > 0);
  assert.ok(compare("ä", "z", "asc", "de") < 0);
});

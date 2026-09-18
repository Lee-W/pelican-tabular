const { test, expect } = require("@playwright/test");

test("two views isolate URL state; grouped filters and collapse compose", async ({ page }) => {
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/integration.html?works.status=ongoing&other.status=planned");
  await expect(page.locator("#works .tabular-row:visible")).toHaveCount(2);
  await expect(page.locator("#other .tabular-row:visible")).toHaveCount(2);
  const headers = page.locator("#other .tabular-group-header:visible");
  await expect(headers).toHaveCount(2);
  await headers.first().click();
  await expect(page.locator("#other .tabular-row:visible")).toHaveCount(1);
  await expect(page.locator("#other [data-count]")).toHaveText("顯示 2 / 8 筆");
  await page.locator("#works [data-clear]").click();
  await expect(page.locator("#works .tabular-row:visible")).toHaveCount(8);
  await expect(page).toHaveURL(/other.status=planned/);
  await page.locator("#other [data-clear]").click();
  await expect(page.locator("#other .tabular-group-header:visible")).toHaveCount(4);
  await headers.first().focus();
  await page.keyboard.press("Enter");
  expect(errors).toEqual([]);
});

test("legacy OSM tags, group headers and sorting share the controller", async ({ page }) => {
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/integration.html");
  const table = page.locator(".osm-place-list");
  await expect(table.locator("tr.osm-place-row:visible")).toHaveCount(3);
  await expect(table.locator(".osm-group-count b").first()).toHaveText("2");
  await table.locator(".osm-badge--tag").filter({ hasText: /^quiet$/ }).first().click();
  await expect(table.locator("tr.osm-place-row:visible")).toHaveCount(2);
  await expect(table.locator(".osm-group-header:visible")).toHaveCount(2);
  await expect(table.locator(".osm-group-count").first()).toHaveText("2026: 1 places");
  await expect(table.locator(".osm-group-count b").first()).toHaveText("1");
  await table.locator(".osm-group-header").first().click();
  await expect(table.locator("tr.osm-place-row:visible")).toHaveCount(1);
  await page.locator(".osm-tag-filter-chip").click();
  await expect(table.locator("tr.osm-place-row:visible")).toHaveCount(1);
  await table.locator(".osm-group-header").first().click();
  await expect(table.locator("tr.osm-place-row:visible")).toHaveCount(3);
  await table.locator("thead button").first().click();
  await expect(table.locator("thead th").first()).toHaveAttribute("aria-sort", "ascending");
  expect(errors).toEqual([]);
});

test("OSM image and map-link adapters survive table migration", async ({ page }) => {
  await page.goto("/integration.html");
  const enabled = await page.locator('script[src*="osm-map.js"]').count();
  test.skip(!enabled, "Pass --osm-source to build_browser_fixtures.py for live OSM assets");
  const table = page.locator(".osm-place-list");
  await expect(table.locator('a[title="OpenStreetMap"]')).toHaveAttribute("href", /mlat=25.03/);
  await table.locator(".osm-list-image-icon").first().click();
  await expect(page.locator("#osm-photo-lightbox")).toHaveClass(/osm-lightbox--active/);
  await expect(page.locator(".osm-lightbox-image")).toHaveAttribute("src", "/sample.svg");
});

for (const size of [1000, 5000]) {
  test(`performance baseline ${size} rows`, async ({ page }, testInfo) => {
    const start = Date.now();
    await page.goto(`/performance-${size}.html`);
    await expect(page.locator("#perf.tabular-ready")).toHaveCount(1);
    const init = Date.now() - start;
    const queryMs = await page.locator("#perf [data-search]").evaluate((input) => {
      const start = performance.now();
      input.value = "Work 1"; input.dispatchEvent(new Event("input", { bubbles: true }));
      return performance.now() - start;
    });
    const expected = Array.from({ length: size }, (_, i) => `Work ${i}`).filter((s) => s.includes("Work 1")).length;
    await expect(page.locator("#perf .tabular-row:visible")).toHaveCount(expected);
    await testInfo.attach("timings", { body: JSON.stringify({ rows: size, initMs: init, queryMs }), contentType: "application/json" });
    console.log(`TABLE_PERF ${JSON.stringify({ rows: size, initMs: init, queryMs })}`);
  });
}

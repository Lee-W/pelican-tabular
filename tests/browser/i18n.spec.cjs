const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

test("component language, canonical filters and plural updates stay independent", async ({ page }) => {
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/i18n.html");
  await expect(page.locator("#ja [data-count]")).toHaveText("2 件中 2 件");
  await expect(page.locator("#en [data-count]")).toHaveText("2 / 2 rows");
  await expect(page.locator("#zh-Hans [data-search]")).toHaveAttribute("placeholder", "Search");
  await page.locator("#en [data-search]").fill("abc");
  await expect(page.locator("#en .tabular-row:visible")).toHaveCount(1);
  await expect(page.locator("#en .tabular-group-count")).toHaveText("1 row");
  await expect(page.locator("#ja .tabular-group-count")).toHaveText("2 件");
  if (await page.locator("#ja [data-filter-toggle]").getAttribute("aria-expanded") === "false")
    await page.locator("#ja [data-filter-toggle]").click();
  await page.locator('#ja [data-value="anime"]').click();
  await expect(page).toHaveURL(/ja.kind=anime/);
  await expect(page.locator("#ja .tabular-group-count")).toHaveText("1 件");
  await page.locator("#en [data-search]").fill("é");
  await expect(page.locator("#en .tabular-row:visible")).toHaveCount(1);
  await page.locator("#en [data-search]").fill("missing");
  await expect(page.locator("#en [data-count]")).toHaveText("0 / 2 rows");
  expect(errors).toEqual([]);
});

test("OSM maps, more-than-ten layers and shared lightbox use the triggering locale", async ({ page }) => {
  test.skip(!fs.existsSync(path.join(__dirname, "../../examples/database/output/osm-i18n.html")),
    "Build paired fixtures with --osm-source for OSM i18n");
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.route("**/unpkg.com/**", (route) => route.abort());
  await page.goto("/osm-i18n.html#place-0");
  for (const [locale, label, all, close] of [["en", "Work", "All (11)", "Close (Esc)"],
    ["ja", "作品", "すべて（11）", "閉じる（Esc）"]]) {
    const map = page.locator(`#osm-${locale}`);
    await expect(map.locator(".osm-map-layer-label")).toContainText(label);
    await expect(map.locator(".osm-map-layer-select option").first()).toHaveText(all);
    await expect(map.locator(".osm-popup-name")).toHaveText(locale === "ja" ? "場所 0" : "Source 0");
    await map.locator(".osm-popup-photo").click();
    await expect(page.locator("#osm-photo-lightbox")).toHaveAttribute("lang", locale);
    await expect(page.locator(".osm-lightbox-close")).toHaveAttribute("aria-label", close);
    await page.keyboard.press("Escape");
  }
  await page.locator("#osm-ja .osm-list-image-icon").first().click();
  await expect(page.locator(".osm-lightbox-image")).toHaveAttribute("alt", "場所の写真");
  await page.keyboard.press("Escape");
  expect(errors).toEqual([]);
});

test("OSM legacy overrides still win and count callbacks remain callable", async ({ page }) => {
  test.skip(!fs.existsSync(path.join(__dirname, "../../examples/database/output/osm-i18n.html")),
    "Build paired fixtures with --osm-source for OSM i18n");
  await page.route("**/unpkg.com/**", (route) => route.abort());
  await page.addInitScript(() => { window.OSM_I18N = {
    resetView: "Custom reset", placeCount: (n) => `Custom ${n}`, close: "Custom close",
  }; });
  await page.goto("/osm-i18n.html");
  await expect(page.locator("#osm-ja .osm-place-list-count")).toHaveText("Custom 11");
  await expect(page.locator("#osm-ja .osm-reset-btn")).toHaveAttribute("title", "Custom reset");
  await page.locator("#osm-ja .osm-list-image-icon").first().click();
  await expect(page.locator(".osm-lightbox-close")).toHaveAttribute("title", "Custom close");
});

test("translated labels and counts are in the initial HTML", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/i18n.html");
  await expect(page.locator("#ja thead")).toContainText("作品名");
  await expect(page.locator("#ja [data-count]")).toHaveText("2 件中 2 件");
  await expect(page.locator("#en .tabular-group-count")).toHaveText("2 rows");
  await context.close();
});

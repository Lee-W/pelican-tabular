const { test, expect } = require("@playwright/test");
const rows = (page) => page.locator("#works .tabular-row:visible");
const filter = (page, field, value) => page.locator(`#works fieldset[data-filter="${field}"] button[data-value="${value}"]`);

test("loads without JavaScript errors and initializes only once", async ({ page }) => {
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/database.html");
  await expect(rows(page)).toHaveCount(8);
  await expect(page.locator("#works [data-count]")).toHaveText("顯示 8 / 8 筆");
  await page.evaluate(() => { Tabular.init(); Tabular.init(); });
  await expect(page.locator("#works thead .tabular-sort-button")).toHaveCount(2);
  expect(errors).toEqual([]);
});

test("URL status, compound filters, search, details and clearing", async ({ page }) => {
  await page.goto("/database.html?works.status=ongoing&utm_source=test#works");
  await expect(rows(page)).toHaveCount(2);
  await page.locator("#works [data-filter-toggle]").click();
  await filter(page, "genres", "科幻").click();
  await filter(page, "genres", "日常").click();
  await page.locator("#works [data-search]").fill("北光");
  await expect(rows(page)).toHaveCount(1);
  await expect(page).toHaveURL(/utm_source=test/);
  await expect(page).toHaveURL(/#works$/);
  const shared = page.url();
  await page.reload();
  await expect(rows(page)).toHaveCount(1);
  await expect(page.locator("#works [data-search]")).toHaveValue("北光");
  await rows(page).locator("[data-expand]").click();
  await expect(page.locator("#works .tabular-detail:visible")).toContainText("安靜");
  await page.locator("#works [data-clear]").click();
  await expect(rows(page)).toHaveCount(8);
  await page.goto(shared);
  await expect(rows(page)).toHaveCount(1);
});

test("year ranges, null dates, reversed range and empty result", async ({ page }) => {
  await page.goto("/database.html?works.released_at.from=2025");
  await expect(rows(page)).toHaveCount(3);
  await page.locator("#works [data-filter-toggle]").click();
  const range = page.locator('#works fieldset[data-filter="released_at"]');
  await range.locator('[data-range="to"]').selectOption("2026");
  await expect(rows(page)).toHaveCount(2);
  await range.locator('[data-range="from"]').selectOption("2027");
  await expect(page.locator("#works [data-error]")).toBeVisible();
  await expect(rows(page)).toHaveCount(2);
  await page.locator("#works [data-search]").fill("沒有這個故事");
  await expect(rows(page)).toHaveCount(0);
  await expect(page.locator("#works [data-empty]")).toBeVisible();
});

test("sort and quick presets share state; details follow their row", async ({ page }) => {
  await page.goto("/database.html");
  await page.locator('#works [data-sort]').selectOption("rating");
  await expect(rows(page).first()).toContainText("星河慢行");
  await rows(page).first().locator("[data-expand]").click();
  await page.locator("#works [data-direction]").click();
  await expect(rows(page).first()).toContainText("明天也在這裡");
  expect(await page.locator('#works [data-detail="0"]').evaluate((e) => e.previousElementSibling.dataset.row)).toBe("0");
  await page.locator('#works [data-preset="1"]').click();
  await expect(rows(page)).toHaveCount(2);
  await page.locator('#works [data-preset="1"]').click();
  await expect(rows(page)).toHaveCount(8);
});

test("browser navigation restores query state", async ({ page }) => {
  await page.goto("/database.html?works.status=ongoing");
  await expect(rows(page)).toHaveCount(2);
  await page.evaluate(() => {
    history.pushState(null, "", "?works.status=completed");
    dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(rows(page)).toHaveCount(2);
  await expect(rows(page).first()).toContainText("雨停之前的書店");
  await page.goBack();
  await expect(rows(page).first()).toContainText("星河慢行");
});

for (const width of [360, 768, 1280]) {
  for (const scheme of ["light", "dark"]) {
    test(`responsive layout ${width}px ${scheme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("/database.html");
      await expect(rows(page)).toHaveCount(8);
      await page.locator("#works [data-filter-toggle]").click();
      await rows(page).first().locator("[data-expand]").click();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (width === 360) await expect(page.locator("#works thead")).toBeHidden();
      else await expect(page.locator("#works thead")).toBeVisible();
      await page.screenshot({ path: `test-results/database-${width}-${scheme}.png`, fullPage: true });
    });
  }
}

test("static page remains readable without JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("http://127.0.0.1:8765/database.html");
  await expect(rows(page)).toHaveCount(8);
  await expect(page.locator("#works .tabular-detail:visible")).toHaveCount(8);
  await expect(page.locator("#works .tabular-controls")).toBeHidden();
  await context.close();
});

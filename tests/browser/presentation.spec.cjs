const { test, expect } = require('@playwright/test');

async function expectPanel(page, id, expanded) {
  const view = page.locator(`#${id}`);
  await expect(view.locator('[data-filter-toggle]')).toHaveAttribute('aria-expanded', String(expanded));
  if (expanded) await expect(view.locator('.tabular-filters')).toBeVisible();
  else await expect(view.locator('.tabular-filters')).toBeHidden();
}

for (const colorScheme of ['light', 'dark']) {
  test(`view legends stay neutral within theme admonition styles (${colorScheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await page.goto('/presentation.html');
    const legend = page.locator('#auto .tabular-legend');
    const summary = legend.locator('summary');
    for (const width of [360, 1280]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(legend).toHaveCSS('border-inline-start-width', '0px');
      await expect(summary).toHaveCSS('font-size', '15px');
      await expect(summary).toHaveCSS('font-weight', '400');
      await expect(summary).toHaveCSS('margin-bottom', '0px');
      await expect(summary).toHaveCSS('color', await legend.evaluate(el => getComputedStyle(el).color));
      await summary.hover();
      await expect(summary).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
      await summary.click();
      await expect(legend).toHaveAttribute('open', '');
      await expect(summary).toHaveCSS('border-bottom-width', '0px');
      await expect(legend.locator('p').first()).toHaveCSS('padding-left', '0px');
      await expect(legend.locator('p').first()).toHaveCSS('margin-top', '6px');
      await summary.click();
    }
    await expect(page.locator('.outside-details')).toHaveCSS('border-inline-start-width', '3px');
    await expect(page.locator('.outside-details summary')).toHaveCSS('font-weight', '700');
  });
}

for (const width of [360, 680, 681, 1280]) {
  test(`filter defaults and explicit preferences at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/presentation.html');
    await expectPanel(page, 'auto', width > 680);
    await expectPanel(page, 'open', true);
    await expectPanel(page, 'closed', false);
    await expect(page.locator('#empty [data-filter-toggle]')).toBeHidden();
    await expect(page.locator('#empty .tabular-filters')).toBeHidden();
    await expect(page.locator('#empty [data-empty]')).toBeVisible();
    await page.reload();
    await expectPanel(page, 'auto', width > 680);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('manual panel choices survive search, sorting, resizing and repeated initialization', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.goto('/presentation.html');
  await page.setViewportSize({ width: 360, height: 1000 });
  await expectPanel(page, 'auto', false);
  const view = page.locator('#auto');
  await view.locator('[data-filter-toggle]').focus();
  await page.keyboard.press('Enter');
  await expectPanel(page, 'auto', true);
  await view.locator('[data-search]').fill('Research');
  await expect(view.locator('.tabular-row:visible')).toHaveCount(1);
  await view.locator('[data-sort]').selectOption('employee');
  await expectPanel(page, 'auto', true);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await expectPanel(page, 'auto', true);
  await view.locator('[data-filter-toggle]').click();
  await expectPanel(page, 'auto', false);
  await view.locator('[data-clear]').click();
  await page.setViewportSize({ width: 360, height: 1000 });
  await page.setViewportSize({ width: 1280, height: 1000 });
  await expectPanel(page, 'auto', false);
  await expectPanel(page, 'open', true);
  await expectPanel(page, 'closed', false);
  await page.evaluate(() => { Tabular.init(); Tabular.init(); });
  await view.locator('[data-filter-toggle]').click();
  await expectPanel(page, 'auto', true);
});

test('mobile labels, long values and link lists work with reordered non-catalog fields', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 1000 });
  await page.goto('/presentation.html');
  const row = page.locator('#auto .tabular-row').first();
  const title = await row.locator('.tabular-title').boundingBox();
  const metadata = await row.locator('.tabular-meta').evaluateAll(cells => cells.map(cell => ({
    top: cell.getBoundingClientRect().top,
    field: cell.dataset.field,
    label: cell.dataset.label,
    content: getComputedStyle(cell, '::before').content,
    fontSize: getComputedStyle(cell, '::before').fontSize,
    fontWeight: getComputedStyle(cell, '::before').fontWeight,
    labelHeight: parseFloat(getComputedStyle(cell, '::before').height),
    lineHeight: parseFloat(getComputedStyle(cell, '::before').lineHeight),
  })));
  expect(metadata.map(cell => cell.field)).toEqual(['team', 'references', 'level']);
  for (const cell of metadata) {
    expect(cell.top).toBeGreaterThanOrEqual(title.y + title.height);
    expect(cell.content.replaceAll('"', '')).toBe(cell.label + ':');
    expect(cell.fontSize).toBe('15px');
    expect(cell.fontWeight).toBe('650');
    expect(cell.labelHeight).toBeLessThanOrEqual(cell.lineHeight + 1);
  }
  const list = row.locator('[data-field="references"] ul');
  const listBox = await list.boundingBox();
  const linkBox = await list.locator('a').first().boundingBox();
  expect(Math.abs(listBox.x - linkBox.x)).toBeLessThan(1);
  await expect(page.locator('#auto [data-search]')).toHaveCSS('font-size', '16px');
  await expect(row.locator('.tabular-title')).toHaveCSS('font-size', '18px');
  await expect(page.locator('#auto thead')).toBeHidden();
  await expect(page.locator('#table thead')).toBeVisible();
  // Resetting view list indentation must not reset ordinary article lists.
  expect(await page.locator('.outside-list').evaluate(el => parseFloat(getComputedStyle(el).paddingLeft))).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/presentation-mobile.png', fullPage: true });
});

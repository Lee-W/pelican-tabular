const { test, expect } = require('@playwright/test');

for (const [id, expand, collapse] of [
  ['plain', '全部展開', '全部收合'],
  ['responsive', 'Expand all', 'Collapse all'],
  ['table', 'すべて展開', 'すべて折りたたむ'],
]) {
  test(`shared hierarchy, keyboard, sorting and bulk controls in ${id}`, async ({ page }) => {
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('/groups.html');
    const root = page.locator(`#${id}`);
    const rows = root.locator('[data-tabular-group-row]:visible');
    const headers = root.locator('[data-tabular-group]');
    await expect(rows).toHaveCount(6);
    await expect(headers).toHaveCount(9);
    await expect(root.getByRole('button', { name: expand, exact: true })).toBeDisabled();
    await root.getByRole('button', { name: collapse, exact: true }).click();
    await expect(rows).toHaveCount(0);
    await expect(root.locator('[data-tabular-group]:visible')).toHaveCount(2);
    await expect(root.getByRole('button', { name: collapse, exact: true })).toBeDisabled();
    await root.getByRole('button', { name: expand, exact: true }).click();
    await expect(rows).toHaveCount(6);
    await headers.first().focus();
    await page.keyboard.press('Space');
    await expect(rows).toHaveCount(1);
    await page.keyboard.press('Enter');
    await expect(rows).toHaveCount(6);
    await root.locator('th button').first().click();
    await expect(root.locator('[data-tabular-group-row] td:first-child')).toContainText(['1', '2', '7', '3', '5', '6']);
    const leaf = root.locator('[data-tabular-group="2"]').first();
    const anchor = await leaf.getAttribute('id');
    await root.getByRole('button', { name: collapse, exact: true }).click();
    await page.evaluate(anchor => { location.hash = anchor; }, anchor);
    await expect(leaf).toBeVisible();
    await expect(rows).toHaveCount(2);
    await page.evaluate(id => {
      const table = document.querySelector(`#${id} table`);
      Tabular.initTable(table).setGroupsExpanded(true);
      Tabular.initTable(table);
    }, id);
    await expect(root.locator('.tabular-group-controls')).toHaveCount(1);
    await expect(rows).toHaveCount(6);
    expect(errors).toEqual([]);
  });

  test(`shared search reveals hidden group names in ${id}`, async ({ page }) => {
    await page.goto('/groups.html');
    const root = page.locator(`#${id}`);
    await root.getByRole('button', { name: collapse, exact: true }).click();
    for (const [query, count] of [['Taipei', 3], ['Xinyi', 2], ['Japan', 1]]) {
      if (id === 'plain') {
        await page.evaluate(query => {
          const controller = Tabular.initTable(document.querySelector('#plain table'));
          controller.getState().q = query;
          controller.update();
        }, query);
      } else await root.getByRole('searchbox').fill(query);
      await expect(root.locator('[data-tabular-group-row]:visible')).toHaveCount(count);
    }
    await expect(root.locator('[data-tabular-group-count]:visible').first()).toContainText('1');
  });
}

for (const width of [390, 1200]) {
  test(`shared hierarchy has aligned rows and readable theme colors at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/groups.html');
    const brandColors = new Map();
    for (const brand of ['main', 'travlog']) {
      for (const theme of ['light', 'dark']) {
        await page.evaluate(({ brand, theme }) => {
          document.body.className = `site-${brand}`;
          document.documentElement.className = `theme-${theme}`;
        }, { brand, theme });
        for (const id of ['plain', 'responsive', 'table']) {
          const root = page.locator(`#${id}`);
          const padding = await root.locator('[data-tabular-group] td').evaluateAll(cells =>
            cells.slice(0, 3).map(cell => parseFloat(getComputedStyle(cell).paddingInlineStart)));
          expect(padding[0]).toBeLessThan(padding[1]);
          expect(padding[1]).toBeLessThan(padding[2]);
          const readPalette = () => root.locator('[data-tabular-group] td').evaluateAll(cells =>
            cells.slice(0, 3).map(cell => {
              const style = getComputedStyle(cell);
              const canvas = document.createElement('canvas').getContext('2d');
              function rgb(css) {
                canvas.fillStyle = css; canvas.fillRect(0, 0, 1, 1);
                return Array.from(canvas.getImageData(0, 0, 1, 1).data).slice(0, 3);
              }
              const stops = [...style.backgroundImage.matchAll(/(?:color\(srgb [^)]+\)|rgba?\([^)]+\))/g)];
              const title = cell.querySelector('[data-tabular-group-title]');
              const count = cell.querySelector('[data-tabular-group-count]');
              const textColors = [title, count, ...count.querySelectorAll('*')]
                .map(el => rgb(getComputedStyle(el).color));
              return [textColors[0], rgb(stops.at(-1)[0]), textColors,
                rgb(getComputedStyle(count).backgroundColor)];
            }));
          const palette = await readPalette();
          function luminance(rgb) {
            return rgb.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
              .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
          }
          function contrast(a, b) {
            const [high, low] = [luminance(a), luminance(b)].sort((a, b) => b - a);
            return (high + .05) / (low + .05);
          }
          palette.forEach(([text, background, textColors, countBackground]) => {
            expect(contrast(text, background)).toBeGreaterThanOrEqual(4.5);
            textColors.forEach(color => expect(color).toEqual(text));
            expect(contrast(text, countBackground)).toBeGreaterThanOrEqual(4.5);
          });
          await root.locator('[data-tabular-group]').first().hover();
          (await readPalette()).forEach(([text, background, , countBackground]) => {
            expect(contrast(text, background)).toBeGreaterThanOrEqual(4.5);
            expect(contrast(text, countBackground)).toBeGreaterThanOrEqual(4.5);
          });
          await page.mouse.move(0, 0);
          const key = `${id}-${theme}`;
          if (brand === 'main') brandColors.set(key, palette[0][1]);
          else expect(palette[0][1]).not.toEqual(brandColors.get(key));
          expect(contrast(palette[0][1], palette[1][1])).toBeGreaterThan(3);
          const title = await root.locator('[data-tabular-group="2"] [data-tabular-group-title]').first().boundingBox();
          const rowStart = await root.locator('[data-tabular-group-row] td:first-child').first().evaluate(cell =>
            cell.getBoundingClientRect().x + parseFloat(getComputedStyle(cell).paddingInlineStart));
          expect(Math.abs(rowStart - title.x)).toBeLessThan(2);
          if (id !== 'table' && width < 680) {
            const cells = root.locator('[data-tabular-group-row]').first().locator('td');
            const first = await cells.first().boundingBox();
            const second = await cells.nth(1).boundingBox();
            expect(first.y).toBeLessThan(second.y);
          }
          const titleBox = await root.locator('[data-tabular-group-title]').first().boundingBox();
          const countBox = await root.locator('[data-tabular-group-count]').first().boundingBox();
          expect(Math.abs(titleBox.y - countBox.y)).toBeLessThan(10);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath(`${brand}-${theme}.png`), fullPage: true });
      }
    }
  });
}

for (const width of [390, 1200]) {
  test(`tables fill a flex article and keep their width when filtering at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/groups.html');
    await page.evaluate(width => {
      const article = document.querySelector('.post-content');
      Object.assign(article.style, { display: 'flex', flexDirection: 'column', alignItems: 'center' });
      // Consuming sites widen plain tables with negative margins on desktop.
      if (width > 1000) document.querySelector('#plain').style.marginInline = '-40px';
    }, width);
    for (const id of ['plain', 'responsive', 'table']) {
      const root = page.locator(`#${id}`);
      const expectedWidth = await root.evaluate(el => {
        const parent = el.parentElement;
        const style = getComputedStyle(parent), own = getComputedStyle(el);
        return parent.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
          - parseFloat(own.marginLeft) - parseFloat(own.marginRight);
      });
      async function expectWidth() {
        expect((await root.boundingBox()).width).toBeCloseTo(expectedWidth, 0);
        expect((await root.locator('table').boundingBox()).width).toBeCloseTo(expectedWidth, 0);
      }
      await expectWidth();
      await root.locator('.tabular-group-controls button').nth(1).click();
      await expectWidth();
      for (const query of ['Ikebukuro', 'no-such-venue', '']) {
        if (id === 'plain') await root.locator('table').evaluate((table, query) => {
          const controller = Tabular.initTable(table);
          controller.getState().q = query;
          controller.update();
        }, query);
        else await root.getByRole('searchbox').fill(query);
        await expectWidth();
      }
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('shared server-rendered hierarchy remains readable without JavaScript', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto(`${baseURL}/groups.html`);
  await expect(page.locator('[data-tabular-group-row]')).toHaveCount(18);
  await expect(page.locator('.tabular-group-controls')).toHaveCount(0);
  await expect(page.locator('#plain td[data-field="capacity"]').first()).toHaveAttribute('data-label', 'Capacity');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await context.close();
});

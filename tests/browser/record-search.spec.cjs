const { test, expect } = require('@playwright/test');

test('row search metadata supplements cell text with the shared controller', async ({ page }) => {
  await page.goto('/groups.html');
  await page.evaluate(() => {
    const root = document.createElement('div');
    root.id = 'record-search';
    root.className = 'osm-place-list-wrapper';
    root.innerHTML = '<table class="osm-place-list"><thead><tr><th>Name</th></tr></thead><tbody>' +
      '<tr data-tabular-search="custom-field Nested value https://example.test/path"><td>Alpha</td></tr>' +
      '<tr><td>Beta</td></tr></tbody></table>';
    document.body.append(root);
    Tabular.initTable(root.querySelector('table'));
  });
  const rows = page.locator('#record-search tbody tr:visible');
  for (const [query, names] of [
    ['custom-field', ['Alpha']], ['Nested value', ['Alpha']],
    ['example.test/path', ['Alpha']], ['Beta', ['Beta']], ['missing', []],
    ['', ['Alpha', 'Beta']],
  ]) {
    await page.evaluate(query => {
      const controller = Tabular.initTable(document.querySelector('#record-search table'));
      controller.getState().q = query;
      controller.update();
    }, query);
    await expect(rows).toHaveCount(names.length);
    await expect(rows).toHaveText(names);
  }
});

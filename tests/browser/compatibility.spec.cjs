const { test, expect } = require('@playwright/test');

for (const subsite of ['', '/ja']) {
  test(`unchanged legacy URLs work without database controls ${subsite || '/'}`, async ({ page }) => {
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`${subsite}/compat-main-legacy.html`);
    await expect(page.locator('.compat-cv th button').first()).toBeVisible();
    expect(await page.evaluate(() => typeof Tabular.initViews)).toBe('undefined');
    await expect(page.locator('script[src*="pelican_tabular"]')).toHaveCount(0);
    await expect(page.locator('link[href*="pelican_tabular"]')).toHaveCount(0);
    await expect(page.locator('.compat-cv .osm-place-list-count')).toBeEmpty();
    const sort = page.locator('.compat-cv th button').first();
    await expect(sort).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)');
    await sort.focus(); await page.keyboard.press('Enter');
    await expect(page.locator('.compat-cv th').first()).toHaveAttribute('aria-sort', 'ascending');
    const group = page.locator('.compat-ranking .osm-group-header').first();
    await group.click();
    await expect(group).toHaveAttribute('aria-expanded', 'false');
    const places = page.locator('.osm-place-list').last();
    await places.locator('.osm-badge--tag').filter({hasText: /^quiet$/}).first().click();
    await expect(places.locator('.osm-place-row:visible')).toHaveCount(2);
    await page.locator('.osm-tag-filter-chip').click();
    await expect(places.locator('.osm-place-row:visible')).toHaveCount(3);
    expect(errors).toEqual([]);
  });
}

for (const scheme of ['light', 'dark']) {
  test(`legacy palettes survive manual and system theme selection ${scheme}`, async ({page}) => {
    await page.emulateMedia({colorScheme:scheme});
    await page.goto('/compat-main-legacy.html');
    const first = page.locator('.osm-place-list').last();
    const group = first.locator('.osm-group-header td').first();
    await expect(group).toHaveCSS('background-color', scheme === 'light' ? 'rgb(201, 216, 243)' : 'rgb(61, 83, 121)');
    const opposite = scheme === 'dark' ? 'light' : 'dark';
    await page.evaluate(t => document.documentElement.className = `theme-${t}`, opposite);
    await expect(group).toHaveCSS('background-color', opposite === 'light' ? 'rgb(201, 216, 243)' : 'rgb(61, 83, 121)');
    await expect(first.locator('.osm-place-row td').first()).toHaveCSS('background-color', opposite === 'light' ? 'rgb(255, 255, 255)' : 'rgb(30, 30, 30)');
    await expect(first.locator('.osm-sort-icon').first()).toHaveCSS('opacity', opposite === 'light' ? '0.3' : '0.4');
  });
}

for (const brand of ['main', 'travlog']) {
  for (const width of [360, 1280]) {
    test(`optional view inherits ${brand} theme at ${width}px`, async ({page}) => {
      const errors=[]; page.on('pageerror', e=>errors.push(e.message));
      await page.setViewportSize({width,height:1000});
      await page.goto(`/ja/compat-${brand}-modern.html?works.status=ongoing`);
      await expect(page.locator('#works.tabular-ready')).toHaveCount(1);
      await expect(page.locator('#works .tabular-row:visible')).toHaveCount(2);
      await expect(page.locator('script[src*="pelican_osm"]')).toHaveCount(0);
      await expect(page.locator('script[src="/ja/static/pelican_tabular/js/tabular.js"]')).toHaveCount(1);
      if (await page.locator('[data-filter-toggle]').getAttribute('aria-expanded') === 'false') await page.locator('[data-filter-toggle]').click();
      const buttons=page.locator('fieldset[data-filter="format"] button');
      await expect(buttons.first()).toHaveCSS('min-height', '44px');
      const rectangles=await buttons.evaluateAll(bs=>bs.slice(0,2).map(b=>({top:b.getBoundingClientRect().top,height:b.getBoundingClientRect().height,display:getComputedStyle(b).display})));
      expect(rectangles[0].top).toBe(rectangles[1].top);
      expect(rectangles[0].height).toBeGreaterThanOrEqual(44);
      expect(rectangles[0].display).toBe('inline-block');
      expect(await page.locator('#works').evaluate(el=>getComputedStyle(el).getPropertyValue('--tabular-accent').trim())).toBe(brand === 'main' ? '#b3573a' : '#4a8a63');
      expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.locator('[data-clear]').click();
      await page.locator('.tabular-row [data-expand]').first().focus();
      await page.keyboard.press('Enter');
      await expect(page.locator('.tabular-detail:visible')).toHaveCount(1);
      await page.evaluate(()=>document.documentElement.className='theme-dark');
      await expect(page.locator('#works')).toHaveCSS('background-color','rgb(34, 36, 38)');
      await expect(page.locator('#works [data-clear]')).toHaveCSS('background-color','rgb(34, 36, 38)');
      await expect(page.locator('#works [data-clear]')).toHaveCSS('color','rgb(225, 227, 230)');
      await page.screenshot({path:`test-results/attila-${brand}-${width}.png`,fullPage:true});
      expect(errors).toEqual([]);
    });
  }
}

test('mixed asset bundles share the same controller in either loading order', async ({page})=>{
  await page.goto('/compat-travlog-mixed.html');
  const button=page.locator('.compat-cv th button').first();
  const identity=await page.evaluate(()=>{
    const before=Tabular.initTable(document.querySelector('.osm-place-list'));
    Tabular.init();
    return before === Tabular.initTable(document.querySelector('.osm-place-list'));
  });
  expect(identity).toBe(true);
  await button.click();
  await expect(page.locator('.compat-cv th').first()).toHaveAttribute('aria-sort','ascending');
  // Load the legacy bundle again after the optional bundle has initialized.
  await page.addScriptTag({url:'/static/pelican_osm/js/osm-map.js'});
  await button.click();
  await expect(page.locator('.compat-cv th').first()).toHaveAttribute('aria-sort','descending');
  await expect(page.locator('.compat-cv th').first().locator('button')).toHaveCount(1);
  await page.locator('#works [data-preset="0"]').click();
  await expect(page.locator('#works .tabular-row:visible')).toHaveCount(2);
});

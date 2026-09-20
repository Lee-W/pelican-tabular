const { defineConfig } = require("@playwright/test");
const port = process.env.TABULAR_TEST_PORT || "8765";
const baseURL = `http://127.0.0.1:${port}`;

module.exports = defineConfig({
  testDir: "tests/browser",
  fullyParallel: true,
  workers: 2,
  use: { baseURL, browserName: "chromium" },
  webServer: {
    command: `python3 scripts/serve_browser_fixtures.py --port ${port}`,
    url: `${baseURL}/database.html`,
    reuseExistingServer: !process.env.CI,
  },
});

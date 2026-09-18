const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/browser",
  fullyParallel: true,
  workers: 2,
  use: { baseURL: "http://127.0.0.1:8765", browserName: "chromium" },
  webServer: {
    command: "python3 -m http.server 8765 --bind 127.0.0.1 --directory examples/database/output",
    url: "http://127.0.0.1:8765/database.html",
    reuseExistingServer: !process.env.CI,
  },
});

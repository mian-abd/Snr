import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:41733', browserName: 'chromium', channel: 'chrome' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 41733 --strictPort',
    url: 'http://127.0.0.1:41733',
    reuseExistingServer: false,
  },
})

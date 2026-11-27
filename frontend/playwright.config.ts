import { defineConfig } from '@playwright/test'

// Locally the tests drive the installed Chrome. In CI there is none, so set PW_BUNDLED=1
// to use the Chromium that `playwright install chromium` downloads.
const channel = process.env.PW_BUNDLED ? undefined : 'chrome'
// The accessibility sweep reads real data, so it needs the built site served by the backend.
const a11yUrl = process.env.A11Y_URL ?? 'http://127.0.0.1:8012'

export default defineConfig({
  testDir: './e2e',
  projects: [
    {
      name: 'smoke',
      testMatch: 'smoke.spec.ts',
      use: { baseURL: 'http://127.0.0.1:41733', browserName: 'chromium', channel },
    },
    {
      name: 'a11y',
      testMatch: /(a11y|keyboard).spec.ts/,
      use: { baseURL: a11yUrl, browserName: 'chromium', channel },
    },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 41733 --strictPort',
    url: 'http://127.0.0.1:41733',
    reuseExistingServer: false,
  },
})

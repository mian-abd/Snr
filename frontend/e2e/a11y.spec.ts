import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

/**
 * Accessibility sweep: every page in both themes, run against the real backend (default
 * http://127.0.0.1:8012, or A11Y_URL) so charts, tables and lazy sections hold real data.
 * Serious and critical violations fail the test; moderate and minor ones are listed.
 */

const pages: Array<{ name: string; hash: string }> = [
  { name: 'Home', hash: '#/' },
  { name: 'Router', hash: '#/router' },
  { name: 'Models', hash: '#/models' },
  { name: 'Model page', hash: '#/models/gemma-4-26b' },
  { name: 'Compare', hash: '#/compare?models=gemma-4-26b,mercury-3' },
  { name: 'Research', hash: '#/research' },
  { name: 'Prompts', hash: '#/prompts' },
  { name: 'Prompt page', hash: '#/prompts/gsm8k-test-0008' },
  { name: 'FAQ', hash: '#/faq' },
  { name: 'Lab', hash: '#/lab' },
]

const tags = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']

async function scrollThrough(page: Page) {
  // Scroll in steps so lazy sections mount, then come back to the top.
  let last = -1
  for (let step = 0; step < 80; step += 1) {
    const done = await page.evaluate(() => {
      window.scrollBy(0, Math.round(window.innerHeight * 0.8))
      return window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2
    })
    await page.waitForTimeout(60)
    const height = await page.evaluate(() => document.documentElement.scrollHeight)
    if (done && height === last) break
    last = height
  }
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => window.scrollTo(0, 0))
}

async function scan(page: Page, label: string) {
  // Colors are read mid-fade otherwise: let entrance animations finish first.
  await page.evaluate(() => Promise.all(document.getAnimations()
    .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime))
    .map((animation) => animation.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(tags).analyze()
  const describe = (items: typeof violations) =>
    items.map((v) => `${v.id} (${v.impact}) x${v.nodes.length}: ${v.help}\n${v.nodes.slice(0, 4).map((n) => `    ${n.target.join(' ')}`).join('\n')}`)
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  const minor = violations.filter((v) => v.impact !== 'serious' && v.impact !== 'critical')
  if (minor.length) console.log(`[a11y] ${label}: ${minor.length} moderate/minor\n  ${describe(minor).join('\n  ')}`)
  expect(blocking, `${label}\n${describe(blocking).join('\n')}`).toEqual([])
}

for (const theme of ['light', 'dark'] as const) {
  test.describe(`${theme} theme`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem('router-theme', value), theme)
      // The sweep reads; it must never start a live model call.
      await page.route('**/api/v1/**', (route) => (route.request().method() === 'GET' ? route.continue() : route.abort()))
    })

    for (const entry of pages) {
      test(`${entry.name} has no serious or critical violations`, async ({ page }) => {
        await page.goto(`/${entry.hash}`)
        await expect(page.locator('main h1').first()).toBeVisible()
        await expect(page.locator('main [aria-busy="true"]')).toHaveCount(0)
        await scrollThrough(page)
        await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
        await scan(page, `${entry.name} (${theme})`)
      })
    }

    test('search palette has no serious or critical violations', async ({ page }) => {
      await page.goto('/#/')
      await expect(page.locator('main h1').first()).toBeVisible()
      await page.keyboard.press('Control+k')
      const dialog = page.getByRole('dialog', { name: 'Search the site' })
      await expect(dialog).toBeVisible()
      await expect(dialog.getByRole('option').first()).toBeVisible()
      await scan(page, `Search palette (${theme})`)
    })
  })
}

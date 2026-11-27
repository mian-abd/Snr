import { expect, test } from '@playwright/test'

// Keyboard behavior, against the real backend like the accessibility sweep. Nothing here
// presses Run prompt or a Compare send button, so no live model call can start.

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', (route) => (route.request().method() === 'GET' ? route.continue() : route.abort()))
})

test('the skip link is the first stop and moves focus to the content without changing the route', async ({ page }) => {
  await page.goto('/#/faq')
  await expect(page.locator('main h1').first()).toBeVisible()
  await page.keyboard.press('Tab')
  const skip = page.getByRole('link', { name: 'Skip to content' })
  await expect(skip).toBeFocused()
  await expect(skip).toBeInViewport()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
  expect(new URL(page.url()).hash).toBe('#/faq')
})

test('every control reached by Tab shows a focus indicator', async ({ page }) => {
  await page.goto('/#/models')
  await expect(page.locator('main h1').first()).toBeVisible()
  const missing: string[] = []
  for (let step = 0; step < 25; step += 1) {
    await page.keyboard.press('Tab')
    const state = await page.evaluate(() => {
      const element = document.activeElement
      if (!element || element === document.body) return null
      const style = getComputedStyle(element)
      const ring = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0
      const shadow = style.boxShadow !== 'none'
      // Some controls draw the ring on a wrapper or pseudo-element that follows :focus-within or :focus-visible.
      const wrapper = element.closest('[class]')?.parentElement
      const wrapped = !!wrapper && getComputedStyle(wrapper).boxShadow !== 'none' && wrapper.matches(':focus-within')
      return { visible: ring || shadow || wrapped, name: `${element.tagName.toLowerCase()} ${(element.getAttribute('aria-label') ?? element.textContent ?? '').trim().slice(0, 40)}` }
    })
    if (state && !state.visible) missing.push(state.name)
  }
  expect(missing).toEqual([])
})

test('the search palette is a modal dialog that takes focus, closes on Escape, and gives focus back', async ({ page }) => {
  await page.goto('/#/')
  await expect(page.locator('main h1').first()).toBeVisible()
  const opener = page.getByRole('button', { name: 'Search' })
  await opener.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Search the site' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAttribute('aria-modal', 'true')
  await expect(dialog.getByRole('combobox')).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('combobox')).not.toBeFocused()
  // Focus stays inside the dialog.
  expect(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'))).toBe(true)
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(opener).toBeFocused()
  await page.keyboard.press('Control+k')
  await expect(dialog).toBeVisible()
  await page.keyboard.press('Control+k')
  await expect(dialog).toBeHidden()
})

test('the arrow keys move the priority slider and the readout follows', async ({ page }) => {
  await page.goto('/#/research?section=priorities')
  const slider = page.getByRole('slider').first()
  await expect(slider).toBeVisible()
  await slider.focus()
  const before = await slider.inputValue()
  await page.keyboard.press('ArrowRight')
  expect(await slider.inputValue()).not.toBe(before)
  await page.keyboard.press('ArrowLeft')
  expect(await slider.inputValue()).toBe(before)
  await page.keyboard.press('End')
  expect(await slider.inputValue()).toBe(await slider.getAttribute('max'))
  await page.keyboard.press('Home')
  expect(await slider.inputValue()).toBe(await slider.getAttribute('min'))
})

test('the router weight sliders move with the arrow keys', async ({ page }) => {
  await page.goto('/#/router')
  await expect(page.locator('main h1').first()).toBeVisible()
  await page.getByText('Advanced', { exact: false }).first().click()
  const slider = page.getByRole('slider', { name: /Cost weight/ })
  await slider.focus()
  const before = Number(await slider.inputValue())
  await page.keyboard.press('ArrowRight')
  expect(Number(await slider.inputValue())).toBeGreaterThan(before)
})

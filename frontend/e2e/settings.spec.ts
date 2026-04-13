import { test, expect } from '@playwright/test'
import { login, openNav } from './helpers'

test('settings lassen sich ohne inhaltliche aenderung speichern', async ({ page }) => {
  await login(page)
  await openNav(page, 'Settings')
  await expect(page.getByRole('heading', { name: /^settings$/i })).toBeVisible()

  await page.getByRole('button', { name: /effects/i }).click()
  const uiSoundSwitch = page.getByRole('switch', { name: /enable ui sound effects/i })
  const wasEnabled = (await uiSoundSwitch.getAttribute('aria-checked')) === 'true'

  await uiSoundSwitch.click()
  await page.getByRole('button', { name: /save settings/i }).click()
  await expect(page.getByText(/settings saved/i)).toBeVisible()

  if (wasEnabled !== ((await uiSoundSwitch.getAttribute('aria-checked')) === 'true')) {
    await uiSoundSwitch.click()
  }
  await page.getByRole('button', { name: /save settings/i }).click()
  await expect(page.getByText(/settings saved/i)).toBeVisible()
})

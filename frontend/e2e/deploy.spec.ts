import { test, expect } from '@playwright/test'
import { login, openNav, uniqueName } from './helpers'

test('deploy seite erzeugt register key und installer-ausgabe', async ({ page }) => {
  await login(page)
  await openNav(page, 'Deploy')

  await expect(page.getByRole('heading', { name: /deploy agent/i })).toBeVisible()
  await page.getByRole('button', { name: /generate key|new key/i }).click()

  await expect(page.locator('code').filter({ hasText: /^[a-f0-9]{32}$/i })).toBeVisible()
  await expect(page.getByText(/quick install/i)).toBeVisible()

  const customAgentId = uniqueName('e2e-deploy')
  await page.getByPlaceholder(/optional — defaults to hostname/i).fill(customAgentId)
  await expect(page.locator('pre').filter({ hasText: customAgentId }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /copy command/i })).toBeVisible()
})

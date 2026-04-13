import { test, expect } from '@playwright/test'
import { login, uniqueName } from './helpers'

test('ping target kann angelegt, geprueft und entfernt werden', async ({ page }) => {
  const targetName = uniqueName('e2e-ping')

  await login(page)
  await page.getByRole('button', { name: /\+ ping target/i }).click()
  await page.getByPlaceholder(/fritz!box/i).fill(targetName)
  await page.getByPlaceholder(/192\.168\.178\.1/i).fill('127.0.0.1')
  await page.getByRole('button', { name: /add ping target/i }).click()

  const row = page.locator('tr').filter({ hasText: targetName })
  await expect(row).toBeVisible()
  await row.click()

  await expect(page.getByRole('heading', { name: new RegExp(targetName, 'i') })).toBeVisible()
  await page.getByRole('button', { name: /ping check/i }).click()
  await expect(page.getByText(/ping target reachable|ping target unreachable/i)).toBeVisible()

  await page.getByRole('button', { name: /remove vm/i }).click()
  await page.getByRole('button', { name: /^confirm$/i }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('tr').filter({ hasText: targetName })).toHaveCount(0)
})

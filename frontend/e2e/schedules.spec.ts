import { test, expect } from '@playwright/test'
import { login, openNav, uniqueName } from './helpers'

test('schedule kann erstellt und wieder geloescht werden', async ({ page }) => {
  const scheduleName = uniqueName('e2e-schedule')

  await login(page)
  await openNav(page, 'Schedules')
  await page.getByRole('button', { name: /\+ new schedule/i }).click()
  await page.getByPlaceholder(/nightly patch/i).fill(scheduleName)
  await page.getByRole('button', { name: /create schedule/i }).click()

  const row = page.locator('tr').filter({ hasText: scheduleName })
  await expect(row).toBeVisible()

  await row.locator('button').last().click()
  await page.getByRole('button', { name: /^delete$/i }).click()
  await expect(row).toHaveCount(0)
})

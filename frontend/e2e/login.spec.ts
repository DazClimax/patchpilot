import { test, expect } from '@playwright/test'
import { login } from './helpers'

test('login laedt das dashboard erfolgreich', async ({ page }) => {
  await login(page)
  await expect(page.getByText(/systems online/i)).toBeVisible()
  await expect(page.getByText(/pending updates/i)).toBeVisible()
})

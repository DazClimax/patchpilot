import { test, expect } from '@playwright/test'
import { login } from './helpers'
import { getLinuxAgentId } from './env'

test('dashboard kann patch all triggern', async ({ page }) => {
  const agentId = getLinuxAgentId()

  await login(page)
  await page.goto(`/vm/${agentId}`, { waitUntil: 'domcontentloaded' })
  const before = await page.locator('tbody tr').filter({ hasText: /PATCH/i }).count()

  await page.goto('/', { waitUntil: 'domcontentloaded' })
  const updateAllButton = page.getByRole('button', { name: /update all \(/i })
  await expect(updateAllButton).toBeVisible()
  await expect.poll(async () => await updateAllButton.textContent(), { timeout: 10_000 }).not.toBeNull()
  await expect.poll(async () => await updateAllButton.isDisabled(), { timeout: 10_000 }).toBe(false)

  await updateAllButton.click()
  await page.getByRole('button', { name: /^ok$/i }).click()

  await page.goto(`/vm/${agentId}`, { waitUntil: 'domcontentloaded' })
  await expect
    .poll(async () => {
      return await page.locator('tbody tr').filter({ hasText: /PATCH/i }).count()
    }, { timeout: 20_000, intervals: [500, 1000, 2000] })
    .toBeGreaterThan(before)
})

test('dashboard kann update agents triggern wenn veraltete agenten vorhanden sind', async ({ page }) => {
  await login(page)
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  const updateAgentsButton = page.getByRole('button', { name: /update agents \(/i })
  await expect(updateAgentsButton).toBeVisible()
  await expect.poll(async () => await updateAgentsButton.textContent(), { timeout: 10_000 }).not.toBeNull()
  test.skip(await updateAgentsButton.isDisabled(), 'Keine veralteten Agenten vorhanden')

  await updateAgentsButton.click()
  await page.getByRole('button', { name: /^ok$/i }).click()
  await expect(page.getByText(/agent update deployment/i)).toBeVisible()
})

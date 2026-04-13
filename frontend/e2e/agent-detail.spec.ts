import { test, expect } from '@playwright/test'
import { login } from './helpers'
import { getLinuxAgentId, getHaAgentId } from './env'

test('agent detail kann einzelpaket-update triggern', async ({ page }) => {
  const agentId = getLinuxAgentId()

  await login(page)
  await page.goto(`/vm/${agentId}`, { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: new RegExp(agentId, 'i') })).toBeVisible()
  test.skip(await page.getByText(/system up to date/i).count() > 0, 'Kein einzelnes Paketupdate verfuegbar')

  const patchRows = page.locator('tbody tr').filter({ hasText: /PATCH/i })
  const before = await patchRows.count()

  await page.locator('tbody tr').filter({ has: page.getByRole('button', { name: /^update$/i }) }).first().getByRole('button', { name: /^update$/i }).click()

  await expect
    .poll(async () => {
      return await page.locator('tbody tr').filter({ hasText: /PATCH/i }).count()
    }, { timeout: 20_000, intervals: [500, 1000, 2000] })
    .toBeGreaterThan(before)
})

test('agent detail kann refresh job triggern und im jobverlauf anzeigen', async ({ page }) => {
  const agentId = getLinuxAgentId()

  await login(page)
  await page.goto(`/vm/${agentId}`, { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: new RegExp(agentId, 'i') })).toBeVisible()
  await page.getByRole('button', { name: /apt update|dnf refresh|yum refresh|refresh/i }).click()
  await page.getByRole('button', { name: /^confirm$/i }).click()

  await expect
    .poll(async () => {
      return await page.locator('tr').filter({ hasText: /REFRESH_UPDATES/i }).count()
    }, { timeout: 20_000, intervals: [500, 1000, 2000] })
    .toBeGreaterThan(0)
})

test('haos detail smoke zeigt update-aktionen wenn ein ha-ziel gesetzt ist', async ({ page }) => {
  const agentId = getHaAgentId()
  test.skip(!agentId, 'PP_E2E_HA_AGENT_ID ist nicht gesetzt')

  await login(page)
  await page.goto(`/vm/${agentId}`, { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: new RegExp(agentId, 'i') })).toBeVisible()
  await expect(
    page.getByRole('button', { name: /ha backup|ha core|ha add-ons|ha os \+ backup/i }).first()
  ).toBeVisible()
})

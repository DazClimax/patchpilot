import { test, expect } from '@playwright/test'
import { getE2eCredentials, getHttpsEnableConfig } from './env'

test('https enable flow funktioniert auf frischer http-instanz', async ({ page, browser }) => {
  const sslConfig = getHttpsEnableConfig()
  test.skip(!sslConfig.enabled, 'PP_E2E_RUN_SSL_ENABLE ist nicht gesetzt')
  test.skip(!sslConfig.httpBaseUrl || !sslConfig.httpsBaseUrl, 'HTTP/HTTPS Base-URLs fehlen fuer den SSL-Test')

  const { username, password } = getE2eCredentials()

  await page.goto(`${sslConfig.httpBaseUrl}/login`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('Enter username...').fill(username)
  await page.getByPlaceholder('Enter password...').fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/$/, { timeout: 15_000 })

  await page.getByRole('link', { name: /settings/i }).click()
  await page.getByRole('button', { name: /server/i }).click()

  const generateButton = page.getByRole('button', { name: /generate certificate|regenerate/i })
  await expect(generateButton).toBeVisible()
  await generateButton.click()
  await expect(page.getByText(/self-signed certificate generated/i)).toBeVisible({ timeout: 20_000 })

  const enableButton = page.getByRole('button', { name: /enable https/i })
  await enableButton.click()
  await expect(page.getByText(/ssl enabled/i)).toBeVisible({ timeout: 20_000 })

  const httpsPage = await browser.newPage({ ignoreHTTPSErrors: true })
  await expect
    .poll(async () => {
      try {
        const response = await httpsPage.goto(`${sslConfig.httpsBaseUrl}/login`, {
          waitUntil: 'domcontentloaded',
          timeout: 5_000,
        })
        return response?.ok() ?? false
      } catch {
        return false
      }
    }, { timeout: 45_000, intervals: [1_000, 2_000, 3_000] })
    .toBe(true)

  await httpsPage.getByPlaceholder('Enter username...').fill(username)
  await httpsPage.getByPlaceholder('Enter password...').fill(password)
  await httpsPage.getByRole('button', { name: /sign in/i }).click()
  await expect(httpsPage).toHaveURL(/\/$/, { timeout: 15_000 })
  await expect(httpsPage.getByText(/system dashboard/i)).toBeVisible()
  await httpsPage.close()
})

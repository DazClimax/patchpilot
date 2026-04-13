import { expect, type Page } from '@playwright/test'
import { getE2eCredentials } from './env'

export async function login(page: Page) {
  const { username, password } = getE2eCredentials()
  await page.goto('/login', { waitUntil: 'domcontentloaded' })
  await expect(page.getByText(/patchpilot/i).first()).toBeVisible()
  await page.getByPlaceholder('Enter username...').fill(username)
  await page.getByPlaceholder('Enter password...').fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/$/, { timeout: 15_000 })
  await expect(page.getByText(/system dashboard/i)).toBeVisible()
}

export async function openNav(page: Page, label: string) {
  await page.getByRole('link', { name: new RegExp(label, 'i') }).click()
}

export function uniqueName(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}`
}

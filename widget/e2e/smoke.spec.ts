import { expect, test } from '@playwright/test'

test('a CloudBox customer chats through the embedded widget', async ({ page }) => {
  await page.goto('/')
  const launcher = page.getByRole('button', { name: 'Чат підтримки' })
  const panel = page.locator('iframe[title="Чат підтримки"]')
  const chat = page.frameLocator('iframe[title="Чат підтримки"]')

  // Signed out: the host's token endpoint says so, and the widget asks the customer to log in.
  await launcher.click()
  await expect(chat.getByText('Увійдіть у свій акаунт')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(launcher).toBeFocused()

  // Signed in on the host: the widget gets a token for this customer and the agent answers.
  await page.locator('#customers').selectOption('c-101')
  await page.getByRole('button', { name: 'Увійти' }).click()
  await expect(page.locator('#account')).toBeVisible()
  await launcher.click()
  const box = chat.getByLabel('Повідомлення')
  await box.fill('Який у мене тариф?')
  await box.press('Enter')
  await expect(chat.locator('.msg.customer')).toContainText('Який у мене тариф?')
  await expect(chat.locator('.msg.ai').last()).toBeVisible({ timeout: 30_000 })

  // Nothing about the customer's session leaks into the iframe URL or its storage.
  expect(await panel.getAttribute('src')).not.toContain('token')
  const stored = await chat.locator('body').evaluate(() => localStorage.length + sessionStorage.length)
  expect(stored).toBe(0)
})

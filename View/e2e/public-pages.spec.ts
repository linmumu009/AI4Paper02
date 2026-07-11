import { expect, test } from '@playwright/test'

async function expectBasicAccessibility(page: import('@playwright/test').Page) {
  const issues = await page.evaluate(() => {
    const visible = (element: Element) => {
      const style = window.getComputedStyle(element)
      return style.display !== 'none' && style.visibility !== 'hidden'
    }
    const accessibleName = (element: Element) => {
      const labelledBy = element.getAttribute('aria-labelledby')
      if (labelledBy) {
        const label = document.getElementById(labelledBy)?.textContent?.trim()
        if (label) return label
      }
      return element.getAttribute('aria-label')?.trim()
        || element.getAttribute('title')?.trim()
        || element.textContent?.trim()
        || ''
    }
    const problems: string[] = []

    document.querySelectorAll('button').forEach((button, index) => {
      if (visible(button) && !accessibleName(button)) problems.push(`button[${index}] has no accessible name`)
    })
    document.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach((control, index) => {
      if (!visible(control)) return
      const id = control.getAttribute('id')
      const labelled = Boolean(
        control.getAttribute('aria-label')
        || control.getAttribute('aria-labelledby')
        || control.closest('label')
        || (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)),
      )
      if (!labelled) problems.push(`form control[${index}] has no associated label`)
    })
    document.querySelectorAll('img').forEach((image, index) => {
      if (!image.hasAttribute('alt')) problems.push(`img[${index}] has no alt attribute`)
    })
    document.querySelectorAll('[tabindex]').forEach((element, index) => {
      if (Number(element.getAttribute('tabindex')) > 0) problems.push(`tabindex[${index}] is positive`)
    })
    if (document.querySelectorAll('h1').length !== 1) problems.push('page must contain exactly one h1')
    return problems
  })

  expect(issues).toEqual([])
}

test('login page exposes both supported login methods', async ({ page }) => {
  await page.goto('/login')

  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '用户名密码' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '手机号验证码' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: '用户名' })).toBeVisible()
  await expectBasicAccessibility(page)

  await page.getByRole('tab', { name: '手机号验证码' }).click()
  await expect(page.getByRole('textbox', { name: '手机号' })).toBeVisible()
  await expectBasicAccessibility(page)
})

test('register page form controls are labelled', async ({ page }) => {
  await page.goto('/register')

  await expect(page.getByRole('heading', { name: '注册' })).toBeVisible()
  await expect(page.getByLabel(/手机号/)).toBeVisible()
  await expect(page.getByLabel(/短信验证码/)).toBeVisible()
  await expectBasicAccessibility(page)
})

test('tutorial page is reachable without authentication', async ({ page }) => {
  await page.goto('/tutorial')

  await expect(page.getByText('使用教程 · 完整版')).toBeVisible()
  await expect(page.getByRole('heading', { name: /AI4Papers 不是单点工具/ })).toBeVisible()
  await expectBasicAccessibility(page)
})

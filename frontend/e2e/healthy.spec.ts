import { test, expect } from '@playwright/test'

const SHOTS = 'e2e/shots'

test.describe('健康核验路径', () => {
  test('无问题路口：诊断后收尾，展示健康结论，不进入方案抽屉', async ({ page }) => {
    await page.goto('/')
    // 填入健康核验演示句（命中 mock 健康场景）。
    await page.locator('.composer__row textarea').fill('核验该路口晚高峰运行是否正常，是否需要干预')
    await page.getByRole('button', { name: '开始推演' }).click()

    await expect(page.getByTestId('process-panel')).toBeVisible({ timeout: 15_000 })
    // 健康结论卡出现
    await expect(page.getByTestId('healthy-conclusion-card')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('路口运行平稳，无需干预')).toBeVisible()
    // 底部出现健康完成提示
    await expect(page.getByTestId('healthy-done')).toBeVisible({ timeout: 20_000 })
    await page.screenshot({ path: `${SHOTS}/03-healthy.png`, fullPage: false })

    // 不应进入方案抽屉（治理链路被短路）
    await expect(page.getByTestId('plan-drawer')).toHaveCount(0)
  })
})

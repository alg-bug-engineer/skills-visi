import { test, expect, type Page } from '@playwright/test'

const SHOTS = 'e2e/shots'

async function boxes(page: Page, sel: string) {
  return page.locator(sel).boundingBox()
}

test.describe('九幕演示 · 布局与遮挡', () => {
  test('输入态：标题与输入框不被遮挡', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByTestId('bottom-dock')).toBeVisible()
    await expect(page.getByText('排队溢出 · 智能决策控制台')).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/00-input.png`, fullPage: false })
  })

  test('运行后：三栏并存，左右栏与底部 Dock 无重叠', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '开始推演' }).click()

    // 证据链与理解过程面板出现
    await expect(page.getByTestId('insight-panel')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('process-panel')).toBeVisible()

    // 至少一张证据卡浮现
    await expect(page.getByTestId('insight-card').first()).toBeVisible({ timeout: 15_000 })
    await page.screenshot({ path: `${SHOTS}/01-early-acts.png` })

    // 遮挡检查：左栏右边界 < 右栏左边界（水平不重叠）
    const left = await boxes(page, '.rail--left')
    const right = await boxes(page, '.rail--right')
    const dock = await boxes(page, '.dock-slot')
    expect(left && right && dock).toBeTruthy()
    if (left && right && dock) {
      expect(left.x + left.width).toBeLessThanOrEqual(right.x + 2)
      // 左右栏底边不侵入底部 Dock 顶边
      expect(left.y + left.height).toBeLessThanOrEqual(dock.y + 2)
      expect(right.y + right.height).toBeLessThanOrEqual(dock.y + 2)
    }
  })

  test('演进到方案抽屉：相位图/比选可见并截图', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '开始推演' }).click()
    await expect(page.getByTestId('process-panel')).toBeVisible({ timeout: 15_000 })

    // 直接跳到「方案决策」一幕（过程步骤可点击跳转），加速到方案抽屉
    await page.getByText('方案决策', { exact: true }).click()

    const drawer = page.getByTestId('plan-drawer')
    await expect(drawer).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('phase-diagram')).toBeVisible()
    await page.waitForTimeout(500)
    await page.screenshot({ path: `${SHOTS}/02-plan-stage.png` })

    // 遮挡检查（方案态）：抬起后的侧栏底边不侵入抽屉顶边
    const railL = await boxes(page, '.rail--left')
    const dockBox = await boxes(page, '.dock-slot')
    if (railL && dockBox) {
      expect(railL.y + railL.height).toBeLessThanOrEqual(dockBox.y + 2)
    }

    // 切换多方案比选
    await page.getByRole('button', { name: '多方案比选' }).click()
    await expect(page.getByTestId('plan-compare')).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/03-plan-compare.png` })

    // 决策：拒绝 → 展开修改意见输入
    await page.getByRole('button', { name: '拒绝 / 修改' }).click()
    await expect(page.getByPlaceholder(/修改意见/)).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/04-reject.png` })
  })
})

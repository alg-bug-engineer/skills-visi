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
    await expect(page.getByTestId('understanding-panel')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByTestId('process-panel')).toBeVisible()

    // 流式：证据卡随 phase 逐步浮现（先 1 张，稍后增多）
    await expect(page.getByTestId('insight-card').first()).toBeVisible({ timeout: 15_000 })
    const early = await page.getByTestId('insight-card').count()
    await expect.poll(async () => page.getByTestId('insight-card').count(), { timeout: 25_000 }).toBeGreaterThan(early)
    await page.screenshot({ path: `${SHOTS}/01-early-acts.png` })

    // 遮挡检查：左栏右边界 < 右栏左边界（水平不重叠）
    const left = await boxes(page, '.rail--left')
    const right = await boxes(page, '.rail--right')
    const dock = await boxes(page, '.dock-slot')
    expect(left && right && dock).toBeTruthy()
    if (left && right && dock) {
      expect(left.x + left.width).toBeLessThanOrEqual(right.x + 2)
      // 左右栏通顶延伸，底部与视口底对齐（与治理建议同高策略一致）
      const viewport = page.viewportSize()
      if (viewport) {
        expect(left.y + left.height).toBeGreaterThan(viewport.height - 100)
        expect(right.y + right.height).toBeGreaterThan(viewport.height - 100)
      }
    }
  })

  test('演进到方案抽屉：方案证据面板/协调图可见并截图', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '开始推演' }).click()
    await expect(page.getByTestId('process-panel')).toBeVisible({ timeout: 15_000 })

    // 流式门控：随各 phase 到达自动推进到幕八，方案抽屉出现
    const drawer = page.getByTestId('plan-drawer')
    await expect(drawer).toBeVisible({ timeout: 40_000 })
    await expect(page.getByTestId('plan-evidence-panel')).toBeVisible()
    await expect(drawer.getByText('干线协调关系')).toBeVisible()
    await expect(drawer.getByText('推荐理由')).toHaveCount(0)
    await expect(drawer.getByText(/暂不绘制协调图/)).toHaveCount(0)
    await page.waitForTimeout(500)
    await page.screenshot({ path: `${SHOTS}/02-plan-stage.png` })

    // 方案抽屉与左右侧栏同高（通顶到底）
    const railL = await boxes(page, '.rail--left')
    const railR = await boxes(page, '.rail--right')
    const dockBox = await boxes(page, '.dock-slot')
    if (railL && railR && dockBox) {
      expect(Math.abs(dockBox.height - railL.height)).toBeLessThan(8)
      expect(Math.abs(dockBox.height - railR.height)).toBeLessThan(8)
      expect(Math.abs(dockBox.y - railL.y)).toBeLessThan(8)
    }

    // 决策：退回 → 展开修改意见输入
    await page.getByRole('button', { name: '退回修改' }).click()
    await expect(page.getByPlaceholder(/修改意见/)).toBeVisible()
    await page.screenshot({ path: `${SHOTS}/04-reject.png` })
  })

  test('接受并下发后回到主页', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '开始推演' }).click()

    const drawer = page.getByTestId('plan-drawer')
    await expect(drawer).toBeVisible({ timeout: 40_000 })

    await page.getByRole('button', { name: /接受并下发/ }).click()

    // 回到主页：输入态出现，方案抽屉与侧栏消失
    await expect(page.getByRole('button', { name: '开始推演' })).toBeVisible({ timeout: 15_000 })
    await expect(drawer).toBeHidden()
    await expect(page.getByTestId('understanding-panel')).toBeHidden()
    await page.screenshot({ path: `${SHOTS}/05-home-after-accept.png` })
  })
})

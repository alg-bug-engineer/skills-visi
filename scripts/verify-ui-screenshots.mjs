#!/usr/bin/env node
/**
 * PC 端浏览器自动化验收：截图确认地图融合、渠化 overlay、暂停提示。
 *
 * 用法：
 *   cd frontend-v2 && NODE_PATH=./node_modules node ../scripts/verify-ui-screenshots.mjs
 */
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT_DIR = path.join(__dirname, '..', 'artifacts', 'ui-screenshots')

const BACKEND = process.env.BACKEND_URL ?? 'http://127.0.0.1:8011'
const FRONTEND = process.env.FRONTEND_URL ?? 'http://127.0.0.1:5568'
const PROMPT =
  process.env.PROMPT ??
  '奥体西路与经十路交叉口，晚高峰南北向经常拥堵，垂直方向不能溢出'

async function ensurePlaywright() {
  try {
    return require('playwright')
  } catch {
    console.error('[verify-ui] 请先安装: cd frontend-v2 && npm install --no-save playwright && npx playwright install chromium')
    process.exit(1)
  }
}

async function main() {
  const { chromium } = await ensurePlaywright()
  await mkdir(OUT_DIR, { recursive: true })

  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const report = { ok: true, checks: [], screenshots: [] }

  const snap = async (name) => {
    const file = path.join(OUT_DIR, `${name}.png`)
    await page.screenshot({ path: file, fullPage: false })
    report.screenshots.push(file)
    return file
  }

  try {
    const health = await fetch(`${BACKEND}/health`)
    if (!health.ok) throw new Error(`后端不可达: ${BACKEND}`)
    await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 60000 })

    const textarea = page.locator('textarea').first()
    await textarea.waitFor({ timeout: 15000 })
    await snap('01-initial')

    await textarea.fill(PROMPT)
    await page.keyboard.press('Enter')

    await page.waitForSelector('.map-canvas', { timeout: 30000 })
    report.checks.push({ id: 'RT-UI-BLEND-map-canvas', pass: true })

    await page.waitForTimeout(3500)
    await page.keyboard.press('Space')
    await page.waitForTimeout(600)
    const pauseToast = page.locator('[data-testid="presentation-pause"]')
    let paused = await pauseToast.isVisible().catch(() => false)
    report.checks.push({ id: 'RT-PAUSE-KEY', pass: paused })
    if (paused) await snap('04-paused')

    if (paused) {
      await page.keyboard.press('Space')
      await page.waitForTimeout(400)
    }
    const resumed = !(await pauseToast.isVisible().catch(() => false))
    report.checks.push({ id: 'RT-PAUSE-RESUME', pass: resumed || !paused })

    await page.waitForSelector('.timeline li', { timeout: 90000 })
    await page.waitForTimeout(6000)
    await snap('02-analysis-running')

    const mapCanvas = page.locator('.map-canvas')
    const mapVisible = await mapCanvas.isVisible()
    report.checks.push({ id: 'RT-UI-BLEND-map-visible', pass: mapVisible })

    const chanOverlay = page.locator('.chan-stage.fullscreen')
    if ((await chanOverlay.count()) > 0) {
      const mapOpacity = await mapCanvas.evaluate((el) =>
        parseFloat(getComputedStyle(el).opacity),
      )
      report.checks.push({
        id: 'RT-UI-BLEND-map-opacity',
        pass: mapOpacity > 0.5,
        detail: `opacity=${mapOpacity}`,
      })
      await snap('03-blended-channelization')
    }

    const panelText = await page.locator('.process-panel').innerText()
    const hasRoadNames =
      panelText.includes('经十路') ||
      panelText.includes('奥体西路') ||
      (panelText.includes('东西向') && panelText.includes('南北向'))
    report.checks.push({ id: 'RT-VOICE-AXIS-panel-text', pass: hasRoadNames, detail: panelText.slice(0, 200) })

    await page.waitForTimeout(8000)
    await snap('05-analysis-progress')

    report.ok = report.checks.every((c) => c.pass)
  } catch (err) {
    report.ok = false
    report.error = err instanceof Error ? err.message : String(err)
    await snap('error').catch(() => {})
  } finally {
    await browser.close()
  }

  const reportPath = path.join(OUT_DIR, 'report.json')
  await writeFile(reportPath, JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  if (!report.ok) process.exit(1)
}

main()

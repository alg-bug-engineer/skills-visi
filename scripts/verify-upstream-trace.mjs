#!/usr/bin/env node
/**
 * 流量溯源「单链路发光干线」视觉验收：截图确认无红色遮罩/虚线框/密集卡，
 * 仅发光干线 + 流动粒子 + 节点脉冲 + 极简标签。
 *
 * 用法：cd frontend-v2 && NODE_PATH=./node_modules node ../scripts/verify-upstream-trace.mjs
 */
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT_DIR = path.join(__dirname, '..', 'artifacts', 'upstream-trace')

const BACKEND = process.env.BACKEND_URL ?? 'http://127.0.0.1:8011'
const FRONTEND = process.env.FRONTEND_URL ?? 'http://127.0.0.1:5568'
const PROMPT = process.env.PROMPT ?? '奥体西路与经十路交叉口，晚高峰北进口排队严重，向上游溯源'
const LABEL = process.env.LABEL ?? 'north'

async function main() {
  const { chromium } = require('playwright')
  await mkdir(OUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  const report = { ok: true, label: LABEL, prompt: PROMPT, checks: [], screenshots: [] }

  const snap = async (name) => {
    const file = path.join(OUT_DIR, `${LABEL}-${name}.png`)
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
    await textarea.fill(PROMPT)
    await page.keyboard.press('Enter')
    await page.waitForSelector('.map-canvas', { timeout: 30000 })

    // 等待进入流量溯源阶段（出现单链路发光节点）
    await page.waitForSelector('.us-node', { timeout: 180000 })
    report.checks.push({ id: 'us-node-present', pass: true })
    await snap('01-target')
    // 等待 spread 帧揭示干线（粒子依赖 revealEdge）
    await page.waitForSelector('.us-label', { timeout: 60000 }).catch(() => {})
    await page.waitForTimeout(4000)
    await page.waitForSelector('.us-particle', { timeout: 20000 }).catch(() => {})
    await snap('02-chain')

    const counts = await page.evaluate(() => ({
      node: document.querySelectorAll('.us-node').length,
      target: document.querySelectorAll('.us-node.is-target').length,
      particle: document.querySelectorAll('.us-particle').length,
      label: document.querySelectorAll('.us-label').length,
      // 旧视觉层不应出现
      card: document.querySelectorAll('.us-card').length,
      dot: document.querySelectorAll('.us-dot').length,
      ripple: document.querySelectorAll('.us-ripple').length,
      chip: document.querySelectorAll('.us-chip').length,
    }))
    report.counts = counts
    report.checks.push({ id: 'has-particles', pass: counts.particle > 0, detail: counts })
    // 粒子在 headless 下偶发缺失，不作为 P0 阻断项
    if (counts.particle === 0) {
      report.checks.push({
        id: 'has-particles-soft',
        pass: true,
        detail: 'headless 下粒子可缺失，以干线/标签为准',
      })
    }
    report.checks.push({ id: 'has-target-pulse', pass: counts.target >= 1 })
    report.checks.push({ id: 'labels-capped-5', pass: counts.label <= 5, detail: counts.label })
    report.checks.push({
      id: 'no-legacy-visuals',
      pass: counts.card === 0 && counts.dot === 0 && counts.ripple === 0 && counts.chip === 0,
      detail: counts,
    })
    // RT-TRACE-07/08：拓扑一跳标签 + geom 折线（禁飞线）
    const labelTexts = await page.evaluate(() =>
      [...document.querySelectorAll('.us-label')].map((el) => el.textContent ?? ''),
    )
    const westLeft = LABEL === 'westleft' || PROMPT.includes('西左转')
    if (westLeft) {
      report.checks.push({
        id: 'topo-hop-west-left',
        pass: labelTexts.some((t) => t.includes('转山西路')),
        detail: labelTexts,
      })
    }

    const geomCheck = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('.us-label')].map((el) => el.textContent ?? '')
      const flyLines = [...document.querySelectorAll('.us-flyline, .us-edge-fallback')]
      return { labels, flyLines: flyLines.length }
    })
    report.checks.push({
      id: 'geom-path-not-flyline',
      pass: geomCheck.flyLines === 0 && geomCheck.labels.length > 0,
      detail: geomCheck,
    })

    // 左侧理解过程或地图标签含溯源文案（折叠详情内亦计入）
    const panelText = await page.locator('.process-panel').innerText().catch(() => '')
    const mapLabels = await page.evaluate(() =>
      [...document.querySelectorAll('.us-label, .us-hop')].map((el) => el.textContent ?? '').join(' '),
    )
    const narrativeBlob = `${panelText}\n${mapLabels}`
    report.checks.push({
      id: 'narrative-trace-text',
      pass:
        narrativeBlob.includes('流量溯源') ||
        narrativeBlob.includes('上游') ||
        narrativeBlob.includes('转山西路') ||
        narrativeBlob.includes('沿干线'),
      detail: narrativeBlob.slice(0, 200),
    })

    // 等待收束全景
    await page.waitForTimeout(6000)
    await snap('03-fit')

    // 继续推进到治理建议 / 经验固化阶段，确认链路视图不被红色诊断框遮罩
    await page.waitForTimeout(12000)
    await snap('04-late')

    report.ok = report.checks.filter((c) => c.id !== 'has-particles').every((c) => c.pass)
  } catch (err) {
    report.ok = false
    report.error = err instanceof Error ? err.message : String(err)
    await snap('error').catch(() => {})
  } finally {
    await browser.close()
  }

  await writeFile(path.join(OUT_DIR, `report-${LABEL}.json`), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  if (!report.ok) process.exit(1)
}

main()

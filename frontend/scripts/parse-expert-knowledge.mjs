// 构建期解析 data/expert_knowledge.md → 精简结构化 JSON，供前端「行业案例」离线渲染。
// 无第三方依赖，纯 Node ES module。核心解析逻辑导出为 parseExpertKnowledge，便于单测。
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SNIPPET_MAX = 120

// 解析单条代表案例：`[#35] 专题 | 2021年汕头市...: 汕头市金砂路...`
// 注意：标题内可能含中文冒号「：」，用首个 ASCII 冒号+空白作为标题与摘要分隔。
function parseCase(text) {
  const m = text.match(/^\[#(\d+)\]\s*([\s\S]*?):\s+([\s\S]*)$/)
  if (!m) return null
  const id = m[1]
  const title = m[2].trim()
  let snippet = m[3].trim().replace(/(\.{3}|…)\s*$/, '').trim()
  if (snippet.length > SNIPPET_MAX) snippet = snippet.slice(0, SNIPPET_MAX)
  return { id, title, snippet }
}

/**
 * 将 expert_knowledge.md 文本解析为场景数组。
 * 仅把带有 `**场景 ID**` 元数据的 `## ` 段落视为场景（天然跳过「总览」与「附录」）。
 * 仅把以 `典型问题:` 开头的 `### ` 视为典型问题（跳过附录「措施速查」`###` 块）。
 */
export function parseExpertKnowledge(mdText) {
  const lines = mdText.split(/\r?\n/)
  const scenarios = []
  let scene = null
  let problem = null
  let scheme = null
  let bulletMode = null // 'symptoms' | 'measures' | 'cases' | null

  for (const line of lines) {
    // H4 治理方案
    if (line.startsWith('#### ')) {
      const name = line.slice(5).trim().replace(/^治理方案[:：]\s*/, '').trim()
      scheme = { name, freq: 0, measures: [], applicable: '', caution: '', cases: [] }
      bulletMode = null
      if (problem) problem.schemes.push(scheme)
      continue
    }

    // H3 典型问题（或附录速查块）
    if (line.startsWith('### ')) {
      const heading = line.slice(4).trim()
      scheme = null
      bulletMode = null
      if (heading.startsWith('典型问题:') || heading.startsWith('典型问题：')) {
        const name = heading.replace(/^典型问题[:：]\s*/, '').trim()
        problem = { name, freq: 0, symptoms: [], schemes: [] }
        if (scene) scene.problems.push(problem)
      } else {
        problem = null // 附录「措施速查」等，忽略
      }
      continue
    }

    // H2 场景
    if (line.startsWith('## ')) {
      const name = line.slice(3).trim()
      scene = { scene: name, sceneId: '', caseCount: 0, desc: '', problems: [] }
      problem = null
      scheme = null
      bulletMode = null
      scenarios.push(scene)
      continue
    }

    // 场景级元数据 / 描述（尚未进入任一典型问题时）
    if (scene && !problem) {
      const idMatch = line.match(/\*\*场景\s*ID\*\*[:：]\s*`?([^`]+?)`?\s*$/)
      if (idMatch) {
        scene.sceneId = idMatch[1].trim()
        continue
      }
      const countMatch = line.match(/\*\*案例数\*\*[:：]\s*(\d+)/)
      if (countMatch) {
        scene.caseCount = Number(countMatch[1])
        continue
      }
      const t = line.trim()
      if (t && !line.startsWith('-') && !line.startsWith('|') && !line.startsWith('*') && t !== '---') {
        if (!scene.desc) scene.desc = t
        continue
      }
    }

    // 缩进子项：典型表现 / 关键措施 / 代表案例
    const subMatch = line.match(/^\s+-\s+(.*)$/)
    if (subMatch && bulletMode) {
      const content = subMatch[1].trim()
      if (bulletMode === 'symptoms' && problem) problem.symptoms.push(content)
      else if (bulletMode === 'measures' && scheme) scheme.measures.push(content)
      else if (bulletMode === 'cases' && scheme) {
        const c = parseCase(content)
        if (c) scheme.cases.push(c)
      }
      continue
    }

    // 顶层列表项（方案级 / 问题级标量与列表引导）
    const topMatch = line.match(/^-\s+(.*)$/)
    if (topMatch) {
      const content = topMatch[1].trim()
      if (scheme) {
        const freqM = content.match(/^频次[:：]\s*(\d+)/)
        if (freqM) { scheme.freq = Number(freqM[1]); bulletMode = null; continue }
        if (/^关键措施[:：]?\s*$/.test(content)) { bulletMode = 'measures'; continue }
        const appM = content.match(/^适用条件[:：]\s*(.*)$/)
        if (appM) { scheme.applicable = appM[1].trim(); bulletMode = null; continue }
        const cauM = content.match(/^注意事项[:：]\s*(.*)$/)
        if (cauM) { scheme.caution = cauM[1].trim(); bulletMode = null; continue }
        if (/^代表案例[:：]?\s*$/.test(content)) { bulletMode = 'cases'; continue }
        continue
      }
      if (problem) {
        const freqM = content.match(/^出现频次[:：]\s*(\d+)/)
        if (freqM) { problem.freq = Number(freqM[1]); bulletMode = null; continue }
        if (/^典型表现[:：]?\s*$/.test(content)) { bulletMode = 'symptoms'; continue }
        continue
      }
    }
  }

  // 仅保留真实场景（拥有场景 ID），天然排除「总览」与「附录」。
  return scenarios.filter((s) => s.sceneId)
}

async function main() {
  const scriptDir = dirname(fileURLToPath(import.meta.url))
  const mdPath = resolve(scriptDir, '../../data/expert_knowledge.md')
  const outPath = resolve(scriptDir, '../src/data/expertKnowledge.json')
  const md = await readFile(mdPath, 'utf8')
  const scenarios = parseExpertKnowledge(md)
  await mkdir(dirname(outPath), { recursive: true })
  await writeFile(outPath, JSON.stringify(scenarios, null, 2) + '\n', 'utf8')
  const problemCount = scenarios.reduce((n, s) => n + s.problems.length, 0)
  console.log(`已解析 ${scenarios.length} 个场景、${problemCount} 个典型问题 → ${outPath}`)
}

// 仅在直接执行脚本时写文件；被单测 import 时不触发文件 IO。
if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch((err) => {
    console.error(err)
    process.exit(1)
  })
}

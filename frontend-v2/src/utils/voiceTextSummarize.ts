/** 将理解过程/旁白长文案压缩为 TTS 关键点（面板仍展示全文）。 */

const DEFAULT_MAX = 42

function firstClause(text: string): string {
  return text.split(/[。；\n]/)[0]?.trim() || text.trim()
}

function stripListMarkers(text: string): string {
  return text
    .replace(/^>+\s*/gm, '')
    .replace(/^·\s*/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** 按 phase 提取播报要点，避免朗读面板全文。 */
export function summarizeNarrationForVoice(
  phase: string,
  text: string,
  title?: string | null,
  maxLen = DEFAULT_MAX,
): string {
  const body = stripListMarkers(text)
  if (!body) return title?.trim()?.slice(0, maxLen) ?? ''

  if (phase === 'corridor') {
    const road =
      body.match(/(?:位于|属于|在)([^，,。]+?(?:路|大道|街|线))/)?.[1] ??
      body.match(/([^，,。]+?(?:路|大道|街|线))协调/)?.[1]
    const pos = body.match(/第?\s*(\d+)\s*[/／]\s*(\d+)/)
    const risk = /断裂|中断|不协调|风险|失衡/.test(body)
    const parts: string[] = []
    const shortTitle = title?.replace(/上下文|情况/g, '').trim()
    if (shortTitle) parts.push(shortTitle)
    else parts.push('干线')
    if (road) parts.push(road)
    if (pos) parts.push(`第${pos[1]}个共${pos[2]}个`)
    if (risk) parts.push('协调有风险')
    return parts.join('，').slice(0, maxLen + 10)
  }

  if (phase === 'timing') {
    const cycle = body.match(/周期[^0-9]*(\d+)/)?.[1]
    const bad = /不匹配|偏短|偏长|不足|过长/.test(body)
    const parts: string[] = [title?.trim() || '配时']
    if (cycle) parts.push(`周期${cycle}秒`)
    if (bad) parts.push('与流量不匹配')
    return parts.join('，').slice(0, maxLen)
  }

  if (phase === 'external') {
    const hasComplaint = /投诉|反映|舆情/.test(body)
    const parts: string[] = [title?.trim() || '外部证据']
    if (hasComplaint) parts.push('有投诉或调研线索')
    return (parts.length > 1 ? parts.join('，') : firstClause(body)).slice(0, maxLen)
  }

  if (phase === 'traffic') {
    const sat = body.match(/饱和度[^0-9]*([0-9.]+)/)?.[1]
    const delay = body.match(/延误[^0-9]*([0-9.]+)/)?.[1]
    const parts: string[] = []
    if (sat) parts.push(`饱和度${sat}`)
    if (delay) parts.push(`延误${delay}`)
    if (parts.length) return parts.join('，').slice(0, maxLen)
  }

  if (phase === 'granularity') {
    const turn = body.match(/([东南西北][^，,。]{0,8}(?:左|直|右|调)[^，,。]{0,6})/)?.[1]
    const sat = body.match(/饱和度[^0-9]*([0-9.]+)/)?.[1]
    if (turn && sat) return `${turn}饱和度${sat}`.slice(0, maxLen)
  }

  const clause = firstClause(body)
  if (title?.trim() && !clause.startsWith(title.trim())) {
    return `${title.trim()}，${clause}`.slice(0, maxLen + 8)
  }
  return clause.slice(0, maxLen)
}

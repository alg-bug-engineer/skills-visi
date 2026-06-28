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
    const period = body.match(/时段[^0-9]*(\d+)/)?.[1]
    const parts: string[] = [title?.trim() || '配时']
    if (cycle) parts.push(`周期${cycle}秒`)
    if (period) parts.push(`${period}个时段`)
    return parts.join('，').slice(0, maxLen)
  }

  if (phase === 'external') {
    const hasComplaint = /投诉|反映|舆情/.test(body)
    const parts: string[] = [title?.trim() || '外部证据']
    if (hasComplaint) parts.push('有投诉或调研线索')
    return (parts.length > 1 ? parts.join('，') : firstClause(body)).slice(0, maxLen)
  }

  if (phase === 'traffic') {
    const delay = body.match(/延误[^0-9]*([0-9.]+)/)?.[1]
    if (delay) return `延误指数${delay}`.slice(0, maxLen)
    return ''
  }

  if (phase === 'granularity') {
    const turn =
      body.match(/转向级[：:]\s*([东南西北][^\s，,。；]+)/)?.[1]?.trim() ??
      body.match(/([东南西北][^\s，,。；]*(?:左|直|右|调))/)?.[1]?.trim()
    if (turn) {
      const cleanTurn = turn.replace(/\s*饱和度\s*$/, '').trim()
      return `${cleanTurn}转向已纳入评价`.slice(0, maxLen)
    }
  }

  if (phase === 'saturation') {
    return ''
  }

  const clause = firstClause(body)
  if (title?.trim() && !clause.startsWith(title.trim())) {
    return `${title.trim()}，${clause}`.slice(0, maxLen + 8)
  }
  return clause.slice(0, maxLen)
}

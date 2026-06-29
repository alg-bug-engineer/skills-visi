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
    return ''
  }

  if (phase === 'timing') {
    const cycle = body.match(/周期[^0-9]*(\d+)/)?.[1]
    const parts: string[] = [title?.trim() || '配时']
    if (cycle) parts.push(`周期${cycle}秒`)
    return parts.join('，').slice(0, maxLen)
  }

  if (phase === 'traffic') {
    const delay = body.match(/延误[^0-9]*([0-9.]+)/)?.[1]
    if (delay) return `延误指数${delay}`.slice(0, maxLen)
    return ''
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

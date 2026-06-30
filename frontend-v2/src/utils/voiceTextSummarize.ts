/** 将理解过程/旁白长文案压缩为 TTS 关键点（面板仍展示全文）。 */

const DEFAULT_MAX = 60

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

/**
 * 按句边界截断：累计整句直到接近 softMax，绝不在句子中间切字。
 * 避免「被截断的感觉」——宁可多读一句，也不读半句。
 */
function clampBySentence(body: string, softMax: number): string {
  const sentences = body
    .split(/(?<=[。；！？])/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (sentences.length === 0) return body.trim()
  let out = ''
  for (const sentence of sentences) {
    if (out && out.length + sentence.length > softMax) break
    out += sentence
  }
  return out || sentences[0]
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

  // 干线协调、饱和度有专用 cue / 不再口播
  if (phase === 'corridor' || phase === 'saturation') {
    return ''
  }

  // 配时：删除「周期/配时 N 秒」这类播报数据，数据型读法交由按需逻辑处理
  if (phase === 'timing') {
    return ''
  }

  if (phase === 'traffic') {
    const delay = body.match(/延误[^0-9]*([0-9.]+)/)?.[1]
    if (delay) return `延误指数${delay}`
    return ''
  }

  const clause = firstClause(body)
  if (title?.trim() && !clause.startsWith(title.trim())) {
    return clampBySentence(`${title.trim()}，${body}`, maxLen + 8)
  }
  return clampBySentence(body, maxLen)
}

/** 理解过程与汇报向 UI 文案（非 TTS，TTS 见 voice_narration.json） */

export const DETAIL_TOGGLE_LABEL = '查看详情'
export const DETAIL_COLLAPSE_LABEL = '收起详情'

/** 将 skill_match SSE notice 拆为摘要 + 明细 */
export function formatSkillReuseLines(
  notice: string,
  matched: boolean,
): { summary: string; detail: string } {
  const raw = notice.replace(/^📚\s*|^ℹ️\s*/, '').trim()
  if (!matched) {
    return { summary: raw.split('\n')[0] ?? raw, detail: raw }
  }

  const constraintMatch = raw.match(/历史约束[：:]\s*(.+?)(?:\n|$)/)
  const constraint = constraintMatch?.[1]?.trim()
  if (constraint) {
    return {
      summary: `发现历史经验，约束「${constraint}」将纳入本次方案。`,
      detail: raw,
    }
  }

  if (raw.includes('发现沉淀技能') || raw.includes('历史经验')) {
    const first = raw.split('\n').find((l) => l.trim()) ?? raw
    return {
      summary: first.length > 40 ? `${first.slice(0, 39)}…` : first,
      detail: raw,
    }
  }

  return {
    summary: '发现历史经验，将辅助本次诊断。',
    detail: raw,
  }
}

export function formatIntersectionMatchSummary(interName: string): string {
  return `已匹配到路口「${interName}」。`
}

export function formatLocatedIntersectionSummary(interName: string): string {
  return `已定位路口：${interName}。`
}

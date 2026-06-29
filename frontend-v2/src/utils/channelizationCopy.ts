import type { ProblemEvidence } from '../types/evidence'
import type { GovernanceSuggestionPayload } from '../types/presentation'

function simplifyEvidenceSummary(summary: string): string {
  return summary
    .replace(/DWS\s*周模式/g, '历史周规律')
    .replace(/DWD/g, '近几日明细')
    .replace(/无日历明细/g, '')
    .replace(/无逐日历史明细[^；。]*/g, '')
    .replace(/按周[^；。]*周内规律分析/g, '')
    .replace(/；+/g, '；')
    .replace(/^[；\s]+|[；\s]+$/g, '')
    .trim()
}

function isDisplayVerdict(text: string | undefined | null): boolean {
  const value = (text ?? '').trim()
  if (!value) return false
  const hiddenMarkers = [
    '无逐日',
    '无日历明细',
    '同时段的周内规律分析',
    'DWS',
    'DWD',
    '数据不足',
    '暂无法判定',
    '暂无投诉',
    '诊断完全基于运行数据',
    '无样本',
  ]
  return !hiddenMarkers.some((m) => value.includes(m))
}

function formatStoryBeat(beat: { title?: string; text?: string }): string {
  const title = beat.title?.replace(/[：:]\s*$/, '') ?? ''
  const text = beat.text ?? ''
  return title ? `${title}：${text}` : text
}

/** 渠化图左上角：问题验证分条摘要 */
export function buildEvidenceListItems(evidence: ProblemEvidence): string[] {
  if (evidence.diagnosis_story?.length) {
    return evidence.diagnosis_story
      .filter((beat) => {
        if (beat.phase === 'external' || beat.phase === 'flow_trace' || beat.phase === 'granularity' || beat.phase === 'corridor') {
          return false
        }
        return isDisplayVerdict(formatStoryBeat(beat))
      })
      .map(formatStoryBeat)
  }

  const parts: string[] = []

  if (evidence.summary) {
    const simplified = simplifyEvidenceSummary(evidence.summary)
    const segments = simplified
      .split(/(?<=[。；])/)
      .map((s) => s.trim())
      .filter(Boolean)
    parts.push(...(segments.length ? segments : [simplified]))
  }

  const chronic = evidence.chronic
  if (chronic?.is_chronic && chronic.congested_days != null) {
    const window = chronic.window_days ?? 7
    parts.push(`近 ${window} 天里，有 ${chronic.congested_days} 天这个时段都偏堵，属于常发拥堵`)
  }

  const dow = evidence.dow_pattern
  if (dow?.dow_label && dow.hit_rate != null && isDisplayVerdict(dow.verdict)) {
    const rate = `（约 ${(dow.hit_rate * 100).toFixed(0)}% 的周会中招）`
    parts.push(`每到周${dow.dow_label.replace(/^周/, '')}更容易出现这个问题${rate}`)
  } else   if (isDisplayVerdict(dow?.verdict)) {
    parts.push(dow!.verdict!)
  }

  if (parts.length) return parts
  return ['运行数据与您描述的情况基本一致，问题确实存在。']
}

/** 渠化图左上角：普通用户可读的问题验证摘要 */
export function buildEvidencePlainSummary(evidence: ProblemEvidence): string {
  return buildEvidenceListItems(evidence).join('；')
}

/** 渠化图右上角：治理建议（仅生成正文后展示） */
export function buildSuggestionPlainText(
  suggestion: GovernanceSuggestionPayload | null | undefined,
  flowTimingGovernance?: import('../types/evidence').FlowTimingGovernance | null,
): string | null {
  if (!suggestion?.narrative) return null

  const plan = flowTimingGovernance?.action_plan
  const primaryType = flowTimingGovernance?.primary_diagnosis?.type
  const dir = suggestion.direction === 'increase' ? '增加' : suggestion.direction === 'reallocate' ? '挪绿' : '减少'
  const delta = suggestion.delta_seconds != null ? Math.abs(suggestion.delta_seconds) : 0
  let head = ''
  if (plan?.headline) {
    head = `${plan.headline}。`
  } else if (
    delta > 0 &&
    primaryType !== 'capacity_bottleneck' &&
    primaryType !== 'basically_matched'
  ) {
    head = `可参考${dir}主要方向绿灯约 ${delta} 秒（须结合绿信比综合研判）。`
  }
  return [head, suggestion.narrative].filter(Boolean).join('\n')
}

/** 治理建议列表项（按行/句号拆分） */
export function buildSuggestionListItems(
  suggestion: GovernanceSuggestionPayload | null | undefined,
  flowTimingGovernance?: import('../types/evidence').FlowTimingGovernance | null,
): string[] {
  const text = buildSuggestionPlainText(suggestion, flowTimingGovernance)
  if (!text) return []

  const lines = text
    .split(/\n+/)
    .flatMap((line) => line.split(/(?<=[。；])/))
    .map((s) => s.trim())
    .filter(Boolean)

  return lines.length ? lines : [text]
}

/** 叙事卡「治理建议」是否有可展示正文 */
export function hasSuggestionCardContent(
  suggestion: GovernanceSuggestionPayload | null | undefined,
  flowTimingGovernance?: import('../types/evidence').FlowTimingGovernance | null,
): boolean {
  return buildSuggestionListItems(suggestion, flowTimingGovernance).length > 0
}

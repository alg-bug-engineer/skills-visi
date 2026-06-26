import type { ProblemEvidence } from '../types/evidence'
import type { GovernanceSuggestionPayload } from '../types/presentation'
import { formatPercent } from './evidencePresentation'

function simplifyEvidenceSummary(summary: string): string {
  return summary
    .replace(/DWS\s*周模式/g, '历史周规律')
    .replace(/DWD/g, '近几日明细')
    .replace(/无日历明细/g, '缺少逐日明细')
}

function formatStoryBeat(beat: { title?: string; text?: string }): string {
  const title = beat.title?.replace(/[：:]\s*$/, '') ?? ''
  const text = beat.text ?? ''
  return title ? `${title}：${text}` : text
}

/** 渠化图左上角：问题验证分条摘要 */
export function buildEvidenceListItems(evidence: ProblemEvidence): string[] {
  if (evidence.diagnosis_story?.length) {
    return evidence.diagnosis_story.map(formatStoryBeat).filter(Boolean)
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
  if (dow?.dow_label) {
    const rate =
      dow.hit_rate != null ? `（约 ${(dow.hit_rate * 100).toFixed(0)}% 的周会中招）` : ''
    parts.push(`每到周${dow.dow_label.replace(/^周/, '')}更容易出现这个问题${rate}`)
  }

  const sat = evidence.metrics?.saturation_rate
  if (sat != null && sat >= 0.85) {
    parts.push(`路口整体饱和度 ${formatPercent(sat)}，已过饱和`)
  } else if (sat != null && sat >= 0.65) {
    parts.push(`路口整体饱和度 ${formatPercent(sat)}，处于偏高`)
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
): string | null {
  if (!suggestion?.narrative) return null

  const dir = suggestion.direction === 'increase' ? '增加' : '减少'
  const head =
    suggestion.delta_seconds != null
      ? `建议${dir}主要方向绿灯约 ${Math.abs(suggestion.delta_seconds)} 秒。`
      : ''
  return [head, suggestion.narrative].filter(Boolean).join('\n')
}

/** 治理建议列表项（按行/句号拆分） */
export function buildSuggestionListItems(
  suggestion: GovernanceSuggestionPayload | null | undefined,
): string[] {
  const text = buildSuggestionPlainText(suggestion)
  if (!text) return []

  const lines = text
    .split(/\n+/)
    .flatMap((line) => line.split(/(?<=[。；])/))
    .map((s) => s.trim())
    .filter(Boolean)

  return lines.length ? lines : [text]
}

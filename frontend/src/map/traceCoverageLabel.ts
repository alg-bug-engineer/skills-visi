/** 路段覆盖溯源：占比展示口径（ratio 为 0–1 小数；低样本时附带趟次）。 */

import { formatTargetFlowShareLabel } from './traceLabels'

export const LOW_SAMPLE_TARGET_FLOW = 10

export function normalizeCoverageRatio(ratio: number | null | undefined): number | null {
  if (ratio == null || !Number.isFinite(ratio)) return null
  if (ratio > 1 && ratio <= 100) return ratio / 100
  return Math.max(0, Math.min(1, ratio))
}

export function formatCoverageShare(opts: {
  ratio: number | null | undefined
  flow?: number | null
  targetFlow?: number | null
}): string {
  const normalized = normalizeCoverageRatio(opts.ratio)
  if (normalized == null) return '暂无'
  const pct = (normalized * 100).toFixed(1)
  const flow = opts.flow
  const target = opts.targetFlow
  if (typeof target === 'number' && target > 0 && target < LOW_SAMPLE_TARGET_FLOW) {
    if (typeof flow === 'number') return `${flow}/${target}趟 (${pct}%)`
    return `约${pct}%`
  }
  return `${pct}%`
}

export function buildSegmentCoverageLabelHtml(opts: {
  name: string
  ratio: number | null | undefined
  flow?: number | null
  targetFlow?: number | null
  kind?: 'intersection' | 'link'
}): string {
  const share = formatCoverageShare(opts)
  const title = (opts.name || (opts.kind === 'link' ? '路段' : '来源路口')).trim()
  const metric =
    opts.kind === 'link'
      ? `覆盖 ${share}`
      : formatTargetFlowShareLabel(
          opts.ratio != null && Number.isFinite(opts.ratio)
            ? opts.ratio > 1 && opts.ratio <= 100
              ? opts.ratio
              : opts.ratio * 100
            : null,
        )
  return (
    `<div class="trace-label">` +
    `<div class="trace-name">${title}</div>` +
    `<div class="trace-metric">${metric}</div>` +
    `</div>`
  )
}

export function buildSegmentCoverageLinkHtml(opts: {
  name?: string | null
  ratio: number | null | undefined
  flow?: number | null
  targetFlow?: number | null
}): string {
  const share = formatCoverageShare(opts)
  const title = (opts.name || '路段').trim()
  return (
    `<div class="trace-label">` +
    `<div class="trace-name">${title}</div>` +
    `<div class="trace-metric">覆盖 ${share}</div>` +
    `</div>`
  )
}

export function buildSegmentCoverageTargetHtml(opts: {
  name?: string | null
  targetFlow?: number | null
  lowSample?: boolean
}): string {
  const name = opts.name ?? '目标路口'
  return `<div class="trace-label"><div class="trace-name">目标：${name}</div></div>`
}

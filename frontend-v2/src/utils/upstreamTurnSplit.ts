import type { UpstreamTurnSplit } from '../types/map'

function movementLabel(row: UpstreamTurnSplit): string {
  if (row.feed_direction) return row.feed_direction
  return row.turn ?? ''
}

function formatPct(pct: number): string {
  return Number.isInteger(pct) ? `${pct}` : pct.toFixed(1)
}

function usableRows(split: UpstreamTurnSplit[] | null | undefined): UpstreamTurnSplit[] {
  if (!split?.length) return []
  return split
    .filter((row) => {
      if (!movementLabel(row) || row.data_gap || row.share_pct == null) return false
      const pct = Number(row.share_pct)
      return Number.isFinite(pct) && pct > 0
    })
    .sort((a, b) => Number(b.share_pct) - Number(a.share_pct))
}

/**
 * 将上游路口 turn_split 格式化为「东直行76.2% · 北右转16.1%」；
 * 优先使用 feed_direction（方位+转向），无 share_pct 或 data_gap 的项不展示。
 */
export function formatUpstreamTurnSplit(
  split: UpstreamTurnSplit[] | null | undefined,
): string {
  const rows = usableRows(split)
  if (!rows.length) return ''
  return rows
    .map((row) => `${movementLabel(row)}${formatPct(Number(row.share_pct))}%`)
    .join(' · ')
}

/** 列表 HTML：每行「方位转向」+ 占比，供地图浮动标注。 */
export function formatUpstreamTurnSplitHtml(
  split: UpstreamTurnSplit[] | null | undefined,
): string {
  const rows = usableRows(split)
  if (!rows.length) return ''
  return rows
    .map((row) => {
      const label = movementLabel(row)
      const pct = formatPct(Number(row.share_pct))
      return (
        `<div class="us-split-item">` +
        `<span class="us-move">${label}</span>` +
        `<span class="us-pct">${pct}%</span>` +
        `</div>`
      )
    })
    .join('')
}

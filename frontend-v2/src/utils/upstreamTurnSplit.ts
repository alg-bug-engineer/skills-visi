import type { UpstreamTurnSplit } from '../types/map'

/** 上游路口汇入车流转向占比展示顺序 */
const TURN_ORDER = ['左转', '直行', '右转'] as const

/**
 * 将上游路口 turn_split 格式化为「左转22% · 直行67%」；
 * 无 share_pct 或 data_gap 的项不展示。
 */
export function formatUpstreamTurnSplit(
  split: UpstreamTurnSplit[] | null | undefined,
): string {
  if (!split?.length) return ''
  const byTurn = new Map<string, UpstreamTurnSplit>()
  for (const row of split) {
    if (!row.turn || row.data_gap || row.share_pct == null) continue
    const pct = Number(row.share_pct)
    if (!Number.isFinite(pct) || pct <= 0) continue
    byTurn.set(row.turn, row)
  }
  const parts: string[] = []
  for (const turn of TURN_ORDER) {
    const row = byTurn.get(turn)
    if (row?.share_pct == null) continue
    const pct = Number(row.share_pct)
    const label = Number.isInteger(pct) ? `${pct}` : pct.toFixed(1)
    parts.push(`${turn}${label}%`)
  }
  return parts.join(' · ')
}

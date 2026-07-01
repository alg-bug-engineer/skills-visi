import type { UpstreamCorrelateMap } from '../types/map'

/**
 * 理解过程「原因诊断」：溯源表全量上游路口事实陈述。
 */
export function buildCorrelateProcessText(
  map: UpstreamCorrelateMap | null | undefined,
  targetLabel?: string | null,
): string {
  if (!map?.intersections?.length) return ''

  const approach = (targetLabel || map.approach || '').trim()
  const stats = map.stats
  const distinct = stats?.distinct_upstream ?? 0
  const mainCount = stats?.main_corridor_count ?? map.main_corridor_chain?.length ?? 0

  const lines: string[] = [
    `流量溯源：${approach} 统计途经上游路口 ${distinct} 个（主走廊链 ${mainCount} 个）。`,
  ]

  const chain = map.main_corridor_chain ?? []
  if (chain.length) {
    const chainTxt = chain
      .map((n) => `${n.name}（途经 ${n.path_coverage}%）`)
      .join(' → ')
    lines.push(`主走廊：${chainTxt}`)
  }

  return lines.join('\n')
}

/** 地图展示停留时长（ms）：随上游路口数略增。 */
export function upstreamCorrelateDurationMs(map: UpstreamCorrelateMap | null | undefined): number {
  const n = map?.intersections?.length ?? 0
  return Math.min(8000, Math.max(3200, 2800 + n * 40))
}

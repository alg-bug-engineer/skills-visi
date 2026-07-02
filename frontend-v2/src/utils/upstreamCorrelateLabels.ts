import type { CorrelateTraceIntersection, UpstreamCorrelateMap } from '../types/map'

const DIR8_LABELS: Record<number, string> = {
  0: '北',
  1: '东北',
  2: '东',
  3: '东南',
  4: '南',
  5: '西南',
  6: '西',
  7: '西北',
}

const TURN_DIR_LABELS: Record<number, string> = {
  0: '掉头',
  1: '左转',
  2: '直行',
  3: '右转',
}

/** 溯源地图：途经占比低于此值的上游路口不渲染。 */
export const MIN_PATH_COVERAGE = 5

/** 上游路口是否具备坐标、link 与有效途经占比。 */
export function isRenderableUpstream(node: CorrelateTraceIntersection): boolean {
  if (node.role === 'target') return true
  const cov = node.path_coverage
  if (cov == null || cov < MIN_PATH_COVERAGE) return false
  if (!node.center?.length) return false
  if (!node.links?.length) return false
  return true
}

/** 去除路口名末尾「路口」后缀。 */
export function stripIntersectionSuffix(name: string): string {
  return name.replace(/路口\s*$/u, '').trim() || name
}

/** 溯源表 cor_f_dir8_no + cor_turn_dir_no → 如「东直行」。 */
export function formatCorrelateFeedDirection(
  dir8?: number | null,
  turnNo?: number | null,
): string {
  const dir = DIR8_LABELS[Number(dir8 ?? 0)] ?? ''
  const turn = TURN_DIR_LABELS[Number(turnNo ?? 2)] ?? '直行'
  return `${dir}${turn}`
}

/** 流量占比 → 节点尺寸/透明度/发光强度（0–100）。 */
export function coverageNodeStyle(coverage: number): {
  size: number
  opacity: number
  glow: number
} {
  const t = Math.max(0, Math.min(1, coverage / 100))
  const eased = Math.sqrt(t)
  return {
    size: 10 + eased * 14,
    opacity: 0.42 + eased * 0.58,
    glow: 0.35 + eased * 0.65,
  }
}

export function buildCorrelateLabelHtml(node: CorrelateTraceIntersection): string {
  const cov = node.path_coverage ?? 0
  const name = stripIntersectionSuffix(node.name)
  const direction = formatCorrelateFeedDirection(node.cor_f_dir8_no, node.cor_turn_dir_no)
  return (
    `<div class="us-label">` +
    `<div class="us-name">${name}</div>` +
    `<div class="us-metric" style="color:#fbbf24">${direction} · 途经 ${cov.toFixed(1)}%</div>` +
    `</div>`
  )
}

/** 默认展开标签：主走廊 hop1；无走廊时取占比最高上游路口。 */
export function defaultOpenUpstreamId(map: UpstreamCorrelateMap): string | null {
  const chainId = map.main_corridor_chain?.[0]?.inter_id
  if (chainId) return chainId

  const hop1 = map.intersections.find(
    (n) => n.role === 'upstream' && n.corridor_hop === 1,
  )
  if (hop1) return hop1.inter_id

  const upstream = map.intersections
    .filter((n) => n.role === 'upstream')
    .sort((a, b) => (b.path_coverage ?? 0) - (a.path_coverage ?? 0))
  return upstream[0]?.inter_id ?? null
}

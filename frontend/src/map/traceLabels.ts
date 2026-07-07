/**
 * 溯源节点样式/标签纯函数（呈现逻辑对齐 references/流量溯源 upstreamCorrelateLabels.ts
 * 与 upstreamStoryboard.upstreamEdgeStrokeWeight，仅配色落到本项目主题）。
 */

/** 溯源地图：途经占比低于此值的上游路口不渲染（对齐参考 MIN_PATH_COVERAGE）。 */
export const MIN_PATH_COVERAGE = 5

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

/** 干线路径线宽：低流量仍可见，高流量加粗但不淹没底图（对齐参考）。 */
export function upstreamEdgeStrokeWeight(flowPct: number | null | undefined): number {
  const pct = Math.max(0, Math.min(100, Number(flowPct) || 0))
  return 2.8 + Math.sqrt(pct / 100) * 5.7
}

/** 流量占比 → 节点尺寸/透明度/发光强度（0–100，对齐参考 coverageNodeStyle）。 */
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

/** 去除路口名末尾「路口」后缀。 */
export function stripIntersectionSuffix(name: string): string {
  return name.replace(/路口\s*$/u, '').trim() || name
}

/** dir8 + turn_dir_no → 如「东直行」。 */
export function formatFeedDirection(
  dir8?: number | null,
  turnNo?: number | null,
): string {
  const dir = DIR8_LABELS[Number(dir8 ?? 0)] ?? ''
  const turn = TURN_DIR_LABELS[Number(turnNo ?? 2)] ?? '直行'
  return `${dir}${turn}`
}

/** 归一化 movement/turn 英文 → 中文转向。 */
export function turnLabelFromMovement(movement?: string | null): string {
  const raw = String(movement ?? '').toLowerCase()
  if (raw.includes('left')) return '左转'
  if (raw.includes('right')) return '右转'
  if (raw.includes('uturn') || raw.includes('u_turn')) return '掉头'
  if (raw.includes('through') || raw.includes('straight')) return '直行'
  return String(movement ?? '')
}

/** 上游节点标签 HTML：名称 + 方向 + 途经占比（缺占比显示「拓扑」，对齐参考不造数）。 */
export function buildUpstreamLabelHtml(opts: {
  name: string
  direction?: string
  coverage?: number | null
}): string {
  const name = stripIntersectionSuffix(opts.name || '上游')
  const dir = opts.direction ? `${opts.direction} · ` : ''
  const cov =
    opts.coverage != null && Number.isFinite(opts.coverage)
      ? `途经 ${Number(opts.coverage).toFixed(1)}%`
      : '拓扑'
  return (
    `<div class="trace-label">` +
    `<div class="trace-name">${name}</div>` +
    `<div class="trace-metric" style="color:#fbbf24">${dir}${cov}</div>` +
    `</div>`
  )
}

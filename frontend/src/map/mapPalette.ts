/** 地图色板逐值提取自 references/3d源码/src/main.js，禁止近似替换。 */
export const THREE_MAP_PALETTE = {
  background: '#030812',
  fog: '#061225',
  ground: '#07111f',
  groundEmissive: '#06192b',
  contextRoad: '#214a66',
  express: '#ff9d1b',
  trunk: '#ffc640',
  primaryRoad: '#5ccfff',
  secondaryRoad: '#2189ff',
  defaultRoad: '#1f4d7c',
  boundary: '#4ee9ff',
} as const

export const TRAFFIC_PALETTE = {
  low: '#39dfff',
  medium: '#ffd247',
  high: '#ff8d1f',
  severe: '#ff3c1f',
} as const

/** 业务语义映射到 3D 源码色板；策略成功态保留政务系统的绿色语义。 */
export const MAP_PALETTE = {
  primary: THREE_MAP_PALETTE.secondaryRoad,
  flow: TRAFFIC_PALETTE.low,
  warning: TRAFFIC_PALETTE.medium,
  danger: TRAFFIC_PALETTE.severe,
  success: '#2ed573',
  reasoning: THREE_MAP_PALETTE.primaryRoad,
  text: '#dff7ff',
  muted: THREE_MAP_PALETTE.defaultRoad,
} as const

export const TRACE_PALETTE = {
  target: { glow: MAP_PALETTE.danger, core: MAP_PALETTE.danger },
  upstreamMain: { glow: MAP_PALETTE.flow, core: MAP_PALETTE.flow },
  upstreamOther: { glow: MAP_PALETTE.primary, core: MAP_PALETTE.primary },
  downstreamMain: { glow: MAP_PALETTE.success, core: MAP_PALETTE.success },
  downstreamOther: { glow: MAP_PALETTE.reasoning, core: MAP_PALETTE.reasoning },
} as const

/** 对齐 3D 源码 getRoadType：数据库只有 fc 时采用同一降级分级。 */
export function roadColorForFunctionalClass(fc: unknown): string {
  const value = Number(fc)
  if (Number.isFinite(value) && value <= 2) return THREE_MAP_PALETTE.trunk
  if (value === 3) return THREE_MAP_PALETTE.primaryRoad
  if (value === 4) return THREE_MAP_PALETTE.secondaryRoad
  return THREE_MAP_PALETTE.defaultRoad
}

/** 目标附近红 → 橙 → 黄 → 远端青，对齐 3D 源码四级交通色。 */
export function propagationColor(
  order: number,
  total: number,
  palette: {
    severe?: string
    high?: string
    medium?: string
    low?: string
    near?: string
    middle?: string
    far?: string
  } = {},
): string {
  const progress = total <= 1 ? 0 : Math.max(0, Math.min(1, order / (total - 1)))
  if (progress <= 0.2) return palette.severe ?? palette.near ?? TRAFFIC_PALETTE.severe
  if (progress <= 0.46) return palette.high ?? TRAFFIC_PALETTE.high
  if (progress <= 0.72) return palette.medium ?? palette.middle ?? TRAFFIC_PALETTE.medium
  return palette.low ?? palette.far ?? TRAFFIC_PALETTE.low
}

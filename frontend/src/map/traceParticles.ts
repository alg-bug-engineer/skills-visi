/**
 * 溯源粒子/折线纯函数（呈现逻辑对齐 references/流量溯源 traceParticles.ts，
 * 仅本项目坐标类型别名不同）。所有函数纯粹、无副作用，供单测覆盖。
 */
export type LngLat = [number, number]

function segmentLengths(path: LngLat[]): number[] {
  const lengths: number[] = []
  for (let i = 1; i < path.length; i += 1) {
    lengths.push(Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]))
  }
  return lengths
}

/** 沿折线按归一化进度 t∈[0,1] 线性插值，端点夹紧。空路径返回 null。 */
export function interpolatePath(path: LngLat[], t: number): LngLat | null {
  const pts = (path ?? []).filter(Boolean)
  if (!pts.length) return null
  if (pts.length === 1) return [pts[0][0], pts[0][1]]
  const clamped = Math.max(0, Math.min(1, t))
  const lengths = segmentLengths(pts)
  const total = lengths.reduce((sum, value) => sum + value, 0)
  if (total <= 0) return [pts[0][0], pts[0][1]]
  const target = total * clamped
  let passed = 0
  for (let i = 0; i < lengths.length; i += 1) {
    const next = passed + lengths[i]
    if (target <= next || i === lengths.length - 1) {
      const local = lengths[i] <= 0 ? 0 : (target - passed) / lengths[i]
      const a = pts[i]
      const b = pts[i + 1]
      return [a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local]
    }
    passed = next
  }
  return [pts[pts.length - 1][0], pts[pts.length - 1][1]]
}

/** 返回从起点蔓延到 t 的真实折线前缀，用于逐帧扩散线。 */
export function pathPrefix(path: LngLat[], t: number): LngLat[] {
  const pts = (path ?? []).filter(Boolean)
  if (pts.length < 2) return pts.map((p) => [p[0], p[1]])
  const clamped = Math.max(0, Math.min(1, t))
  if (clamped >= 1) return pts.map((p) => [p[0], p[1]])
  const lengths = segmentLengths(pts)
  const total = lengths.reduce((sum, value) => sum + value, 0)
  if (total <= 0) return [pts[0], pts[0]]
  const target = total * clamped
  const out: LngLat[] = [[pts[0][0], pts[0][1]]]
  let passed = 0
  for (let i = 0; i < lengths.length; i += 1) {
    const next = passed + lengths[i]
    if (target >= next) {
      out.push([pts[i + 1][0], pts[i + 1][1]])
      passed = next
      continue
    }
    const local = lengths[i] <= 0 ? 0 : (target - passed) / lengths[i]
    const a = pts[i]
    const b = pts[i + 1]
    out.push([a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local])
    break
  }
  return out.length >= 2 ? out : [out[0], out[0]]
}

/** 将真实 path 朝“目标点 → 上游来源”定向，只允许反转，不生成新几何。 */
export function orientPathFromOrigin(path: LngLat[], origin: LngLat | null | undefined): LngLat[] {
  const pts = (path ?? []).filter(Boolean)
  if (pts.length < 2 || !origin) return pts.map((p) => [p[0], p[1]])
  const first = Math.hypot(pts[0][0] - origin[0], pts[0][1] - origin[1])
  const last = Math.hypot(pts[pts.length - 1][0] - origin[0], pts[pts.length - 1][1] - origin[1])
  const oriented = first <= last ? pts : [...pts].reverse()
  return oriented.map((p) => [p[0], p[1]])
}

/** 沿折线等距采样 count 个点（含起点），用于布置原位流动点。 */
export function sampleAlongPath(path: LngLat[], count: number): LngLat[] {
  const pts = (path ?? []).filter(Boolean)
  if (!pts.length || count <= 0) return []
  if (count === 1) return [interpolatePath(pts, 0)!]
  const out: LngLat[] = []
  for (let i = 0; i < count; i++) {
    const pos = interpolatePath(pts, i / (count - 1))
    if (pos) out.push(pos)
  }
  return out
}

/** 折线经纬度近似总长（度），仅用于相对比较 / 时长映射。 */
export function approxPathLength(path: LngLat[]): number {
  const pts = (path ?? []).filter(Boolean)
  let total = 0
  for (let i = 1; i < pts.length; i++) {
    total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
  }
  return total
}

/** 按路径长度映射粒子流动周期（毫秒），夹在 1200~2800ms，长干线更慢。 */
export function particleDurationFor(path: LngLat[]): number {
  const len = approxPathLength(path)
  const ms = 1200 + len * 90000
  return Math.max(1200, Math.min(2800, Math.round(ms)))
}

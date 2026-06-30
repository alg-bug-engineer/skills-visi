export type LngLat = [number, number]

/** 沿折线按归一化进度 t∈[0,1] 线性插值，端点夹紧。空路径返回 null。 */
export function interpolatePath(path: LngLat[], t: number): LngLat | null {
  const pts = (path ?? []).filter(Boolean)
  if (!pts.length) return null
  if (pts.length === 1) return [pts[0][0], pts[0][1]]
  const clamped = Math.max(0, Math.min(1, t))
  const segT = clamped * (pts.length - 1)
  const idx = Math.min(pts.length - 2, Math.floor(segT))
  const local = segT - idx
  const a = pts[idx]
  const b = pts[idx + 1]
  return [a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local]
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

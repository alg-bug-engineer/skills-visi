/**
 * channelizationGeometry.ts
 *
 * 渠化几何纯函数库（从 channelization-amap-demo.html 提取并 TS 化）。
 * 供 AMap 渠化渲染器使用：经纬度↔局部米投影、臂方位角、归臂、路口框、
 * 车道功能码解析与配色、转向箭头 SVG。
 *
 * 坐标约定（臂局部空间）：
 *   u = 沿臂朝外（arm bearing 方向）
 *   v = 面朝外时的右手侧
 *   中国右行：进口道在 -v（左侧），出口道在 +v（右侧）
 */

export interface ChannelLink {
  link_id?: string
  link_role?: string // 'entrance' | 'exit'
  dir4_label?: string
  road_name?: string
  road_level?: string
  lane_num?: number
  c_lane_num?: number
  lane_info?: string
  geom?: string
  path?: Array<[number, number]>
  /** 角度回退：进口取 (t_angle+180)%360，出口取 f_angle（与 channelizationLayer.js 一致） */
  t_angle?: number
  f_angle?: number
  entrance_angle?: number | null
}

export interface ChannelArm {
  angle: number
  inLink: ChannelLink | null
  outLink: ChannelLink | null
}

/* ── 几何 / 样式常量 ───────────────────────────────────────────────────────── */
export const LANE_W = 3.3 // 车道宽(米)
export const ARM_LEN = 64 // 渠化绘制长度(米)
export const MEDIAN_W = 1.2 // 进出口中央分隔半宽(米)
export const CW_GAP = 2.0 // 停止线到斑马线间距
export const CW_LEN = 6.0 // 斑马线长度

export const MOVE_COLOR = {
  left: '#3b82f6',
  straight: '#94a3b8',
  right: '#22c55e',
  mixed: '#14b8a6',
  uturn: '#a855f7',
  exit: '#cbd5e1',
} as const

/** LOD 缩放阈值：<L1 路网；[L1,L2) 轮廓；>=L2 全渠化 */
export const LOD_THRESHOLDS = { L1: 16, L2: 18 } as const

const R = 6378137

/* ── 投影：臂局部坐标(米) → 经纬度 ─────────────────────────────────────────── */
export function metersToLngLat(
  center: [number, number],
  u: number,
  v: number,
  bearingDeg: number,
): [number, number] {
  const br = (bearingDeg * Math.PI) / 180
  const fE = Math.sin(br)
  const fN = Math.cos(br) // 朝外单位向量(东,北)
  const rE = Math.cos(br)
  const rN = -Math.sin(br) // 右手侧单位向量(东,北)
  const dE = u * fE + v * rE
  const dN = u * fN + v * rN
  const lat = center[1] + ((dN / R) * 180) / Math.PI
  const lng = center[0] + ((dE / (R * Math.cos((center[1] * Math.PI) / 180))) * 180) / Math.PI
  return [lng, lat]
}

/* ── 地理方位角(度, 正北=0 顺时针) ─────────────────────────────────────────── */
export function geoBearing(p0: [number, number], p1: [number, number]): number {
  const dLat = p1[1] - p0[1]
  const dLon = (p1[0] - p0[0]) * Math.cos(((p0[1] + p1[1]) * Math.PI) / 360)
  return ((Math.atan2(dLon, dLat) * 180) / Math.PI + 360) % 360
}

export function angleDiff(a: number, b: number): number {
  const d = Math.abs(((a - b + 360) % 360))
  return d > 180 ? 360 - d : d
}

/* ── WKT/path → 经纬度序列 ─────────────────────────────────────────────────── */
export function linkPath(link: ChannelLink): Array<[number, number]> {
  if (link.path?.length) return link.path
  const g = link.geom
  if (g && g.includes('(')) {
    const inner = g.slice(g.indexOf('(') + 1, g.lastIndexOf(')'))
    return inner
      .split(',')
      .map((s) => s.trim().split(/\s+/).map(Number) as [number, number])
      .filter((p) => p.length === 2 && !Number.isNaN(p[0]) && !Number.isNaN(p[1]))
  }
  return []
}

/* ── 由真实 geom 求路臂朝外方位角（带角度回退） ───────────────────────────── */
export function armAngleFromLink(link: ChannelLink): number {
  const isEntrance = link.link_role !== 'exit'
  const p = linkPath(link)
  if (p.length >= 2) {
    const [near, outer] = isEntrance ? [p[p.length - 1], p[p.length - 2]] : [p[0], p[1]]
    return geoBearing(near, outer)
  }
  if (isEntrance && link.t_angle != null) return ((link.t_angle + 180) % 360 + 360) % 360
  if (!isEntrance && link.f_angle != null) return ((link.f_angle % 360) + 360) % 360
  if (link.entrance_angle != null) return ((link.entrance_angle % 360) + 360) % 360
  return 0
}

/* ── lane_info 解析 ────────────────────────────────────────────────────────── */
export function parseLaneInfo(link: ChannelLink): string[] {
  if (link.lane_info && link.lane_info !== 'null') {
    return link.lane_info.split('|').filter(Boolean)
  }
  return Array(link.c_lane_num || link.lane_num || 1).fill('C')
}

/* ── 车道功能码 → 配色 / 中文标签 ─────────────────────────────────────────── */
export function laneColor(code: string): string {
  const c = (code || 'C').toUpperCase()
  const movs: string[] = []
  if (c.includes('B')) movs.push('left')
  if (c.includes('C')) movs.push('straight')
  if (c.includes('D')) movs.push('right')
  if (c.includes('A')) movs.push('uturn')
  if (movs.length === 0) return MOVE_COLOR.straight
  if (movs.length > 1) return MOVE_COLOR.mixed
  return MOVE_COLOR[movs[0] as keyof typeof MOVE_COLOR]
}

const MOVE_CN: Record<string, string> = { A: '掉头', B: '左转', C: '直行', D: '右转' }
export function laneLabel(code: string): string {
  return (code || 'C')
    .toUpperCase()
    .split('')
    .map((ch) => MOVE_CN[ch] || '')
    .join('')
}

/* ── 归组成「臂」：进/出口按方位角(<25°)合并，取最宽 ─────────────────────── */
export function gatherArms(links: ChannelLink[]): ChannelArm[] {
  const ins = links.filter((l) => l.link_role !== 'exit')
  const outs = links.filter((l) => l.link_role === 'exit')
  const arms: ChannelArm[] = []
  const find = (angle: number) => arms.find((a) => angleDiff(a.angle, angle) < 25)
  for (const lk of ins) {
    const angle = armAngleFromLink(lk)
    let arm = find(angle)
    if (!arm) {
      arm = { angle, inLink: null, outLink: null }
      arms.push(arm)
    }
    if (!arm.inLink || parseLaneInfo(lk).length > parseLaneInfo(arm.inLink).length) {
      arm.inLink = lk
      arm.angle = angle
    }
  }
  for (const lk of outs) {
    const angle = armAngleFromLink(lk)
    let arm = find(angle)
    if (!arm) {
      arm = { angle, inLink: null, outLink: null }
      arms.push(arm)
    }
    const w = lk.c_lane_num || lk.lane_num || 0
    const cur = arm.outLink ? arm.outLink.c_lane_num || arm.outLink.lane_num || 0 : -1
    if (w > cur) arm.outLink = lk
  }
  return arms
}

/* ── 路口框半径：相邻臂斑马线不重叠 ───────────────────────────────────────── */
export function calcBoxR(arms: ChannelArm[]): number {
  let r = 18
  for (const a of arms) {
    const nI = a.inLink ? parseLaneInfo(a.inLink).length : 0
    const nO = a.outLink ? a.outLink.c_lane_num || a.outLink.lane_num || 0 : 0
    r = Math.max(r, ((nI + nO) * LANE_W) / 2 + CW_GAP + CW_LEN + 1.5)
  }
  return Math.min(Math.max(r, 18), 60)
}

/* ── 转向箭头 SVG（图标朝上=朝向路口；按功能码组合绘制） ─────────────────── */
export function arrowSvg(code: string, color: string): string {
  const c = (code || 'C').toUpperCase()
  const has = (ch: string) => c.includes(ch)
  const seg: string[] = []
  const head = (x: number, y: number, dx: number, dy: number) => {
    const a = Math.atan2(dy, dx)
    const s = 7
    const lx = x - s * Math.cos(a - 0.5)
    const ly = y - s * Math.sin(a - 0.5)
    const rx = x - s * Math.cos(a + 0.5)
    const ry = y - s * Math.sin(a + 0.5)
    return `M${lx.toFixed(1)} ${ly.toFixed(1)} L${x} ${y} L${rx.toFixed(1)} ${ry.toFixed(1)}`
  }
  const hasStraight = has('C')
  const hasLeft = has('B')
  const hasRight = has('D')
  const hasU = has('A')
  const forkY = 38
  seg.push(`M24 60 L24 ${hasStraight ? 14 : forkY}`)
  if (hasStraight) seg.push(head(24, 14, 0, -1))
  if (hasLeft) {
    seg.push(`M24 ${forkY} L11 ${forkY - 11}`)
    seg.push(head(11, forkY - 11, -13, -11))
  }
  if (hasRight) {
    seg.push(`M24 ${forkY} L37 ${forkY - 11}`)
    seg.push(head(37, forkY - 11, 13, -11))
  }
  if (hasU) {
    seg.push(`M24 ${forkY} Q12 ${forkY - 14} 12 ${forkY - 2} L12 ${forkY + 9}`)
    seg.push(head(12, forkY + 9, 0, 1))
  }
  const d = seg.join(' ')
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="64" viewBox="0 0 48 64">` +
    `<path d="${d}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>`
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

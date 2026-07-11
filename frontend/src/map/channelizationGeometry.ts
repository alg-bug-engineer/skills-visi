export type LngLat = [number, number]

export interface ChannelLink {
  link_id?: string
  link_role?: string
  dir4_label?: string
  dir8_label?: string
  road_name?: string
  lane_num?: number
  c_lane_num?: number
  lane_info?: string | null
  turn_move?: string | null
  path?: LngLat[]
  t_angle?: number
  f_angle?: number
  entrance_angle?: number | null
  metrics?: Record<string, number | null | undefined>
}

export interface ChannelArm {
  angle: number
  inLink: ChannelLink | null
  outLink: ChannelLink | null
}

export const LANE_W = 3.3
export const ARM_LEN = 64
export const MEDIAN_W = 1.2
export const CW_GAP = 2.0
export const CW_LEN = 6.0
export const LOD_THRESHOLDS = { L1: 16, L2: 18 } as const

export const MOVE_COLOR = {
  left: '#3b82f6',
  straight: '#94a3b8',
  right: '#22c55e',
  mixed: '#14b8a6',
  uturn: '#a855f7',
  exit: '#cbd5e1',
} as const

const R = 6378137

export function metersToLngLat(center: LngLat, u: number, v: number, bearingDeg: number): LngLat {
  const br = (bearingDeg * Math.PI) / 180
  const fE = Math.sin(br)
  const fN = Math.cos(br)
  const rE = Math.cos(br)
  const rN = -Math.sin(br)
  const dE = u * fE + v * rE
  const dN = u * fN + v * rN
  const lat = center[1] + ((dN / R) * 180) / Math.PI
  const lng = center[0] + ((dE / (R * Math.cos((center[1] * Math.PI) / 180))) * 180) / Math.PI
  return [lng, lat]
}

export function geoBearing(p0: LngLat, p1: LngLat): number {
  const dLat = p1[1] - p0[1]
  const dLon = (p1[0] - p0[0]) * Math.cos(((p0[1] + p1[1]) * Math.PI) / 360)
  return ((Math.atan2(dLon, dLat) * 180) / Math.PI + 360) % 360
}

export function angleDiff(a: number, b: number): number {
  const d = Math.abs((a - b + 360) % 360)
  return d > 180 ? 360 - d : d
}

export function parseLaneInfo(link: ChannelLink): string[] {
  if (link.lane_info && link.lane_info !== 'null') return link.lane_info.split('|').filter(Boolean)
  return Array(link.c_lane_num || link.lane_num || 1).fill('C')
}

export function armAngleFromLink(link: ChannelLink): number {
  const isEntrance = String(link.link_role ?? '').toLowerCase() !== 'exit'
  const path = link.path ?? []
  if (path.length >= 2) {
    const [near, outer] = isEntrance ? [path[path.length - 1], path[path.length - 2]] : [path[0], path[1]]
    return geoBearing(near, outer)
  }
  if (isEntrance && link.t_angle != null) return ((link.t_angle + 180) % 360 + 360) % 360
  if (!isEntrance && link.f_angle != null) return ((link.f_angle % 360) + 360) % 360
  if (link.entrance_angle != null) return ((link.entrance_angle % 360) + 360) % 360
  return 0
}

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

export function gatherArms(links: ChannelLink[]): ChannelArm[] {
  const entrances = links.filter((l) => String(l.link_role ?? '').toLowerCase() !== 'exit')
  const exits = links.filter((l) => String(l.link_role ?? '').toLowerCase() === 'exit')
  const arms: ChannelArm[] = []
  const find = (angle: number) => arms.find((a) => angleDiff(a.angle, angle) < 25)

  for (const link of entrances) {
    const angle = armAngleFromLink(link)
    let arm = find(angle)
    if (!arm) {
      arm = { angle, inLink: null, outLink: null }
      arms.push(arm)
    }
    if (!arm.inLink || parseLaneInfo(link).length > parseLaneInfo(arm.inLink).length) {
      arm.inLink = link
      arm.angle = angle
    }
  }

  for (const link of exits) {
    const angle = armAngleFromLink(link)
    let arm = find(angle)
    if (!arm) {
      arm = { angle, inLink: null, outLink: null }
      arms.push(arm)
    }
    const laneCount = link.c_lane_num || link.lane_num || 0
    const current = arm.outLink ? arm.outLink.c_lane_num || arm.outLink.lane_num || 0 : -1
    if (laneCount > current) arm.outLink = link
  }

  return arms
}

/** 按 ticket 方位匹配进口 arm（dir8_label 或角度差 < 25°）。 */
export function findArmForDirection(arms: ChannelArm[], direction: string | null | undefined): ChannelArm | null {
  const label = String(direction ?? '').trim()
  if (!label) return null
  for (const arm of arms) {
    const dir8 = String(arm.inLink?.dir8_label ?? arm.inLink?.dir4_label ?? '')
    if (dir8 && label.split('').some((ch) => dir8.includes(ch))) return arm
  }
  const bearing = (() => {
    if (label.includes('东') && label.includes('南')) return 135
    if (label.includes('东') && label.includes('北')) return 45
    if (label.includes('西') && label.includes('南')) return 225
    if (label.includes('西') && label.includes('北')) return 315
    if (label.includes('东')) return 90
    if (label.includes('西')) return 270
    if (label.includes('南')) return 180
    if (label.includes('北')) return 0
    return null
  })()
  if (bearing == null) return null
  let best: ChannelArm | null = null
  let bestDiff = 999
  for (const arm of arms) {
    const d = angleDiff(arm.angle, bearing)
    if (d < bestDiff) {
      bestDiff = d
      best = arm
    }
  }
  return bestDiff < 25 ? best : null
}

export function calcBoxR(arms: ChannelArm[]): number {
  let r = 18
  for (const arm of arms) {
    const nIn = arm.inLink ? parseLaneInfo(arm.inLink).length : 0
    const nOut = arm.outLink ? arm.outLink.c_lane_num || arm.outLink.lane_num || 0 : 0
    r = Math.max(r, ((nIn + nOut) * LANE_W) / 2 + CW_GAP + CW_LEN + 1.5)
  }
  return Math.min(Math.max(r, 18), 60)
}

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
  const forkY = 38
  seg.push(`M24 60 L24 ${has('C') ? 14 : forkY}`)
  if (has('C')) seg.push(head(24, 14, 0, -1))
  if (has('B')) {
    seg.push(`M24 ${forkY} L11 ${forkY - 11}`)
    seg.push(head(11, forkY - 11, -13, -11))
  }
  if (has('D')) {
    seg.push(`M24 ${forkY} L37 ${forkY - 11}`)
    seg.push(head(37, forkY - 11, 13, -11))
  }
  if (has('A')) {
    seg.push(`M24 ${forkY} Q12 ${forkY - 14} 12 ${forkY - 2} L12 ${forkY + 9}`)
    seg.push(head(12, forkY + 9, 0, 1))
  }
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="64" viewBox="0 0 48 64">` +
    `<path d="${seg.join(' ')}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

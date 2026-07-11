/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapMap = any

const PANEL_OFFSET_X = -120

export function flyTo(
  map: AMapMap,
  center: [number, number],
  zoom: number,
  duration = 700,
): Promise<void> {
  return new Promise((resolve) => {
    try {
      map.setStatus?.({ animateEnable: true })
      map.setZoomAndCenter?.(zoom, center, false, duration)
    } catch {
      map.setCenter?.(center)
    }
    window.setTimeout(resolve, duration + 80)
  })
}

/** 将地理中心偏移到屏幕指定像素位置（侧栏占位时视觉居中路口） */
export function panToVisualCenter(
  map: AMapMap,
  lngLat: [number, number],
  pixelOffsetX = PANEL_OFFSET_X,
  pixelOffsetY = 0,
): void {
  try {
    const px = map.lngLatToContainer(lngLat)
    const x = typeof px.getX === 'function' ? px.getX() : (px as { x: number }).x
    const y = typeof px.getY === 'function' ? px.getY() : (px as { y: number }).y
    const size = map.getSize()
    const w = typeof size.getWidth === 'function' ? size.getWidth() : (size as { width: number }).width
    const h = typeof size.getHeight === 'function' ? size.getHeight() : (size as { height: number }).height
    const targetX = w / 2 + pixelOffsetX
    const targetY = h / 2 + pixelOffsetY
    map.panBy?.(targetX - x, targetY - y)
  } catch {
    /* ignore */
  }
}

export function clampZoomUp(current: number, next: number): number {
  return Math.max(current, next)
}

/**
 * 连贯下钻的单调 zoom 步序（纯函数，供单测）。
 *
 * 关键修复（消除闪烁）：每一步都 **严格大于当前 zoom 且小于目标**，最后落到目标，
 * 因此不会出现「已在 16、进车道 17 时先飞到锚点 14（缩小再放大）」的跳变。
 * 目标不高于当前时返回 [target]（下钻场景不回退；抬升由 smoothPullback 处理）。
 */
export function drillSteps(current: number, target: number): number[] {
  if (!(target > current)) return [target]
  const anchors = [14, 16.2, 17.5]
  const steps = anchors.filter((z) => z > current && z < target)
  steps.push(target)
  return [...new Set(steps)].sort((a, b) => a - b)
}

/** 单调连贯下钻：从当前 zoom 起只放大不回退，逐段平滑 flyTo。 */
export async function drillToIntersection(
  map: AMapMap,
  center: [number, number],
  finalZoom: number,
): Promise<void> {
  const current = map.getZoom?.() ?? 11
  for (const z of drillSteps(current, finalZoom)) {
    await flyTo(map, center, z, 700)
  }
  panToVisualCenter(map, center)
}

/**
 * 平滑抬升/回拉镜头（允许受控降 zoom，单次动画）。
 * 用于溯源/干线阶段从车道级(≈18) 连贯过渡到干线级(17)，禁止硬 setZoomAndCenter 刷新。
 */
export function smoothPullback(
  map: AMapMap,
  center: [number, number],
  zoom: number,
  duration = 900,
): Promise<void> {
  return flyTo(map, center, zoom, duration)
}

/** 方位汉字 → 地理 bearing（北=0，东=90）。 */
export function bearingFromDirectionLabel(dir: string | null | undefined): number | null {
  const d = String(dir ?? '').trim()
  if (!d) return null
  if (d.includes('东') && d.includes('南')) return 135
  if (d.includes('东') && d.includes('北')) return 45
  if (d.includes('西') && d.includes('南')) return 225
  if (d.includes('西') && d.includes('北')) return 315
  if (d.includes('东')) return 90
  if (d.includes('西')) return 270
  if (d.includes('南')) return 180
  if (d.includes('北')) return 0
  return null
}

const EARTH_R = 6378137

/** 沿 bearing 偏移 center（米），供 micro-dolly 纯函数测试。 */
export function offsetLngLatByMeters(
  center: [number, number],
  bearingDeg: number,
  meters: number,
): [number, number] {
  const br = (bearingDeg * Math.PI) / 180
  const dLat = (meters * Math.cos(br)) / EARTH_R
  const dLng = (meters * Math.sin(br)) / (EARTH_R * Math.cos((center[1] * Math.PI) / 180))
  return [center[0] + (dLng * 180) / Math.PI, center[1] + (dLat * 180) / Math.PI]
}

export type BoundsLngLat = { sw: [number, number]; ne: [number, number] }

/** 多点外包矩形（纯函数）。 */
export function boundsFromPoints(points: [number, number][]): BoundsLngLat | null {
  const valid = points.filter(
    (p) => Number.isFinite(p[0]) && Number.isFinite(p[1]),
  )
  if (valid.length === 0) return null
  let minLng = valid[0][0]
  let maxLng = valid[0][0]
  let minLat = valid[0][1]
  let maxLat = valid[0][1]
  for (const [lng, lat] of valid) {
    minLng = Math.min(minLng, lng)
    maxLng = Math.max(maxLng, lng)
    minLat = Math.min(minLat, lat)
    maxLat = Math.max(maxLat, lat)
  }
  return { sw: [minLng, minLat], ne: [maxLng, maxLat] }
}

export interface FitBoundsOptions {
  padding?: [number, number, number, number]
  maxZoom?: number
  duration?: number
  panelOffsetX?: number
  /** 高德 AMap 命名空间，用于构造 Bounds。 */
  AMap?: any
}

function estimateZoomForBounds(bounds: BoundsLngLat, maxZoom: number): number {
  const lngSpan = Math.max(bounds.ne[0] - bounds.sw[0], 0.0004)
  const latSpan = Math.max(bounds.ne[1] - bounds.sw[1], 0.0004)
  const span = Math.max(lngSpan, latSpan)
  let z = 18
  if (span > 0.04) z = 13
  else if (span > 0.02) z = 14.2
  else if (span > 0.012) z = 15.2
  else if (span > 0.008) z = 16.2
  else if (span > 0.004) z = 17.2
  else if (span > 0.002) z = 17.8
  return Math.min(maxZoom, z)
}

/** 多点 fitBounds + 侧栏视觉居中校正。 */
export async function fitBoundsForPoints(
  map: AMapMap,
  points: [number, number][],
  opts: FitBoundsOptions = {},
): Promise<void> {
  const bounds = boundsFromPoints(points)
  if (!bounds) return
  const pad = opts.padding ?? [80, 80, 80, 80]
  const duration = opts.duration ?? 900
  const maxZoom = opts.maxZoom ?? 18
  const cx = (bounds.sw[0] + bounds.ne[0]) / 2
  const cy = (bounds.sw[1] + bounds.ne[1]) / 2
  const z = estimateZoomForBounds(bounds, maxZoom)

  return new Promise((resolve) => {
    try {
      map.setStatus?.({ animateEnable: true })
      const AMapNS = opts.AMap
      if (AMapNS?.Bounds && typeof map.setBounds === 'function') {
        const b = new AMapNS.Bounds(bounds.sw, bounds.ne)
        map.setBounds(b, false, pad, duration)
      } else {
        map.setZoomAndCenter?.(z, [cx, cy], false, duration)
      }
    } catch {
      map.setCenter?.([cx, cy])
      map.setZoom?.(z)
    }
    window.setTimeout(() => {
      panToVisualCenter(map, [cx, cy], opts.panelOffsetX ?? PANEL_OFFSET_X)
      const current = map.getZoom?.()
      if (typeof current === 'number' && current > maxZoom) map.setZoom?.(maxZoom)
      resolve()
    }, duration + 80)
  })
}

/** 沿进口 bearing 微推镜头，突出问题进口（zoom +0.3，上限 18.5）。 */
export async function microDollyToApproach(
  map: AMapMap,
  center: [number, number],
  bearingDeg: number,
  currentZoom: number,
): Promise<number> {
  const focus = offsetLngLatByMeters(center, (bearingDeg + 180) % 360, 42)
  const z = Math.min(18.5, currentZoom + 0.35)
  await flyTo(map, focus, z, 650)
  panToVisualCenter(map, focus)
  return z
}

/** 分步插值 pitch，避免俯仰角硬切。 */
export async function lerpPitch(
  map: AMapMap,
  from: number,
  to: number,
  duration = 600,
): Promise<void> {
  const steps = Math.max(2, Math.ceil(Math.abs(to - from) / 8))
  const stepMs = Math.floor(duration / steps)
  for (let i = 1; i <= steps; i++) {
    const t = i / steps
    const p = from + (to - from) * t
    try {
      map.setPitch?.(p)
    } catch {
      /* ignore */
    }
    await new Promise((r) => window.setTimeout(r, stepMs))
  }
}

export { PANEL_OFFSET_X }

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

export { PANEL_OFFSET_X }

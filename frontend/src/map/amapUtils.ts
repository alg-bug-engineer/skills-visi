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

/** 多段推进式 zoom-in，避免一次跳变 */
export async function drillToIntersection(
  map: AMapMap,
  center: [number, number],
  finalZoom: number,
): Promise<void> {
  const steps = [14, 16.2, Math.min(finalZoom, 17.5)]
  const unique = [...new Set(steps.filter((z) => z <= finalZoom))]
  if (!unique.includes(finalZoom) && finalZoom > (unique[unique.length - 1] ?? 11)) {
    unique.push(finalZoom)
  }
  for (const z of unique) {
    await flyTo(map, center, z, 700)
  }
  panToVisualCenter(map, center)
}

export { PANEL_OFFSET_X }

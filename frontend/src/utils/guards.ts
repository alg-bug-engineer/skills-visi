import type { LngLat } from '@/api/types'

/** 坐标有效性：两个有限数。用于地图覆盖物 null 守卫（F-06）。 */
export function hasCoord(lng: unknown, lat: unknown): boolean {
  return typeof lng === 'number' && Number.isFinite(lng) && typeof lat === 'number' && Number.isFinite(lat)
}

/** 过滤出有效坐标点列。 */
export function validPath(path: unknown): LngLat[] {
  if (!Array.isArray(path)) return []
  return path.filter(
    (p): p is LngLat => Array.isArray(p) && p.length >= 2 && hasCoord(p[0], p[1]),
  )
}

export function nonEmpty<T>(arr: T[] | null | undefined): arr is T[] {
  return Array.isArray(arr) && arr.length > 0
}

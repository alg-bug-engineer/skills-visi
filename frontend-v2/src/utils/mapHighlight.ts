import type { IntersectionLink } from '../types/map'

export interface GeoBounds {
  minLon: number
  maxLon: number
  minLat: number
  maxLat: number
}

export function boundsFromLinks(
  links: IntersectionLink[],
  center: [number, number],
  pad = 0.00018,
): GeoBounds {
  let minLon = center[0]
  let maxLon = center[0]
  let minLat = center[1]
  let maxLat = center[1]

  for (const link of links) {
    for (const [lon, lat] of link.path) {
      minLon = Math.min(minLon, lon)
      maxLon = Math.max(maxLon, lon)
      minLat = Math.min(minLat, lat)
      maxLat = Math.max(maxLat, lat)
    }
  }

  return {
    minLon: minLon - pad,
    maxLon: maxLon + pad,
    minLat: minLat - pad,
    maxLat: maxLat + pad,
  }
}

export function boxPath(bounds: GeoBounds): Array<[number, number]> {
  const { minLon, maxLon, minLat, maxLat } = bounds
  return [
    [minLon, minLat],
    [maxLon, minLat],
    [maxLon, maxLat],
    [minLon, maxLat],
  ]
}

export function isEntranceRole(role: string): boolean {
  return role === 'entrance' || role === '进口'
}

export function linkMatchesDir(link: IntersectionLink, dir: string | null): boolean {
  if (!dir) return false
  const label = link.dir4_label || link.dir8_label || ''
  return label.includes(dir)
}

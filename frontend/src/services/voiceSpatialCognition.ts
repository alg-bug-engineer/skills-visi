import type { RunResponse } from '@/api/types'

export interface AxisRoads {
  ew_road?: string | null
  ns_road?: string | null
  road_pair?: string[]
  available?: boolean
  source?: string
}

/** act2 路口空间认知播报（数据来自 spatial_scene.axis_roads，禁止前端编造）。 */
export function voiceSpatialCognition(resp: RunResponse | null): string | null {
  const scene = resp?.phases?.intent?.spatial_scene
  const name = scene?.target?.inter_name ?? resp?.diagnosis_ticket?.intersection_name
  if (!name) return null

  const axis = (scene?.axis_roads ?? {}) as AxisRoads
  const ew = axis.ew_road?.trim()
  const ns = axis.ns_road?.trim()

  if (ew && ns) return `${name}，东西向是${ew}，南北向是${ns}`
  if (ew) return `${name}，东西向是${ew}，南北向道路信息待补全`
  if (ns) return `${name}，南北向是${ns}，东西向道路信息待补全`
  const pair = (axis.road_pair ?? []).map((road) => road.trim()).filter(Boolean)
  if (pair.length >= 2) return `${name}，由${pair[0]}与${pair[1]}相交`
  return null
}

import type { RunResponse } from '@/api/types'
import type { ActMapScene } from '@/composables/useTimeline'

type UnknownRecord = Record<string, unknown>

function isRecord(value: unknown): value is UnknownRecord {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function findMockVisualizationPaths(value: unknown, prefix = ''): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, i) => findMockVisualizationPaths(item, `${prefix}[${i}]`))
  }
  if (!isRecord(value)) return []
  const selfMock = value.mock === true || value.source === 'mock_visualization'
  const own = selfMock ? [prefix || 'scene'] : []
  return [...new Set([...own, ...Object.entries(value).flatMap(([key, item]) => findMockVisualizationPaths(item, prefix ? `${prefix}.${key}` : key))])]
}

function scenePayload(scene: ActMapScene, resp: RunResponse | null): unknown {
  if (!resp) return null
  const mapScenes = resp.phases?.diagnosis?.map_scenes as UnknownRecord | undefined
  switch (scene.evidence) {
    case 'recognition': return resp.phases?.intent?.spatial_scene
    case 'overflow_validation': return mapScenes?.queue_evidence ?? mapScenes?.channelization_map
    case 'downstream_topology': return mapScenes?.diagnosis_compare ?? mapScenes?.downstream_trace_map
    case 'flow_trace': return mapScenes?.flow_trace_segment_coverage_map ?? mapScenes?.flow_trace_links_sniff_map
    case 'cause_annotation': return mapScenes?.cause_spatial
    case 'control_scope': return resp.phases?.strategy?.control_scope_map
    case 'plan_output': return ((resp.plan as unknown) as UnknownRecord | undefined)?.map_scene ?? mapScenes?.plan_preview
    default: return resp.diagnosis_ticket
  }
}

export function mockWarningsForScene(scene: ActMapScene, resp: RunResponse | null): string[] {
  return findMockVisualizationPaths(scenePayload(scene, resp))
}

/** 生产响应出现 mock 时拒绝消费；开发 fixture 则由地图持续警告。 */
export function assertNoProductionMock(scene: ActMapScene, resp: RunResponse | null): void {
  if (!import.meta.env.PROD) return
  const paths = mockWarningsForScene(scene, resp)
  if (paths.length) throw new Error(`生产响应禁止 mock_visualization: ${paths.join(', ')}`)
}

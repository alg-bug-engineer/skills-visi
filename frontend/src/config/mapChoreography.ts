import type { EvidenceStage } from '@/map/sceneEvidencePolicy'

export interface MapBeat {
  overlaySettleMs: number
  camera: 'city' | 'drill' | 'micro-dolly' | 'fit-bounds' | 'hold'
}

/**
 * 地图 Promise 的最后一拍。主镜头由 AMap 动画 Promise 计时，这里只等待覆盖物稳定，
 * 因此 map barrier 代表“镜头 + 图层”都已完成，而不是估算旁白时长。
 */
export const MAP_CHOREOGRAPHY: Record<EvidenceStage, MapBeat> = {
  overview: { camera: 'city', overlaySettleMs: 180 },
  recognition: { camera: 'drill', overlaySettleMs: 260 },
  overflow_validation: { camera: 'micro-dolly', overlaySettleMs: 420 },
  downstream_topology: { camera: 'fit-bounds', overlaySettleMs: 480 },
  flow_trace: { camera: 'fit-bounds', overlaySettleMs: 620 },
  cause_annotation: { camera: 'micro-dolly', overlaySettleMs: 360 },
  control_scope: { camera: 'fit-bounds', overlaySettleMs: 520 },
  plan_output: { camera: 'drill', overlaySettleMs: 460 },
  feedback: { camera: 'hold', overlaySettleMs: 180 },
}

function instantPresentation(): boolean {
  if (typeof window === 'undefined') return true
  return (
    new URLSearchParams(window.location.search).get('instant') === '1' ||
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  )
}

export function waitForMapBeat(stage: EvidenceStage | undefined): Promise<void> {
  if (!stage || instantPresentation()) return Promise.resolve()
  const ms = MAP_CHOREOGRAPHY[stage].overlaySettleMs
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function waitForMapSubBeat(stage: EvidenceStage | undefined, ratio = 0.28): Promise<void> {
  if (!stage || instantPresentation()) return Promise.resolve()
  return new Promise((resolve) => window.setTimeout(resolve, Math.round(MAP_CHOREOGRAPHY[stage].overlaySettleMs * ratio)))
}

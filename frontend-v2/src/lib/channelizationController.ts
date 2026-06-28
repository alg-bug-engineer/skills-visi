/**
 * channelizationController.ts
 *
 * 渠化层生命周期 + 阶段同步控制器（与框架无关）。
 * 主图(MapStage)与迷你窗复用同一控制器，避免重复逻辑。
 */
import { ChannelizationAmapLayer, type ChannelInterItem } from './channelizationAmap'
import { applyPhaseHighlight, type PhaseHighlightParams } from './channelizationPhase'

/* eslint-disable @typescript-eslint/no-explicit-any */
type AMapNS = any
type AMapMap = any

export interface ChannelizationController {
  mount(interItem: ChannelInterItem): void
  applyLOD(zoom: number): void
  syncPhase(params: PhaseHighlightParams): void
  readonly center: [number, number] | null
  readonly boxR: number | null
  active(): boolean
  dispose(): void
}

export function createChannelizationController(amap: AMapNS, map: AMapMap): ChannelizationController {
  let layer: ChannelizationAmapLayer | null = null
  return {
    mount(interItem) {
      if (layer) {
        layer.dispose()
        layer = null
      }
      layer = new ChannelizationAmapLayer(amap, map, interItem)
      layer.render()
    },
    applyLOD(zoom) {
      layer?.applyLOD(zoom)
    },
    syncPhase(params) {
      if (layer) applyPhaseHighlight(layer, params)
    },
    get center() {
      return layer?.center ?? null
    },
    get boxR() {
      return layer?.boxR ?? null
    },
    active() {
      return layer != null
    },
    dispose() {
      layer?.dispose()
      layer = null
    },
  }
}

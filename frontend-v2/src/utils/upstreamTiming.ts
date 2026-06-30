import type { UpstreamFrame } from './upstreamFrame'

/** 流量溯源主视角 zoom（自渠化 ~18.5 平滑过渡到该值，蔓延过程保持恒定） */
export const UPSTREAM_CORRIDOR_ZOOM = 16
export const UPSTREAM_FRAME_MS = 2600
export const UPSTREAM_SPREAD_MS = 1500
export const UPSTREAM_PULLBACK_MS = 1200
/** 与 ChannelizationStageOverlay chan-full 过渡时长对齐 */
export const UPSTREAM_CHAN_FADE_MS = 550
/** 渠化隐去后、拉远前仅展示道路 link 的停留 */
export const UPSTREAM_ROAD_HOLD_MS = 450

export function upstreamFrameDuration(frame: UpstreamFrame | undefined): number {
  if (!frame) return UPSTREAM_FRAME_MS
  if (frame.frame_type === 'spread') return UPSTREAM_SPREAD_MS
  if (frame.frame_type === 'pullback') return UPSTREAM_PULLBACK_MS
  return UPSTREAM_FRAME_MS
}

export function upstreamStoryboardDurationMs(frames: UpstreamFrame[] | undefined): number {
  if (!frames?.length) return 0
  return frames.reduce((sum, f) => sum + upstreamFrameDuration(f), 400)
}

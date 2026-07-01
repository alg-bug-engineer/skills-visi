export interface UpstreamFrame {
  idx: number
  tree: string
  focus?: unknown
  center?: [number | null, number | null] | null
  zoom?: number | null
  fit?: boolean
  reveal: string[]
  narration?: string
  frame_type?: 'pullback' | 'target' | 'spread' | 'cross' | 'node' | 'fit'
  show_labels?: boolean
  animate_edge?: string | null
}

export interface UpstreamStoryboard {
  trees: unknown[]
  frames: UpstreamFrame[]
  /** 多进口道并行呈现时为 true，前端不按 tree 变暗 */
  parallel?: boolean
}

/**
 * 帧重建：返回 frames[0..n] 内 reveal 的累计并集，以及当前帧的树/焦点/运镜信息。
 * 纯函数、幂等——任意帧都能确定性重算可见集，供自动逐帧运镜。
 */
export function visibleAtFrame(sb: UpstreamStoryboard, n: number) {
  const overlayIds = new Set<string>()
  const clamped = Math.max(0, Math.min(n, sb.frames.length - 1))
  for (let i = 0; i <= clamped; i++) {
    for (const id of sb.frames[i].reveal) overlayIds.add(id)
  }
  const frame = sb.frames[clamped]
  return {
    overlayIds,
    activeTree: frame.tree,
    focus: frame.focus,
    center: frame.center ?? null,
    zoom: frame.zoom ?? null,
    fit: Boolean(frame.fit),
    narration: frame.narration,
    frame,
  }
}

/** 该帧是否为「边」覆盖物 id（前端按前缀区分节点/连线）。 */
export function isEdgeId(id: string): boolean {
  return id.startsWith('edge:')
}

/** 上游路口来流进口道段（十字高亮）。 */
export function isFeedSegmentId(id: string): boolean {
  return id.startsWith('feed:')
}

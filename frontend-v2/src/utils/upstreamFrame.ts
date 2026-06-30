export interface UpstreamFrame {
  idx: number
  tree: string
  kind: string
  focus: unknown
  reveal: string[]
  camera?: string
  narration?: string
}

export interface UpstreamStoryboard {
  trees: unknown[]
  frames: UpstreamFrame[]
}

/**
 * 帧重建：返回 frames[0..n] 内 reveal 的累计并集，以及当前帧的树/焦点。
 * 纯函数、幂等——拖回任意帧都能确定性重算可见集。
 */
export function visibleAtFrame(sb: UpstreamStoryboard, n: number) {
  const overlayIds = new Set<string>()
  const clamped = Math.max(0, Math.min(n, sb.frames.length - 1))
  for (let i = 0; i <= clamped; i++) {
    for (const id of sb.frames[i].reveal) overlayIds.add(id)
  }
  const frame = sb.frames[clamped]
  return { overlayIds, activeTree: frame.tree, focus: frame.focus, frame }
}

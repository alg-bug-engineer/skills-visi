/**
 * 上游溯源标注防重叠：给同帧可见的多个节点分配不同的像素偏移锚点，
 * 使浮动文本卡围绕各自路口错位散开，避免相互遮挡。
 *
 * 采用确定性的「环形锚点」轮转：相邻节点必然落在不同方位，
 * 纯函数、可单测；真实像素重叠由偏移幅度 + 方位差共同规避。
 */
export interface LabelAnchorInput {
  id: string
  hop?: number | null
}

// 围绕节点的 6 个方位偏移（像素）：上 / 右上 / 右下 / 下 / 左下 / 左上
const ANCHOR_RING: Array<[number, number]> = [
  [0, -58],
  [82, -30],
  [82, 30],
  [0, 58],
  [-82, 30],
  [-82, -30],
]

export function assignLabelAnchors(
  nodes: LabelAnchorInput[],
): Record<string, [number, number]> {
  const out: Record<string, [number, number]> = {}
  nodes.forEach((n, i) => {
    if (!n.id) return
    // 二跳节点向外多推一档，进一步拉开层级
    const base = ANCHOR_RING[i % ANCHOR_RING.length]
    const scale = (n.hop ?? 1) >= 2 ? 1.35 : 1
    out[n.id] = [Math.round(base[0] * scale), Math.round(base[1] * scale)]
  })
  return out
}

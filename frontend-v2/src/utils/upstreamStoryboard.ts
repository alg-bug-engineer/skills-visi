import type { UpstreamStoryboard, UpstreamTreeEdge, UpstreamTreeNode } from '../types/map'
import type { HighlightTurn } from '../types/presentation'

export const MAX_UPSTREAM_TRACE_HOPS = 5

type UpstreamTree = {
  tree_id: string
  approach: string
  nodes: UpstreamTreeNode[]
  edges: UpstreamTreeEdge[]
}

type FrameLike = UpstreamStoryboard['frames'][number]

export interface UpstreamPrepareResult {
  storyboard: UpstreamStoryboard
  selectedApproach: string | null
}

function normalizeDirText(text: string | null | undefined): string {
  const raw = String(text ?? '').replace(/进口道|进口|出口|车道|道/g, '')
  for (const dir of ['东北', '东南', '西北', '西南', '东', '西', '南', '北']) {
    if (raw.includes(dir)) return dir
  }
  return raw.trim()
}

function targetDirFromHint(hint?: HighlightTurn | string | null): string {
  if (!hint) return ''
  if (typeof hint === 'string') return normalizeDirText(hint)
  return normalizeDirText(hint.label || `${hint.dir}${hint.turn || ''}` || hint.dir)
}

function nodeKey(node: UpstreamTreeNode): string {
  return String(node.id || node.inter_id || '')
}

function frameIds(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  if (value == null) return []
  return [String(value)].filter(Boolean)
}

function filterFocus(focus: unknown, allowedIds: Set<string>): unknown {
  if (Array.isArray(focus)) return focus.map(String).filter((id) => allowedIds.has(id))
  if (typeof focus === 'string') return allowedIds.has(focus) ? focus : null
  return focus
}

function asTrees(sb: UpstreamStoryboard): UpstreamTree[] {
  return (sb.trees as UpstreamTree[] | undefined ?? []).filter(
    (tree) => tree && Array.isArray(tree.nodes) && Array.isArray(tree.edges),
  )
}

function treeMatchesTarget(tree: UpstreamTree, targetDir: string): boolean {
  if (!targetDir) return true
  const approachDir = normalizeDirText(tree.approach)
  return approachDir === targetDir || tree.approach.includes(targetDir)
}

function feedSegmentIds(node: UpstreamTreeNode): string[] {
  return (node.feed_segments ?? [])
    .map((seg) => String(seg.id ?? ''))
    .filter(Boolean)
}

function cappedTree(tree: UpstreamTree) {
  const allowedNodeIds = new Set<string>()
  const feedIds = new Set<string>()
  const nodes = tree.nodes.filter((node) => {
    const id = nodeKey(node)
    if (!id) return false
    const keep = node.role === 'target' || (node.hop ?? 0) <= MAX_UPSTREAM_TRACE_HOPS
    if (keep) {
      allowedNodeIds.add(id)
      for (const fid of feedSegmentIds(node)) feedIds.add(fid)
    }
    return keep
  })
  const edges = tree.edges.filter((edge) => {
    const from = String(edge.from ?? '')
    const to = String(edge.to ?? '')
    return Boolean(edge.id) && allowedNodeIds.has(from) && allowedNodeIds.has(to)
  })
  const allowedIds = new Set([
    ...allowedNodeIds,
    ...feedIds,
    ...edges.map((edge) => edge.id),
  ])
  return {
    tree: { ...tree, nodes, edges },
    allowedIds,
  }
}

export function prepareUpstreamStoryboard(
  storyboard: UpstreamStoryboard,
  targetHint?: HighlightTurn | string | null,
): UpstreamPrepareResult {
  const targetDir = targetDirFromHint(targetHint)
  const originalTrees = asTrees(storyboard)
  const matched = originalTrees.filter((tree) => treeMatchesTarget(tree, targetDir))
  const sourceTrees = matched.length ? matched : originalTrees
  const capped = sourceTrees.map(cappedTree)
  const trees = capped.map((item) => item.tree)
  const allowedIds = new Set(capped.flatMap((item) => [...item.allowedIds]))
  const singleTreeId = trees.length === 1 ? trees[0].tree_id : null

  const frames = storyboard.frames
    .map((frame): FrameLike | null => {
      const reveal = frameIds(frame.reveal).filter((id) => allowedIds.has(id))
      const focus = filterFocus(frame.focus, allowedIds)
      if (
        !reveal.length &&
        (frame.frame_type === 'node' ||
          frame.frame_type === 'spread' ||
          frame.frame_type === 'cross')
      ) {
        return null
      }
      return {
        ...frame,
        tree: singleTreeId ?? frame.tree,
        focus,
        reveal,
      }
    })
    .filter((frame): frame is FrameLike => Boolean(frame))
    .map((frame, idx) => ({ ...frame, idx }))

  return {
    storyboard: {
      ...storyboard,
      trees,
      frames,
      parallel: trees.length > 1 ? Boolean(storyboard.parallel) : false,
    },
    selectedApproach: trees.length === 1 ? trees[0].approach : null,
  }
}

/** 干线路径线宽：低流量仍可见，高流量加粗但不淹没底图。 */
export function upstreamEdgeStrokeWeight(flowPct: number | null | undefined): number {
  const pct = Math.max(0, Math.min(100, Number(flowPct) || 0))
  return 2.8 + Math.sqrt(pct / 100) * 5.7
}

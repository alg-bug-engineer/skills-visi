import { describe, expect, it } from 'vitest'
import type { HighlightTurn } from '../types/presentation'
import type { UpstreamStoryboard, UpstreamTreeEdge, UpstreamTreeNode } from '../types/map'
import {
  MAX_UPSTREAM_TRACE_HOPS,
  prepareUpstreamStoryboard,
  upstreamEdgeStrokeWeight,
} from './upstreamStoryboard'

function tree(treeId: string, approach: string, hops: number) {
  const target = { id: `${treeId}-T`, inter_id: `${treeId}-T`, role: 'target', lon: 0, lat: 0 }
  const nodes: UpstreamTreeNode[] = [target]
  const edges: UpstreamTreeEdge[] = []
  let prev = target.id
  for (let hop = 1; hop <= hops; hop += 1) {
    const id = `${treeId}-U${hop}`
    nodes.push({
      id,
      inter_id: id,
      name: `${approach}${hop}`,
      role: hop === hops ? 'governance' : 'upstream',
      hop,
      lon: hop,
      lat: hop,
      saturation: 0.6 + hop / 20,
    })
    edges.push({
      id: `edge:${treeId}:${prev}-${id}`,
      from: prev,
      to: id,
      flow_pct: 20 + hop * 10,
      path: [
        [hop - 1, hop - 1] as [number, number],
        [hop, hop] as [number, number],
      ],
    })
    prev = id
  }
  return { tree_id: treeId, approach, nodes, edges }
}

function storyboard(): UpstreamStoryboard {
  const west = tree('W', '西进口', 7)
  const north = tree('N', '北进口', 3)
  return {
    trees: [west, north],
    parallel: true,
    frames: [
      { idx: 0, tree: '*', frame_type: 'target', focus: ['W-T', 'N-T'], reveal: ['W-T', 'N-T'] },
      {
        idx: 1,
        tree: '*',
        frame_type: 'spread',
        focus: ['edge:W:W-T-W-U1', 'edge:N:N-T-N-U1'],
        reveal: ['edge:W:W-T-W-U1', 'edge:N:N-T-N-U1'],
      },
      { idx: 2, tree: '*', frame_type: 'node', focus: ['W-U1', 'N-U1'], reveal: ['W-U1', 'N-U1'] },
      { idx: 3, tree: '*', frame_type: 'node', focus: 'W-U6', reveal: ['W-U6', 'edge:W:W-U5-W-U6'] },
      { idx: 4, tree: '*', frame_type: 'fit', focus: ['W-U1', 'W-U6'], fit: true, reveal: ['W-U5', 'W-U6', 'edge:W:W-U5-W-U6'] },
    ],
  }
}

describe('prepareUpstreamStoryboard', () => {
  it('keeps only the tree for the fixed import approach hinted by a turn label', () => {
    const hint: HighlightTurn = { dir: '西', turn: '左转', label: '西左转道' }
    const prepared = prepareUpstreamStoryboard(storyboard(), hint)

    expect(prepared.storyboard.trees).toHaveLength(1)
    expect(prepared.storyboard.trees[0].tree_id).toBe('W')
    expect(prepared.selectedApproach).toBe('西进口')
    expect(prepared.storyboard.parallel).toBe(false)
    expect(prepared.storyboard.frames.every((f) => f.tree === 'W')).toBe(true)
  })

  it('caps visible upstream nodes, edges and frame ids to five hops', () => {
    const prepared = prepareUpstreamStoryboard(storyboard(), { dir: '西', turn: '左转' })
    const west = prepared.storyboard.trees[0]

    expect(MAX_UPSTREAM_TRACE_HOPS).toBe(5)
    expect(west.nodes.some((n) => n.id === 'W-U6')).toBe(false)
    expect(west.nodes.some((n) => n.id === 'W-U5')).toBe(true)
    expect(west.edges.some((e) => e.to === 'W-U6')).toBe(false)
    expect(prepared.storyboard.frames.flatMap((f) => f.reveal)).not.toContain('W-U6')
    expect(prepared.storyboard.frames.flatMap((f) => f.reveal)).not.toContain('edge:W:W-U5-W-U6')
  })

  it('maps higher flow percentages to thicker bounded strokes', () => {
    expect(upstreamEdgeStrokeWeight(20)).toBeLessThan(upstreamEdgeStrokeWeight(80))
    expect(upstreamEdgeStrokeWeight(-10)).toBe(upstreamEdgeStrokeWeight(0))
    expect(upstreamEdgeStrokeWeight(200)).toBeLessThanOrEqual(8.5)
  })
})

<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { buildDownstreamTopology, type DownstreamTopologyMetrics } from '@/map/downstreamTopologyLayer'
import { sceneEvidencePolicy } from '@/map/sceneEvidencePolicy'
import type { LngLat } from '@/map/channelizationGeometry'
import { ratio } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()

const target = computed<[number, number] | null>(() => {
  const ticket = store.ticket
  if (typeof ticket?.lng === 'number' && typeof ticket?.lat === 'number') return [ticket.lng, ticket.lat]
  return null
})

const visible = computed(() => {
  const scene = store.activeAct?.scene
  return Boolean(scene && sceneEvidencePolicy(scene).downstreamTopology)
})

const topology = computed(() => buildDownstreamTopology(store.diagnosis?.map_scenes as never, target.value))

const targetName = computed(() => productCopy(store.ticket?.intersection_name ?? '目标路口'))

const round = (n: number) => Math.round(n * 100) / 100

/** 将经纬度路径投影到 100×72 视图（按纬度做经度收缩，保持近似真实形态）。 */
const graph = computed(() => {
  const t = topology.value
  const pts: LngLat[] = []
  if (t.target) pts.push(t.target)
  for (const e of t.edges) for (const p of e.path) pts.push(p)
  for (const n of t.nodes) pts.push(n.position)
  if (pts.length < 2) return null

  const latRef = t.target?.[1] ?? pts[0][1]
  const kx = Math.cos((latRef * Math.PI) / 180) || 1
  const xs = pts.map((p) => p[0] * kx)
  const ys = pts.map((p) => p[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = Math.max(maxX - minX, 1e-9)
  const spanY = Math.max(maxY - minY, 1e-9)
  const W = 100
  const H = 72
  const pad = 13
  const scale = Math.min((W - 2 * pad) / spanX, (H - 2 * pad) / spanY)
  const offX = (W - spanX * scale) / 2
  const offY = (H - spanY * scale) / 2
  const project = (p: LngLat): [number, number] => [
    round(offX + (p[0] * kx - minX) * scale),
    round(offY + (maxY - p[1]) * scale),
  ]

  const edges = t.edges
    .filter((e) => e.path.length >= 2)
    .map((e) => ({
      id: e.id,
      highlighted: e.highlighted,
      points: e.path.map(project).map(([x, y]) => `${x},${y}`).join(' '),
    }))

  const nodes = t.nodes.map((n) => {
    const [x, y] = project(n.position)
    return { id: n.id, name: productCopy(n.name), x, y, highlighted: n.highlighted, metrics: n.metrics }
  })

  const targetPt = t.target ? (() => { const [x, y] = project(t.target); return { x, y } })() : null

  // 无折线路径的节点：补一条目标→节点的直连边，保证拓扑连通
  const straight = targetPt
    ? nodes
        .filter((n) => !t.edges.some((e) => e.id === n.id || e.id === `trace:${n.id}`))
        .map((n) => ({ id: `link:${n.id}`, highlighted: n.highlighted, points: `${targetPt.x},${targetPt.y} ${n.x},${n.y}` }))
    : []

  return { edges: [...edges, ...straight], nodes, target: targetPt }
})

const hotCount = computed(() => topology.value.nodes.filter((n) => n.highlighted).length)

function satText(metrics: DownstreamTopologyMetrics | undefined): string | null {
  if (!metrics) return null
  const parts: string[] = []
  if (metrics.queueRatio != null && metrics.queueRatio > 0) parts.push(`排队比 ${ratio(metrics.queueRatio)}`)
  if (metrics.saturation != null && metrics.saturation > 0) parts.push(`饱和 ${ratio(metrics.saturation)}`)
  return parts.length ? parts.join(' · ') : null
}
</script>

<template>
  <aside
    v-if="visible && topology.nodes.length"
    class="topology-inset us-panel"
    data-testid="downstream-topology-inset"
  >
    <header>
      <span class="mark" />
      <h3>下游承接关系图谱</h3>
      <span class="count">{{ topology.nodes.length }} 节点<template v-if="hotCount"> · 重点 {{ hotCount }}</template></span>
    </header>

    <svg v-if="graph" viewBox="0 0 100 72" class="topo__svg" preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="topo-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
          <path d="M0,0 L5,2.5 L0,5 Z" class="arrow" />
        </marker>
        <marker id="topo-arrow-hot" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
          <path d="M0,0 L5,2.5 L0,5 Z" class="arrow arrow--hot" />
        </marker>
      </defs>

      <polyline
        v-for="e in graph.edges"
        :key="e.id"
        :points="e.points"
        class="edge"
        :class="{ hot: e.highlighted }"
        :marker-end="e.highlighted ? 'url(#topo-arrow-hot)' : 'url(#topo-arrow)'"
      />

      <g v-if="graph.target">
        <circle :cx="graph.target.x" :cy="graph.target.y" r="2.8" class="node-target" />
        <text :x="graph.target.x" :y="graph.target.y - 4" class="label label--target" text-anchor="middle">
          {{ targetName }}
        </text>
      </g>

      <g v-for="n in graph.nodes" :key="n.id">
        <circle :cx="n.x" :cy="n.y" :r="n.highlighted ? 2.4 : 1.9" class="node" :class="{ hot: n.highlighted }" />
        <text :x="n.x" :y="n.y + 4.6" class="label" :class="{ 'label--hot': n.highlighted }" text-anchor="middle">
          {{ n.name }}
        </text>
        <text
          v-if="satText(n.metrics)"
          :x="n.x"
          :y="n.y + 7.8"
          class="label label--metric"
          text-anchor="middle"
        >
          {{ satText(n.metrics) }}
        </text>
      </g>
    </svg>

    <p v-else class="empty">下游拓扑坐标不足，暂不绘制路径图谱</p>

    <div class="legend">
      <span class="legend__item"><i class="dot dot--target" />目标路口</span>
      <span class="legend__item"><i class="dot dot--hot" />重点下游</span>
      <span class="legend__item"><i class="dot" />相邻下游</span>
    </div>
  </aside>
</template>

<style scoped>
.topology-inset {
  width: min(390px, calc(100vw - 32px));
  padding: 13px 14px 12px;
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(0, 229, 255, 0.1), transparent 48%),
    rgba(3, 12, 22, 0.88);
}
header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.mark {
  width: 8px;
  height: 8px;
  background: var(--primary);
  box-shadow: var(--glow-primary);
}
h3 {
  flex: 1;
  margin: 0;
  font-size: 13px;
  letter-spacing: 0;
  color: var(--text);
}
.count {
  color: var(--text-mute);
  font-size: 11px;
}
.topo__svg {
  width: 100%;
  height: 200px;
  overflow: visible;
}
.edge {
  fill: none;
  stroke: rgba(138, 160, 184, 0.5);
  stroke-width: 0.7;
  stroke-dasharray: 2 1.6;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.edge.hot {
  stroke: #38bdf8;
  stroke-width: 1.1;
  stroke-dasharray: none;
}
.arrow {
  fill: rgba(138, 160, 184, 0.7);
}
.arrow--hot {
  fill: #38bdf8;
}
.node {
  fill: #0b1a2b;
  stroke: #8aa0b8;
  stroke-width: 0.7;
}
.node.hot {
  fill: rgba(14, 165, 233, 0.25);
  stroke: #38bdf8;
  stroke-width: 0.9;
}
.node-target {
  fill: rgba(255, 92, 92, 0.28);
  stroke: var(--alarm);
  stroke-width: 1;
}
.label {
  font-size: 3px;
  fill: var(--text-dim);
}
.label--target {
  fill: var(--alarm-2);
  font-weight: 700;
}
.label--hot {
  fill: var(--text);
}
.label--metric {
  font-size: 2.6px;
  fill: var(--text-mute);
}
.empty {
  margin: 6px 0;
  font-size: 12px;
  color: var(--text-mute);
}
.legend {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid rgba(146, 161, 181, 0.18);
}
.legend__item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-mute);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0b1a2b;
  border: 1px solid #8aa0b8;
}
.dot--hot {
  background: rgba(14, 165, 233, 0.35);
  border-color: #38bdf8;
}
.dot--target {
  background: rgba(255, 92, 92, 0.35);
  border-color: var(--alarm);
}
</style>

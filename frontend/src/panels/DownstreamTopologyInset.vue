<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { buildDownstreamTopology, type DownstreamTopologyMetrics } from '@/map/downstreamTopologyLayer'
import { sceneEvidencePolicy } from '@/map/sceneEvidencePolicy'
import { pct, meters } from '@/utils/format'
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
const hotNodes = computed(() => topology.value.nodes.filter((n) => n.highlighted))
const otherNodes = computed(() => topology.value.nodes.filter((n) => !n.highlighted))

function metricText(metrics: DownstreamTopologyMetrics | undefined): string {
  if (!metrics) return '指标暂无'
  const q = metrics.queueRatio == null ? '排队暂无' : `排队 ${pct(metrics.queueRatio)}`
  const s = metrics.saturation == null ? '饱和暂无' : `饱和 ${pct(metrics.saturation)}`
  const g = metrics.greenUtilization == null ? '绿灯暂无' : `绿灯 ${pct(metrics.greenUtilization)}`
  const storage = metrics.remainingStorageM == null ? '余量暂无' : `余量 ${meters(metrics.remainingStorageM)}`
  return `${q}｜${s}｜${g}｜${storage}`
}
</script>

<template>
  <aside v-if="visible && topology.nodes.length" class="topology-inset us-panel" data-testid="downstream-topology-inset">
    <header>
      <span class="mark" />
      <h3>下游承接关系图谱</h3>
      <span class="count">{{ topology.nodes.length }} 节点</span>
    </header>

    <div class="graph">
      <div class="target">
        <span class="dot target-dot" />
        <span>{{ productCopy(store.ticket?.intersection_name ?? '目标路口') }}</span>
      </div>
      <div class="links">
        <article v-for="node in hotNodes" :key="node.id" class="node hot">
          <span class="dot" />
          <div>
            <strong>{{ productCopy(node.name) }}</strong>
            <p>{{ metricText(node.metrics) }}</p>
          </div>
        </article>
        <article v-for="node in otherNodes" :key="node.id" class="node">
          <span class="dot" />
          <div>
            <strong>{{ productCopy(node.name) }}</strong>
            <p>{{ metricText(node.metrics) }}</p>
          </div>
        </article>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.topology-inset {
  width: min(390px, calc(100vw - 32px));
  padding: 13px 14px 14px;
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(0, 229, 255, 0.1), transparent 48%),
    rgba(3, 12, 22, 0.88);
}
header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
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
.graph {
  position: relative;
  padding-left: 4px;
}
.target,
.node {
  display: flex;
  align-items: flex-start;
  gap: 9px;
}
.target {
  color: var(--alarm-2);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
.links {
  display: grid;
  gap: 7px;
  padding-left: 16px;
  border-left: 1px solid rgba(0, 229, 255, 0.22);
  margin-left: 5px;
}
.node {
  position: relative;
  padding: 8px 9px;
  border: 1px solid rgba(138, 160, 184, 0.24);
  background: rgba(255, 255, 255, 0.03);
}
.node::before {
  content: '';
  position: absolute;
  left: -17px;
  top: 17px;
  width: 16px;
  height: 1px;
  background: rgba(0, 229, 255, 0.28);
}
.node.hot {
  border-color: rgba(56, 189, 248, 0.7);
  background: rgba(14, 165, 233, 0.1);
}
.dot {
  width: 8px;
  height: 8px;
  margin-top: 4px;
  border-radius: 50%;
  background: #8aa0b8;
  box-shadow: 0 0 10px rgba(138, 160, 184, 0.45);
  flex: 0 0 auto;
}
.target-dot {
  background: var(--alarm);
  box-shadow: var(--glow-alarm);
}
.hot .dot {
  background: #38bdf8;
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.78);
}
strong {
  display: block;
  color: var(--text);
  font-size: 12px;
  line-height: 1.35;
}
p {
  margin: 2px 0 0;
  color: var(--text-dim);
  font-size: 10.5px;
  line-height: 1.45;
}
</style>

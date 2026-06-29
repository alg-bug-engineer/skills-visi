<script setup lang="ts">
import { computed } from 'vue'
import type { FlowTrace } from '../../types/evidence'
import { buildFlowTraceSummaryLines } from '../../utils/flowTraceCopy'

const props = defineProps<{
  flowTrace?: FlowTrace | null
}>()

const lines = computed(() => buildFlowTraceSummaryLines(props.flowTrace))
const show = computed(() => lines.value.length > 0)
</script>

<template>
  <aside
    v-if="show"
    class="flow-trace-summary"
    data-testid="flow-trace-map-summary"
    aria-label="流量溯源摘要"
  >
    <header class="head">流量溯源 · 上一跳来源</header>
    <p class="hint">按进口道约 100 辆过境车，统计上一路口左/直/右来车（近月同时段）</p>
    <ul class="list">
      <li v-for="line in lines" :key="line.id">{{ line.text }}</li>
    </ul>
  </aside>
</template>

<style scoped>
.flow-trace-summary {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 18;
  width: min(340px, 42vw);
  max-height: 28vh;
  overflow-y: auto;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(6, 12, 22, 0.92);
  border: 1px solid rgba(255, 184, 108, 0.35);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  pointer-events: auto;
  font-family: 'Inter', system-ui, sans-serif;
}
.head {
  margin: 0;
  font-size: 11px;
  font-weight: 700;
  color: #ffb86c;
  letter-spacing: 0.5px;
}
.hint {
  margin: 4px 0 8px;
  font-size: 9px;
  line-height: 1.45;
  color: rgba(180, 200, 220, 0.65);
}
.list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.list li {
  font-size: 11px;
  line-height: 1.5;
  color: rgba(226, 246, 255, 0.92);
}
</style>

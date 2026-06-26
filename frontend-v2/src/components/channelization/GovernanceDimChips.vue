<script setup lang="ts">
import type { FlowTimingGovernance } from '../../types/evidence'

defineProps<{
  governance: FlowTimingGovernance
}>()
</script>

<template>
  <div class="gov-dims" role="list" aria-label="流量-配时四维诊断">
    <div
      v-for="problem in governance.problems ?? []"
      :key="problem.category"
      class="dim-chip"
      role="listitem"
      :class="{ active: problem.detected, [`sev-${problem.severity}`]: problem.detected }"
    >
      <span class="dim-label">{{ problem.label }}</span>
      <span class="dim-status">{{ problem.detected ? '命中' : '正常' }}</span>
    </div>
  </div>
</template>

<style scoped>
.gov-dims {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  align-items: stretch;
}

.dim-chip {
  flex: 0 0 auto;
  min-width: 88px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  opacity: 0.65;
}

.dim-chip.active {
  opacity: 1;
  border-color: rgba(56, 189, 248, 0.4);
  background: rgba(14, 116, 144, 0.15);
}

.dim-chip.sev-high {
  border-color: rgba(248, 113, 113, 0.5);
}

.dim-label {
  display: block;
  font-size: 10px;
  font-weight: 600;
  color: rgba(232, 244, 255, 0.92);
  white-space: nowrap;
}

.dim-status {
  display: block;
  margin-top: 2px;
  font-size: 9px;
  color: rgba(148, 196, 230, 0.75);
}
</style>

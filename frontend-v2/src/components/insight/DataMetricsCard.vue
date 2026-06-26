<script setup lang="ts">
import type { DataInsight } from '../../types/insight'

defineProps<{
  insight: DataInsight
}>()
</script>

<template>
  <article class="stack-card data-card">
    <header class="card-head">
      <span v-if="insight.icon" class="icon">{{ insight.icon }}</span>
      <div>
        <span class="eyebrow">运行数据</span>
        <h3>{{ insight.title || '路口指标' }}</h3>
      </div>
    </header>
    <div class="metrics">
      <div
        v-for="(m, i) in insight.metrics"
        :key="i"
        class="metric"
        :class="m.severity ? `sev-${m.severity}` : ''"
      >
        <span class="label">{{ m.label }}</span>
        <span class="value">{{ m.value }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 8px 10px;
  background: rgba(0, 12, 26, 0.96);
  border: 1px solid rgba(0, 212, 240, 0.22);
  border-left: 2px solid #00d4f0;
  color: rgba(226, 246, 255, 0.92);
}

.card-head {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  margin-bottom: 6px;
}

.icon {
  font-size: 13px;
  line-height: 1;
}

.eyebrow {
  display: block;
  font-size: 8px;
  letter-spacing: 0.8px;
  color: rgba(0, 229, 255, 0.65);
}

.card-head h3 {
  margin: 1px 0 0;
  font-size: 11px;
  font-weight: 600;
  color: #f0f8ff;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}

.metric {
  padding: 4px 6px;
  background: rgba(0, 16, 32, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 2px;
  min-width: 0;
}

.label {
  display: block;
  font-size: 8px;
  color: rgba(200, 230, 255, 0.5);
  margin-bottom: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.value {
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: #00e5ff;
  line-height: 1.2;
}

.metric.sev-high .value {
  color: #ff7b7b;
}

.metric.sev-medium .value {
  color: #ffc266;
}
</style>

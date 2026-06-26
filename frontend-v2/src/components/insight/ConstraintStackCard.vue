<script setup lang="ts">
import type { QuantitativeConstraints } from '../../types/evidence'
import { constraintProgress, formatMetricValue, metricLabel } from '../../utils/evidencePresentation'

defineProps<{
  constraints: QuantitativeConstraints
}>()

const intentLabel: Record<string, string> = {
  no_spillback: '防溢流',
  no_queue_growth: '排队不加剧',
  no_worsen: '不恶化',
  saturation_cap: '饱和度上限',
  protect: '保护方向',
}
</script>

<template>
  <article class="stack-card constraint-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">治理边界</span>
        <h3>用户约束已量化</h3>
      </div>
    </header>

    <p v-if="constraints.raw_text" class="raw">「{{ constraints.raw_text }}」</p>
    <p v-if="constraints.narrative" class="narrative">{{ constraints.narrative }}</p>

    <div v-if="constraints.intent" class="tags">
      <span class="tag">{{ intentLabel[constraints.intent] ?? constraints.intent }}</span>
      <span v-if="constraints.protected_directions?.length" class="tag protect">
        保护 {{ constraints.protected_directions.join('、') }}
      </span>
    </div>

    <div
      v-for="(item, i) in constraints.constraints ?? []"
      :key="`${item.metric}-${i}`"
      class="bound"
    >
      <div class="bound-head">
        <span class="scope">{{ item.scope }}</span>
        <span class="expr">
          {{ metricLabel(item.metric) }} {{ item.operator }}
          {{ formatMetricValue(item.metric, item.value) }}
        </span>
      </div>
      <div class="bar">
        <div class="bar-fill" :style="{ width: `${constraintProgress(item).pct}%` }" />
      </div>
      <div class="bar-labels">
        <span>现状 {{ formatMetricValue(item.metric, item.baseline ?? 0) }}</span>
        <span>上限 {{ formatMetricValue(item.metric, item.value) }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 12px 14px;
  background: rgba(0, 14, 12, 0.96);
  color: rgba(226, 246, 255, 0.92);
}

.constraint-card {
  border: 1px solid rgba(109, 255, 181, 0.35);
  border-left: 3px solid #6dffb5;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #6dffb5;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: #f0f8ff;
}

.raw {
  margin: 0 0 4px;
  font-size: 11px;
  color: rgba(200, 230, 255, 0.55);
}

.narrative {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(220, 240, 255, 0.9);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.tag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 2px;
  border: 1px solid rgba(109, 255, 181, 0.35);
  color: #6dffb5;
}

.tag.protect {
  color: #9ec5ff;
  border-color: rgba(158, 197, 255, 0.35);
}

.bound {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.bound-head {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  margin-bottom: 4px;
  gap: 6px;
}

.scope {
  color: #6dffb5;
  font-weight: 600;
}

.expr {
  font-family: 'Courier New', monospace;
  color: rgba(220, 240, 255, 0.85);
  text-align: right;
}

.bar {
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #38b2ac, #6dffb5);
}

.bar-labels {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: rgba(200, 230, 255, 0.5);
  margin-top: 3px;
}
</style>

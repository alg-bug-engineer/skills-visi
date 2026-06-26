<script setup lang="ts">
import { computed } from 'vue'
import type { QuantitativeConstraints } from '../../types/evidence'
import { constraintProgress, formatMetricValue, metricLabel } from '../../utils/evidencePresentation'

const props = defineProps<{
  constraints: QuantitativeConstraints | null
}>()

const hasConstraints = computed(
  () => Boolean(props.constraints?.narrative || props.constraints?.constraints?.length),
)

const intentLabel: Record<string, string> = {
  no_spillback: '防溢流',
  no_queue_growth: '排队不加剧',
  no_worsen: '不恶化',
  saturation_cap: '饱和度上限',
  protect: '保护方向',
}
</script>

<template>
  <section v-if="hasConstraints" class="constraint-panel">
    <header class="panel-head">
      <span class="eyebrow">CONSTRAINTS</span>
      <h3>约束量化</h3>
    </header>

    <div class="panel-body">
      <p v-if="constraints?.raw_text" class="raw-text">「{{ constraints.raw_text }}」</p>
      <p v-if="constraints?.narrative" class="narrative">{{ constraints.narrative }}</p>

      <div v-if="constraints?.intent" class="intent-row">
        <span class="intent-badge">{{ intentLabel[constraints.intent] ?? constraints.intent }}</span>
        <span v-if="constraints.primary_directions?.length" class="dir-chip primary">
          主方向 {{ constraints.primary_directions.join('、') }}
        </span>
        <span v-if="constraints.protected_directions?.length" class="dir-chip protect">
          保护 {{ constraints.protected_directions.join('、') }}
        </span>
      </div>

      <div
        v-for="(item, i) in constraints?.constraints ?? []"
        :key="`${item.metric}-${item.scope}-${i}`"
        class="constraint-item"
      >
        <div class="item-head">
          <span class="scope">{{ item.scope }}</span>
          <span class="expr">
            {{ metricLabel(item.metric) }} {{ item.operator }} {{ formatMetricValue(item.metric, item.value) }}
          </span>
        </div>
        <div class="range-bar">
          <div class="range-track">
            <div
              class="range-baseline"
              :style="{ width: `${constraintProgress(item).pct}%` }"
            />
            <div class="range-cap" />
          </div>
          <div class="range-labels">
            <span>现状 {{ formatMetricValue(item.metric, item.baseline ?? 0) }}</span>
            <span>上限 {{ formatMetricValue(item.metric, item.value) }}</span>
          </div>
        </div>
        <p v-if="(item.baseline ?? 0) < 0.01 && item.metric === 'spillback_risk'" class="hint">
          现状几乎无排队：上限表示在现状基础上最多恶化约 5 个百分点，非绝对红线。
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.constraint-panel {
  border-bottom: 1px solid rgba(109, 255, 181, 0.15);
  background: rgba(0, 16, 12, 0.45);
}

.panel-head {
  padding: 12px 14px 0;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1.2px;
  color: rgba(109, 255, 181, 0.75);
}

.panel-head h3 {
  margin: 4px 0 0;
  font-size: 14px;
  color: rgba(226, 246, 255, 0.95);
}

.panel-body {
  padding: 10px 14px 14px;
}

.raw-text {
  margin: 0 0 6px;
  font-size: 11px;
  color: rgba(200, 230, 255, 0.55);
}

.narrative {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(220, 240, 255, 0.9);
}

.intent-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.intent-badge {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 2px;
  background: rgba(109, 255, 181, 0.12);
  border: 1px solid rgba(109, 255, 181, 0.35);
  color: #6dffb5;
}

.dir-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.dir-chip.primary {
  color: #ffc266;
}

.dir-chip.protect {
  color: #9ec5ff;
}

.constraint-item {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid rgba(109, 255, 181, 0.2);
  border-radius: 2px;
  background: rgba(0, 10, 8, 0.5);
}

.item-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 11px;
}

.scope {
  color: #6dffb5;
  font-weight: 600;
}

.expr {
  color: rgba(220, 240, 255, 0.8);
  font-family: 'Courier New', monospace;
}

.range-track {
  position: relative;
  height: 8px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  overflow: hidden;
}

.range-baseline {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: linear-gradient(90deg, #38b2ac, #6dffb5);
}

.range-cap {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #ffc266;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.45);
}

.hint {
  margin: 6px 0 0;
  font-size: 10px;
  color: rgba(255, 194, 102, 0.85);
  line-height: 1.45;
}
</style>

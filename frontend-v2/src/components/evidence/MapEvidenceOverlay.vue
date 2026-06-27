<script setup lang="ts">
import { computed } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'
import { THRESHOLDS } from '../../constants'
import { formatSaturation, sourceTierLabel } from '../../utils/evidencePresentation'

const props = defineProps<{
  evidence: ProblemEvidence
}>()

const emit = defineEmits<{
  dismiss: []
}>()

const chronicRate = computed(() => {
  const c = props.evidence.chronic
  if (!c?.window_days) return null
  return ((c.congested_days ?? 0) / c.window_days) * 100
})

const dowRate = computed(() => {
  const d = props.evidence.dow_pattern
  if (d?.hit_rate != null) return d.hit_rate * 100
  return null
})
</script>

<template>
  <div class="map-evidence-card" role="dialog" aria-label="问题验证">
    <header class="card-head">
      <div>
        <span class="eyebrow">问题验证</span>
        <h3>数据印证用户描述</h3>
      </div>
      <button type="button" class="dismiss" title="收起" @click="emit('dismiss')">×</button>
    </header>

    <p v-if="evidence.coverage_warning" class="warn">{{ evidence.coverage_warning }}</p>
    <p v-if="evidence.summary" class="summary">{{ evidence.summary }}</p>

    <div class="badges">
      <span v-if="evidence.chronic?.is_chronic" class="badge chronic">
        常发 {{ evidence.chronic.congested_days }}/{{ evidence.chronic.window_days }} 日
      </span>
      <span v-if="evidence.dow_pattern?.dow_label" class="badge dow">
        每逢{{ evidence.dow_pattern.dow_label }}
      </span>
      <span class="badge tier">{{ sourceTierLabel(evidence.source_tier) }}</span>
    </div>

    <div v-if="chronicRate != null" class="meter">
      <div class="meter-top">
        <span>常发命中</span>
        <span>{{ chronicRate.toFixed(0) }}%</span>
      </div>
      <div class="track"><div class="fill chronic" :style="{ width: `${chronicRate}%` }" /></div>
    </div>

    <div v-if="dowRate != null" class="meter">
      <div class="meter-top">
        <span>{{ evidence.dow_pattern?.dow_label }}命中</span>
        <span>{{ dowRate.toFixed(0) }}%</span>
      </div>
      <div class="track"><div class="fill dow" :style="{ width: `${dowRate}%` }" /></div>
    </div>

    <div v-if="evidence.metrics" class="metrics">
      <div class="m-item">
        <span class="m-label">饱和度</span>
        <span
          class="m-val"
          :class="{
            high: (evidence.metrics.saturation_rate ?? 0) >= THRESHOLDS.saturationHigh,
          }"
        >
          {{ formatSaturation(evidence.metrics.saturation_rate) }}
        </span>
      </div>
      <div class="m-item">
        <span class="m-label">延误</span>
        <span class="m-val">{{ evidence.metrics.delay_index?.toFixed(2) ?? '—' }}</span>
      </div>
      <div class="m-item">
        <span class="m-label">排队</span>
        <span class="m-val">{{ evidence.metrics.avg_queue_m?.toFixed(0) ?? '—' }}m</span>
      </div>
    </div>

    <ul v-if="evidence.by_direction?.length" class="dirs">
      <li v-for="row in evidence.by_direction" :key="row.group" :class="{ focused: row.focused }">
        <span>{{ row.group }}<em v-if="row.focused">关注</em></span>
        <span>{{ formatSaturation(row.saturation) }} · {{ row.avg_queue_m?.toFixed(0) ?? '—' }}m</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.map-evidence-card {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 13;
  width: min(300px, calc(100% - 24px));
  max-height: min(72vh, 520px);
  overflow-y: auto;
  padding: 12px 14px 14px;
  border-radius: 4px;
  background: rgba(0, 10, 22, 0.94);
  border: 1px solid rgba(255, 194, 102, 0.45);
  border-left: 3px solid #ffc266;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(12px);
  color: rgba(226, 246, 255, 0.92);
  pointer-events: auto;
}

.card-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #ffc266;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: rgba(240, 248, 255, 0.98);
}

.dismiss {
  border: none;
  background: transparent;
  color: rgba(200, 230, 255, 0.5);
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}

.dismiss:hover {
  color: #ffc266;
}

.warn {
  margin: 0 0 8px;
  padding: 6px 8px;
  font-size: 11px;
  color: #ffc266;
  background: rgba(255, 194, 102, 0.1);
  border: 1px solid rgba(255, 194, 102, 0.3);
}

.summary {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(220, 240, 255, 0.88);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(220, 240, 255, 0.8);
}

.badge.chronic {
  color: #ff9b9b;
  border-color: rgba(255, 120, 120, 0.35);
}

.badge.dow {
  color: #ffc266;
}

.meter {
  margin-bottom: 8px;
}

.meter-top {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.55);
  margin-bottom: 3px;
}

.track {
  height: 5px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.fill {
  height: 100%;
}

.fill.chronic {
  background: #ff7b7b;
}

.fill.dow {
  background: #ffc266;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin: 10px 0;
}

.m-item {
  text-align: center;
  padding: 6px 4px;
  background: rgba(0, 16, 28, 0.6);
  border: 1px solid rgba(0, 212, 240, 0.12);
  border-radius: 2px;
}

.m-label {
  display: block;
  font-size: 9px;
  color: rgba(200, 230, 255, 0.5);
}

.m-val {
  font-size: 13px;
  font-weight: 700;
  font-family: 'Courier New', monospace;
  color: #00e5ff;
}

.m-val.high {
  color: #ff7b7b;
}

.dirs {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 11px;
}

.dirs li {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: rgba(220, 240, 255, 0.75);
}

.dirs li.focused {
  color: #ffc266;
}

.dirs em {
  margin-left: 4px;
  font-size: 9px;
  font-style: normal;
  opacity: 0.85;
}
</style>

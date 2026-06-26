<script setup lang="ts">
import { computed } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'
import { THRESHOLDS } from '../../constants'
import { formatPercent, sourceTierLabel } from '../../utils/evidencePresentation'

const props = defineProps<{
  evidence: ProblemEvidence | null
  collapsed?: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

const hasEvidence = computed(() => Boolean(props.evidence?.summary || props.evidence?.chronic))

const chronicRate = computed(() => {
  const c = props.evidence?.chronic
  if (!c?.window_days) return null
  return ((c.congested_days ?? 0) / c.window_days) * 100
})

const dowRate = computed(() => {
  const d = props.evidence?.dow_pattern
  if (d?.hit_rate != null) return d.hit_rate * 100
  return null
})

function severityClass(value: number | null | undefined, high: number): string {
  if (value == null) return ''
  if (value >= high) return 'sev-high'
  if (value >= high * 0.8) return 'sev-medium'
  return 'sev-low'
}
</script>

<template>
  <section class="evidence-panel" :class="{ collapsed }">
    <header class="panel-head" @click="emit('toggle')">
      <div>
        <span class="eyebrow">EVIDENCE</span>
        <h3>问题验证</h3>
      </div>
      <button type="button" class="toggle-btn" :aria-expanded="!collapsed">
        {{ collapsed ? '展开' : '收起' }}
      </button>
    </header>

    <div v-if="!collapsed" class="panel-body">
      <p v-if="evidence?.coverage_warning" class="warn-banner">
        {{ evidence.coverage_warning }}
      </p>

      <p v-if="!hasEvidence" class="empty">等待数据验证…</p>

      <template v-else>
        <p v-if="evidence?.summary" class="summary">{{ evidence.summary }}</p>

        <div class="badge-row">
          <span
            v-if="evidence?.chronic?.is_chronic"
            class="badge chronic"
            title="常发性拥堵"
          >
            常发性 {{ evidence.chronic?.congested_days }}/{{ evidence.chronic?.window_days }} 日
          </span>
          <span v-if="evidence?.dow_pattern?.dow_label" class="badge dow">
            每逢{{ evidence.dow_pattern.dow_label }}
          </span>
          <span class="badge tier">{{ sourceTierLabel(evidence?.source_tier) }}</span>
        </div>

        <div v-if="chronicRate != null" class="meter-block">
          <div class="meter-label">
            <span>常发命中率</span>
            <span>{{ chronicRate.toFixed(0) }}%</span>
          </div>
          <div class="meter-track">
            <div class="meter-fill chronic" :style="{ width: `${chronicRate}%` }" />
          </div>
          <p class="meter-hint">{{ evidence?.chronic?.verdict }}</p>
        </div>

        <div v-if="dowRate != null" class="meter-block">
          <div class="meter-label">
            <span>{{ evidence?.dow_pattern?.dow_label }}命中率</span>
            <span>{{ dowRate.toFixed(0) }}%</span>
          </div>
          <div class="meter-track">
            <div class="meter-fill dow" :style="{ width: `${dowRate}%` }" />
          </div>
          <p class="meter-hint">{{ evidence?.dow_pattern?.verdict }}</p>
        </div>

        <div v-if="evidence?.metrics" class="metric-grid">
          <div
            class="metric-card"
            :class="severityClass(evidence.metrics.saturation_rate, THRESHOLDS.saturationHigh)"
          >
            <span class="label">饱和度</span>
            <span class="value">{{ formatPercent(evidence.metrics.saturation_rate) }}</span>
          </div>
          <div class="metric-card">
            <span class="label">延误指数</span>
            <span class="value">{{ evidence.metrics.delay_index?.toFixed(2) ?? '—' }}</span>
          </div>
          <div class="metric-card">
            <span class="label">平均排队</span>
            <span class="value">{{ evidence.metrics.avg_queue_m?.toFixed(0) ?? '—' }}m</span>
          </div>
          <div
            class="metric-card"
            :class="severityClass(evidence.metrics.spillback_risk_max, THRESHOLDS.spillbackRiskHigh)"
          >
            <span class="label">溢流风险</span>
            <span class="value">{{ evidence.metrics.spillback_risk_max?.toFixed(2) ?? '—' }}</span>
          </div>
        </div>

        <table v-if="evidence?.by_direction?.length" class="dir-table">
          <thead>
            <tr>
              <th>方向</th>
              <th>饱和</th>
              <th>排队</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in evidence.by_direction"
              :key="row.group"
              :class="{ focused: row.focused }"
            >
              <td>
                {{ row.group }}
                <span v-if="row.focused" class="focus-tag">关注</span>
              </td>
              <td>{{ formatPercent(row.saturation) }}</td>
              <td>{{ row.avg_queue_m?.toFixed(0) ?? '—' }}m</td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </section>
</template>

<style scoped>
.evidence-panel {
  border-bottom: 1px solid rgba(0, 212, 240, 0.15);
  background: rgba(0, 8, 18, 0.6);
}

.evidence-panel.collapsed .panel-body {
  display: none;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  cursor: pointer;
  user-select: none;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1.2px;
  color: rgba(255, 194, 102, 0.85);
}

.panel-head h3 {
  margin: 4px 0 0;
  font-size: 14px;
  color: rgba(226, 246, 255, 0.95);
  font-weight: 600;
}

.toggle-btn {
  border: 1px solid rgba(0, 212, 240, 0.25);
  background: transparent;
  color: rgba(200, 230, 255, 0.7);
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 2px;
  cursor: pointer;
}

.panel-body {
  padding: 0 14px 14px;
}

.warn-banner {
  margin: 0 0 10px;
  padding: 8px 10px;
  background: rgba(255, 194, 102, 0.12);
  border: 1px solid rgba(255, 194, 102, 0.35);
  color: #ffc266;
  font-size: 12px;
  line-height: 1.5;
}

.empty {
  margin: 0;
  color: rgba(200, 230, 255, 0.45);
  font-size: 12px;
}

.summary {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(220, 240, 255, 0.88);
}

.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.badge {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.badge.chronic {
  color: #ff9b9b;
  border-color: rgba(255, 120, 120, 0.35);
  background: rgba(40, 8, 8, 0.5);
}

.badge.dow {
  color: #ffc266;
  border-color: rgba(255, 194, 102, 0.35);
}

.badge.tier {
  color: rgba(200, 230, 255, 0.55);
}

.meter-block {
  margin-bottom: 12px;
}

.meter-label {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: rgba(200, 230, 255, 0.65);
  margin-bottom: 4px;
}

.meter-track {
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  border-radius: 3px;
}

.meter-fill.chronic {
  background: linear-gradient(90deg, #ff7b7b, #ff4d4d);
}

.meter-fill.dow {
  background: linear-gradient(90deg, #ffc266, #ff9b3d);
}

.meter-hint {
  margin: 4px 0 0;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.45);
  line-height: 1.4;
}

.metric-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}

.metric-card {
  padding: 8px 10px;
  border: 1px solid rgba(0, 212, 240, 0.15);
  background: rgba(0, 12, 24, 0.5);
  border-radius: 2px;
}

.metric-card.sev-high .value {
  color: #ff7b7b;
}

.metric-card.sev-medium .value {
  color: #ffc266;
}

.metric-card .label {
  display: block;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.5);
  margin-bottom: 2px;
}

.metric-card .value {
  font-size: 15px;
  font-weight: 700;
  font-family: 'Courier New', monospace;
  color: #00e5ff;
}

.dir-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.dir-table th,
.dir-table td {
  padding: 6px 4px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.dir-table th {
  color: rgba(200, 230, 255, 0.45);
  font-weight: 500;
}

.dir-table tr.focused {
  background: rgba(255, 194, 102, 0.08);
}

.focus-tag {
  margin-left: 4px;
  font-size: 9px;
  color: #ffc266;
}
</style>

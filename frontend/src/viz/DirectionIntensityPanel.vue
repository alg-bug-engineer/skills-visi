<script setup lang="ts">
import { computed } from 'vue'
import type { OptimizationMeta } from '@/api/types'
import { directionIntensityRows } from '@/viz/planVisualization'

const props = defineProps<{ meta?: OptimizationMeta | null }>()

const target = computed(() => props.meta?.target_saturation ?? 0.8)
const rows = computed(() => directionIntensityRows(props.meta?.direction_intensity_list))
const dataQuality = computed(() => props.meta?.data_quality ?? {})

function pct(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
}

function width(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '0%'
  return `${Math.min(100, (value / target.value) * 100).toFixed(1)}%`
}

function targetLeft(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '100%'
  return value > target.value ? `${((target.value / value) * 100).toFixed(1)}%` : '100%'
}
</script>

<template>
  <section class="intensity">
    <h4>各方向供需强度</h4>
    <p class="intro">
      按进口转向对比实际供需强度 <b>I_dir</b>（≈饱和度）与目标强度 <b>I_obj</b>；越接近目标越均衡，超过目标（红色越过刻度线）说明该方向供不应求、需优先配时。
    </p>
    <div v-if="!rows.length" class="missing">后端未返回供需强度证据</div>
    <table v-else>
      <thead>
        <tr>
          <th>转向</th>
          <th>强度分布</th>
          <th>I_dir</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.movementKey || row.label || String(row.dir8No) + '-' + String(row.turnDirNo)"
          :data-testid="(row.intensity ?? 0) > target ? 'intensity-row-risk' : 'intensity-row-ok'"
        >
          <td>{{ row.label || row.movementKey || '未知转向' }}</td>
          <td>
            <div class="track">
              <div class="bar" :class="{ risk: (row.intensity ?? 0) > target }" :style="{ width: width(row.intensity) }" />
              <i class="target" :style="{ left: targetLeft(row.intensity) }" />
            </div>
          </td>
          <td class="value" :class="{ risk: (row.intensity ?? 0) > target }">{{ pct(row.intensity) }}</td>
        </tr>
      </tbody>
    </table>
    <p class="foot">
      目标强度 I_obj = {{ pct(target) }}
      <span v-if="dataQuality.movement_source">｜{{ dataQuality.movement_source }}</span>
    </p>
  </section>
</template>

<style scoped>
.intensity {
  padding-top: 10px;
  border-top: 1px solid rgba(138, 160, 180, 0.22);
}
h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text);
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  padding: 6px 4px;
  border-bottom: 1px solid rgba(138, 160, 180, 0.14);
  font-size: 12px;
}
th {
  color: var(--text-mute);
  font-weight: 600;
  text-align: left;
}
.track {
  position: relative;
  height: 8px;
  border-radius: 4px;
  background: rgba(231, 245, 255, 0.08);
  overflow: hidden;
}
.bar {
  height: 100%;
  border-radius: 4px;
  background: var(--protected-2);
}
.bar.risk {
  background: var(--evidence);
}
.target {
  position: absolute;
  top: -1px;
  bottom: -1px;
  left: 100%;
  width: 2px;
  background: var(--alarm);
}
.value {
  text-align: right;
  color: var(--protected);
  font-weight: 700;
}
.value.risk {
  color: var(--evidence);
}
.intro {
  margin: 0 0 8px;
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.5;
}
.intro b {
  color: var(--text);
  font-weight: 600;
}
.foot,
.missing {
  margin: 7px 0 0;
  color: var(--text-mute);
  font-size: 11px;
}
</style>

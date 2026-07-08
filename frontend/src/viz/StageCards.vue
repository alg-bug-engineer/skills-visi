<script setup lang="ts">
import type { PhaseStageTiming } from '@/api/types'
import StageMovementCanvas from '@/viz/StageMovementCanvas.vue'

defineProps<{ stages: PhaseStageTiming[] }>()

function sec(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}s` : '—'
}

function delta(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value === 0 ? '±0s' : `${value > 0 ? '+' : ''}${value}s`
}
</script>

<template>
  <section class="stages">
    <article v-for="(stage, i) in stages" :key="stage.phase_stage_id || i" class="card">
      <h4>阶段 {{ i + 1 }}</h4>
      <div class="cmp">
        <span class="old">{{ sec(stage.current_timing?.stage_total_s) }}</span>
        <span>→</span>
        <strong>{{ sec(stage.optimized_timing?.stage_total_s ?? stage.green_time_s) }}</strong>
        <b :class="{ up: (stage.stage_delta_s ?? 0) > 0, down: (stage.stage_delta_s ?? 0) < 0 }">{{ delta(stage.stage_delta_s) }}</b>
      </div>
      <StageMovementCanvas v-if="stage.movements?.length" :movements="stage.movements" />
      <div v-else class="missing">后端未返回释放方向证据</div>
      <div class="meta">
        <span>绿灯 {{ sec(stage.current_timing?.green_time_s) }} → {{ sec(stage.optimized_timing?.green_time_s ?? stage.green_time_s) }}</span>
        <span>最小绿 {{ sec(stage.min_green_time_s) }}</span>
      </div>
    </article>
  </section>
</template>

<style scoped>
.stages {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.card {
  flex: 0 0 176px;
  padding: 10px;
  border: 1px solid rgba(138, 160, 180, 0.28);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
}
h4 {
  margin: 0 0 8px;
  text-align: center;
  color: var(--text);
  font-size: 13px;
}
.cmp {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 5px;
  margin-bottom: 8px;
  color: var(--text-dim);
}
.old {
  text-decoration: line-through;
}
strong {
  color: var(--protected);
  font-size: 22px;
}
b {
  color: var(--text-mute);
  font-size: 12px;
}
b.up {
  color: var(--evidence);
}
b.down {
  color: var(--alarm);
}
.meta,
.missing {
  display: grid;
  gap: 3px;
  margin-top: 7px;
  color: var(--text-mute);
  font-size: 11px;
}
</style>
